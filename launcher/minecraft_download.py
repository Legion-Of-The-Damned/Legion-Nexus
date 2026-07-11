import os
import requests
import json
import hashlib
import zipfile
import sys
import subprocess
import shutil
import threading  # Добавили для синхронизации потоков
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from PySide6.QtCore import QThread, Signal

MAX_WORKERS = 10 
# Глобальный лок для предотвращения конфликтов WinError 32 при записи на диск
file_lock = threading.Lock()

def create_http_session():
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class DownloadThread(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, version, download_path, base_dir):
        super().__init__()
        self.version = version
        self.download_path = download_path
        self.base_dir = base_dir
        self.session = create_http_session()
        
    def check_file_integrity(self, path, expected_size=None, expected_hash=None):
        if not os.path.exists(path):
            return False
        if expected_size and os.path.getsize(path) != expected_size:
            return False
        if expected_hash:
            sha1 = hashlib.sha1()
            try:
                with open(path, 'rb') as f:
                    while chunk := f.read(65536):
                        sha1.update(chunk)
                if sha1.hexdigest() != expected_hash:
                    return False
            except Exception:
                return False
        return True

    def download_file(self, url, path, expected_size=None, expected_hash=None):
        try:
            # Предотвращаем гонку потоков при создании папок
            with file_lock:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            
            if self.check_file_integrity(path, expected_size, expected_hash):
                return True
            
            response = self.session.get(url, stream=True, timeout=15)
            response.raise_for_status()
            
            temp_path = f"{path}.tmp"
            with open(temp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=16384):
                    if chunk:
                        f.write(chunk)
            
            # Безопасная замена файла с использованием блокировки
            with file_lock:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass # Если файл занят, попробуем перезаписать поверх через os.rename
                if os.path.exists(temp_path):
                    shutil.move(temp_path, path)
            
            return self.check_file_integrity(path, expected_size, expected_hash)
        except Exception as e:
            print(f"Ошибка скачивания {url}: {e}")
            return False
            
    def get_version_manifest(self):
        try:
            version_url = "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json"
            response = self.session.get(version_url, timeout=10)
            response.raise_for_status()
            manifest = response.json()
            
            for version in manifest.get("versions", []):
                if version.get("id") == self.version:
                    version_response = self.session.get(version.get("url"), timeout=10)
                    version_response.raise_for_status()
                    return version_response.json()
            return None
        except Exception as e:
            print(f"Ошибка получения манифеста: {e}")
            return None
            
    def _should_download_lib(self, lib):
        if "rules" not in lib:
            return True
        allow = False
        current_os = "windows" if sys.platform == "win32" else "osx" if sys.platform == "darwin" else "linux"
        for rule in lib["rules"]:
            action = rule.get("action")
            rule_os = rule.get("os", {}).get("name")
            if action == "allow":
                if not rule_os or rule_os == current_os:
                    allow = True
            elif action == "disallow":
                if not rule_os or rule_os == current_os:
                    allow = False
        return allow

    def download_libraries(self, version_json):
        libraries_dir = os.path.join(self.download_path, "libraries")
        raw_tasks = []
        
        for lib in version_json.get("libraries", []):
            if not self._should_download_lib(lib):
                continue
            if "downloads" in lib and "artifact" in lib["downloads"]:
                art = lib["downloads"]["artifact"]
                raw_tasks.append((art.get("url"), os.path.join(libraries_dir, art.get("path")), art.get("size"), art.get("sha1")))
            if "downloads" in lib and "classifiers" in lib["downloads"]:
                classifiers = lib["downloads"]["classifiers"]
                current_native_key = "natives-windows" if sys.platform == "win32" else "natives-osx" if sys.platform == "darwin" else "natives-linux"
                for key, info in classifiers.items():
                    if current_native_key in key:
                        raw_tasks.append((info.get("url"), os.path.join(libraries_dir, info.get("path")), info.get("size"), info.get("sha1")))

        # КРИТИЧЕСКИЙ ФИКС: Убираем дубликаты задач, чтобы избежать WinError 32
        download_tasks = list(set(raw_tasks))

        total_libs = len(download_tasks)
        if total_libs == 0:
            return

        self.status.emit("Загрузка библиотек...")
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self.download_file, *task): task for task in download_tasks}
            for future in as_completed(futures):
                completed += 1
                progress = 20 + int((completed / total_libs) * 40)
                self.progress.emit(progress)
                if completed % 5 == 0 or completed == total_libs:
                    self.status.emit(f"Загрузка библиотек: {completed}/{total_libs}")

    def download_client(self, version_json):
        version_dir = os.path.join(self.download_path, "versions", self.version)
        jar_path = os.path.join(version_dir, f"{self.version}.jar")
        if "downloads" in version_json and "client" in version_json["downloads"]:
            client_info = version_json["downloads"]["client"]
            self.status.emit("Скачивание клиента Minecraft...")
            return self.download_file(client_info.get("url"), jar_path, client_info.get("size"), client_info.get("sha1"))
        return False
        
    def download_assets(self, version_json):
        assets_dir = os.path.join(self.download_path, "assets")
        asset_index = version_json.get("assetIndex", {})
        if not asset_index:
            return
            
        index_path = os.path.join(assets_dir, "indexes", f"{asset_index.get('id', self.version)}.json")
        self.status.emit("Загрузка индекса ассетов...")
        
        if not self.download_file(asset_index.get("url"), index_path, asset_index.get("size"), asset_index.get("sha1")):
            return
            
        with open(index_path, 'r') as f:
            objects = json.load(f).get("objects", {})
            
        raw_tasks = []
        for name, info in objects.items():
            hash_val = info.get("hash")
            if hash_val:
                path = os.path.join(assets_dir, "objects", hash_val[:2], hash_val)
                url = f"https://resources.download.minecraft.net/{hash_val[:2]}/{hash_val}"
                raw_tasks.append((url, path, info.get("size"), hash_val))
                
        # КРИТИЧЕСКИЙ ФИКС: Убираем дубликаты ассетов
        download_tasks = list(set(raw_tasks))

        total_assets = len(download_tasks)
        if total_assets == 0:
            return
            
        completed = 0
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self.download_file, *task): task for task in download_tasks}
            for future in as_completed(futures):
                completed += 1
                if completed % 50 == 0 or completed == total_assets:
                    self.status.emit(f"Загрузка ассетов: {completed}/{total_assets}")
                    progress = 60 + int((completed / total_assets) * 35)
                    self.progress.emit(progress)

    def extract_natives(self):
        natives_dir = os.path.join(self.download_path, "versions", self.version, "natives")
        with file_lock:
            os.makedirs(natives_dir, exist_ok=True)
        libraries_dir = os.path.join(self.download_path, "libraries")
        
        self.status.emit("Извлечение нативных библиотек...")
        for root, _, files in os.walk(libraries_dir):
            for file in files:
                if file.endswith('.jar') and ('natives' in file.lower() or 'platform' in file.lower()):
                    jar_path = os.path.join(root, file)
                    try:
                        with zipfile.ZipFile(jar_path, 'r') as zip_ref:
                            for member in zip_ref.namelist():
                                if member.endswith(('.dll', '.so', '.dylib')) and not member.startswith('META-INF'):
                                    filename = os.path.basename(member)
                                    if filename:
                                        target_path = os.path.join(natives_dir, filename)
                                        with zip_ref.open(member) as source, open(target_path, 'wb') as target:
                                            shutil.copyfileobj(source, target)
                    except Exception as e:
                        print(f"Ошибка извлечения из {jar_path}: {e}")
                        
    def run(self):
        try:
            version_dir = os.path.join(self.download_path, "versions", self.version)
            with file_lock:
                os.makedirs(version_dir, exist_ok=True)
            
            self.progress.emit(5)
            self.status.emit("Получение информации о версии...")
            version_json = self.get_version_manifest()
            
            if not version_json:
                self.finished.emit(False, "Не удалось получить информацию о версии Minecraft")
                return
                
            self.progress.emit(10)
            if not self.download_client(version_json):
                self.finished.emit(False, "Не удалось скачать клиент Minecraft")
                return
                
            self.progress.emit(20)
            self.download_libraries(version_json)
            
            self.progress.emit(60)
            self.download_assets(version_json)
            
            self.progress.emit(95)
            self.extract_natives()
            
            json_path = os.path.join(version_dir, f"{self.version}.json")
            with open(json_path, 'w') as f:
                json.dump(version_json, f, indent=2)
                
            self.progress.emit(100)
            self.status.emit("Готово!")
            self.finished.emit(True, f"Minecraft {self.version} успешно установлен!")
        except Exception as e:
            self.finished.emit(False, f"Ошибка установки: {str(e)}")


