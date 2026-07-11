import os
import json
import hashlib
import urllib.request
from PySide6.QtCore import QThread, Signal

class GameUpdateWorker(QThread):
    # Сигналы для вывода статуса в панель настроек
    status_signal = Signal(str)      # Текстовый статус ("проверка", "скачивание...")
    progress_signal = Signal(int, int) # Текущий файл (индекс, всего файлов)

    def __init__(self, base_dir, manifest_path, download_base_url):
        super().__init__()
        self.base_dir = base_dir
        self.manifest_path = manifest_path
        self.download_base_url = download_base_url # Например, 'https://raw.githubusercontent.com/User/Repo/main/game_files/'

    def _calculate_sha256(self, filepath):
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return None

    def run(self):
        # 1. Сначала скачиваем свежий манифест с сервера игроку
        self.status_signal.emit("checking")
        try:
            manifest_url = self.download_base_url + "launcher_manifest.json"
            req = urllib.request.Request(manifest_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req) as response:
                manifest = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Ошибка загрузки манифеста: {e}")
            self.status_signal.emit("manifest_missing")
            return

        # 2. Воссоздаем структуру папок (из блока "folders" твоего нового скрипта)
        folders = manifest.get("folders", [])
        for folder in folders:
            full_folder_path = os.path.join(self.base_dir, folder)
            if not os.path.exists(full_folder_path):
                os.makedirs(full_folder_path, exist_ok=True)

        # 3. Проверяем файлы по хэшам и составляем список на скачивание
        manifest_files = manifest.get("files", {})
        files_to_download = []

        for file_path, expected_hash in manifest_files.items():
            full_path = os.path.join(self.base_dir, file_path)
            
            if not os.path.isfile(full_path):
                files_to_download.append(file_path)
                continue
                
            if self._calculate_sha256(full_path) != expected_hash:
                files_to_download.append(file_path)

        if not files_to_download:
            self.status_signal.emit("launcher_ok")
            return

        # 4. Скачиваем только отсутствующие или поврежденные файлы
        self.status_signal.emit("downloading")
        total_files = len(files_to_download)
        
        for index, file_path in enumerate(files_to_download, start=1):
            self.progress_signal.emit(index, total_files)
            
            full_path = os.path.join(self.base_dir, file_path)
            file_url = self.download_base_url + file_path.replace(" ", "%20") # Кодируем пробелы в URL
            
            # Обеспечиваем создание родительской папки для файла на всякий случай
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            try:
                req_file = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req_file) as stream, open(full_path, "wb") as f:
                    f.write(stream.read())
            except Exception as e:
                print(f"Не удалось скачать {file_path}: {e}")
                self.status_signal.emit("check_failed")
                return

        self.status_signal.emit("launcher_ok")