class ForgeInstaller(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(bool, str)
    
    def __init__(self, minecraft_dir, base_dir):
        super().__init__()
        self.minecraft_dir = minecraft_dir
        self.base_dir = base_dir
        self.forge_version = "1.12.2"
        self.forge_build = "14.23.5.2860"
        # Полное имя версии, как оно будет называться в папке versions
        self.version_name = f"{self.forge_version}-forge-{self.forge_build}"
        self.session = create_http_session()
        
    def download_file(self, url, path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            response = self.session.get(url, stream=True, timeout=15)
            response.raise_for_status()
            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except Exception as e:
            print(f"Ошибка скачивания Forge: {e}")
            return False
            
    def download_forge_installer(self):
        forge_url = f"https://maven.minecraftforge.net/net/minecraftforge/forge/{self.forge_version}-{self.forge_build}/forge-{self.forge_version}-{self.forge_build}-installer.jar"
        installer_path = os.path.join(self.base_dir, "temp", f"forge-{self.forge_version}-{self.forge_build}-installer.jar")
        self.status.emit("Скачивание Forge Installer...")
        if self.download_file(forge_url, installer_path):
            return installer_path
        return None

    def install_forge_extract(self, installer_path):
        """
        ИСПРАВЛЕНО: Автономная установка через распаковку архива.
        Не зависит от серверов Forge и не падает из-за сетевых таймаутов Java.
        """
        try:
            self.status.emit("Распаковка и анализ Forge...")
            
            target_version_dir = os.path.join(self.minecraft_dir, "versions", self.version_name)
            os.makedirs(target_version_dir, exist_ok=True)
            
            # Читаем внутренности инсталлятора как ZIP
            with zipfile.ZipFile(installer_path, 'r') as z:
                # 1. Извлекаем профиль версии (install_profile.json)
                if "install_profile.json" not in z.namelist():
                    return False, "Неверный формат инсталлятора Forge"
                
                profile_data = json.loads(z.read("install_profile.json").decode('utf-8'))
                version_data = profile_data.get("versionInfo") # Это готовый JSON для лаунчера!
                
                # Если в инсталляторе структура отличается, пробуем прочесть version.json
                if not version_data and "version.json" in z.namelist():
                    version_data = json.loads(z.read("version.json").decode('utf-8'))
                
                if not version_data:
                    return False, "Не удалось извлечь конфигурацию версии Forge"

                # Модифицируем ID версии, чтобы лаунчер её точно видел
                version_data["id"] = self.version_name

                # Сохраняем JSON версии в корневую папку Minecraft/versions/
                json_path = os.path.join(target_version_dir, f"{self.version_name}.json")
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(version_data, f, indent=2)

                # 2. Извлекаем сам универсальный JAR-файл Forge
                # У Forge 1.12.2 путь внутри инсталлятора обычно такой: maven/net/minecraftforge/forge/...
                forge_jar_internal_path = f"maven/net/minecraftforge/forge/{self.forge_version}-{self.forge_build}/forge-{self.forge_version}-{self.forge_build}-universal.jar"
                
                # Если universal нет, ищем обычный jar
                if forge_jar_internal_path not in z.namelist():
                    forge_jar_internal_path = f"maven/net/minecraftforge/forge/{self.forge_version}-{self.forge_build}/forge-{self.forge_version}-{self.forge_build}.jar"

                if forge_jar_internal_path in z.namelist():
                    # Куда кладем в библиотеках
                    libraries_forge_dir = os.path.join(
                        self.minecraft_dir, "libraries", "net", "minecraftforge", "forge", f"{self.forge_version}-{self.forge_build}"
                    )
                    os.makedirs(libraries_forge_dir, exist_ok=True)
                    
                    target_jar_name = f"forge-{self.forge_version}-{self.forge_build}.jar"
                    target_jar_path = os.path.join(libraries_forge_dir, target_jar_name)
                    
                    with z.open(forge_jar_internal_path) as source, open(target_jar_path, 'wb') as target:
                        shutil.copyfileobj(source, target)
                else:
                    print("Предупреждение: Основной JAR Forge не найден внутри инсталлятора, будет скачан через манифест.")

            return True, "Конфигурация Forge успешно развернута"
        except Exception as e:
            return False, f"Ошибка распаковки инсталлятора: {str(e)}"
            
    def run(self):
        try:
            self.progress.emit(5)
            installer_path = self.download_forge_installer()
            if not installer_path:
                self.finished.emit(False, "Не удалось скачать установщик Forge")
                return
                
            self.progress.emit(40)
            success, message = self.install_forge_extract(installer_path)
            if not success:
                self.finished.emit(False, message)
                return
                
            self.progress.emit(80)
            # Удаляем временный инсталлятор
            if os.path.exists(installer_path):
                try:
                    os.remove(installer_path)
                except Exception:
                    pass
                    
            self.progress.emit(100)
            self.status.emit("Готово!")
            self.finished.emit(True, f"Forge {self.version_name} успешно развернут!")
        except Exception as e:
            self.finished.emit(False, f"Ошибка Forge Installer: {str(e)}")