import os
import json
import sys
import subprocess
import shutil
import time
import traceback

from PySide6.QtGui import QFontDatabase, QFont, QPixmap, QPainterPath, QRegion, QIcon, QPainter, QDesktopServices
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QPushButton,
    QLabel,
    QProgressBar,
    QLineEdit,
    QMessageBox,
    QFileDialog,
    QVBoxLayout,
    QFrame
)
from PySide6.QtCore import Qt, QEvent, QSize, QTimer, QUrl, QPoint

from launcher.mods_page import AddonsPage
from launcher.settings import SettingsPanel
from launcher.config import ConfigManager
from launcher.discord_rpc import DiscordRPCManager
from launcher.minecraft_download import DownloadThread, ForgeInstaller
from launcher.server_status import ServerStatusWidget
from launcher.sound_manager import SoundManager, SoundButton


class SkinMenu(QFrame):
    """Выпадающее меню для загрузки скина и плаща"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(180, 80)
        
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(20, 20, 20, 240);
                border: 1px solid rgba(139, 0, 0, 180);
                border-radius: 8px;
            }
            QPushButton {
                background-color: transparent;
                color: #e0e0e0;
                border: none;
                text-align: left;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: rgba(139, 0, 0, 100);
                color: white;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        self.skin_btn = SoundButton("🎨 Загрузить скин", sound_id="click")
        self.skin_btn.setCursor(Qt.PointingHandCursor)
        self.skin_btn.clicked.connect(self.on_skin_click)
        layout.addWidget(self.skin_btn)
        
        self.cape_btn = SoundButton("🧥 Загрузить плащ", sound_id="click")
        self.cape_btn.setCursor(Qt.PointingHandCursor)
        self.cape_btn.clicked.connect(self.on_cape_click)
        layout.addWidget(self.cape_btn)
    
    def on_skin_click(self):
        self.hide()
        if self.parent():
            self.parent().load_skin()
    
    def on_cape_click(self):
        self.hide()
        if self.parent():
            self.parent().load_cape()
    
    def show_at_position(self, pos):
        self.move(pos)
        self.show()
        self.raise_()


class MinecraftLauncher:
    """Класс для запуска Minecraft с поддержкой Forge, скинов и настроек"""
    
    def __init__(self, base_dir, settings_panel=None):
        self.base_dir = base_dir
        self.config = None
        self.settings_panel = settings_panel
    
    def load_config(self):
        config_path = os.path.join(self.base_dir, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except:
                self.config = {}
        else:
            self.config = {}
    
    def get_minecraft_dir(self):
        self.load_config()
        
        if self.config and self.config.get("minecraft_path"):
            minecraft_path = self.config["minecraft_path"]
            if minecraft_path and os.path.exists(minecraft_path):
                return minecraft_path
        
        default_path = os.path.join(self.base_dir, "..", "Minecraft")
        if os.path.exists(default_path):
            return default_path
        
        system = sys.platform
        if system == 'win32':
            return os.path.join(os.getenv('APPDATA'), '.minecraft')
        elif system == 'darwin':
            return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'minecraft')
        else:
            return os.path.join(os.path.expanduser('~'), '.minecraft')
    
    def find_java(self):
        self.load_config()
        
        if self.config and self.config.get("java_path"):
            if os.path.exists(self.config["java_path"]):
                print(f"Найдена Java из конфига: {self.config['java_path']}")
                return self.config["java_path"]
        
        runtime_dir = os.path.join(self.base_dir, "runtime", "java8")
        
        if sys.platform == 'win32':
            java_paths = [
                os.path.join(runtime_dir, "bin", "javaw.exe"),
                os.path.join(runtime_dir, "bin", "java.exe"),
                os.path.join(runtime_dir, "jre", "bin", "javaw.exe"),
                os.path.join(runtime_dir, "jre8", "bin", "javaw.exe"),
            ]
            
            for java_path in java_paths:
                if os.path.exists(java_path):
                    print(f"Найдена встроенная Java: {java_path}")
                    return java_path
        
        java_in_path = shutil.which("java")
        if java_in_path:
            print(f"Найдена Java в PATH: {java_in_path}")
            return java_in_path
        
        print("Java не найдена!")
        return None
    
    def find_forge_version(self, minecraft_dir):
        versions_dir = os.path.join(minecraft_dir, "versions")
        
        if not os.path.exists(versions_dir):
            return None
        
        # Корректное сканирование директории versions на наличие Forge сборки
        for version_name in os.listdir(versions_dir):
            if "forge" in version_name.lower():
                jar_path = os.path.join(versions_dir, version_name, f"{version_name}.jar")
                if os.path.exists(jar_path):
                    return version_name
        
        vanilla_path = os.path.join(versions_dir, "1.12.2")
        if os.path.exists(vanilla_path):
            print("Предупреждение: Forge версия не обнаружена в папке versions. Используется чистая 1.12.2")
            return "1.12.2"
        
        return None
    
    def ensure_skin_mod_installed(self, minecraft_dir):
        """Проверяет наличие CustomSkinLoader в папке mods"""
        mods_dir = os.path.join(minecraft_dir, "mods")
        os.makedirs(mods_dir, exist_ok=True)
        
        for file in os.listdir(mods_dir):
            if "CustomSkinLoader" in file and file.endswith('.jar'):
                return True
        
        print("CustomSkinLoader не найден в папке mods")
        return False
    
    def setup_custom_skin_loader(self, minecraft_dir, nickname, skin_path, skin_type="DEFAULT"):
        config_dir = os.path.join(minecraft_dir, "CustomSkinLoader")
        os.makedirs(config_dir, exist_ok=True)
        
        skins_dir = os.path.join(config_dir, "Skins")
        os.makedirs(skins_dir, exist_ok=True)
        
        if skin_path and os.path.exists(skin_path):
            target_skin = os.path.join(skins_dir, f"{nickname}.png")
            shutil.copy2(skin_path, target_skin)
            print(f"Скин скопирован в: {target_skin}")
            
            default_skin = os.path.join(skins_dir, "default.png")
            shutil.copy2(skin_path, default_skin)
        
        config = {
            "enable": True,
            "loadlist": [
                {
                    "name": "LocalSkin",
                    "type": "LocalSkin",
                    "skin": nickname,
                    "model": "steve" if skin_type == "DEFAULT" else "alex"
                }
            ],
            "cache": {
                "enable": True,
                "expiry": 3600
            }
        }
        
        config_path = os.path.join(config_dir, "config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        
        print(f"CustomSkinLoader настроен для скина: {nickname} (тип: {skin_type})")
        return True
    
    def get_ram_arguments(self):
        if self.settings_panel:
            ram_args = self.settings_panel.get_ram_argument()
            return ram_args
        
        self.load_config()
        ram_auto = self.config.get("ram_auto", False)
        
        if ram_auto:
            return ""
        else:
            ram_gb = self.config.get("ram_value", 4)
            if ram_gb > 8:
                ram_gb = 8
            return f"-Xms{ram_gb}G -Xmx{ram_gb}G"
    
    def get_resolution_config(self):
        self.load_config()
        fullscreen = self.config.get("fullscreen", False) if self.config else False
        
        if fullscreen:
            return "fullscreen"
        
        return self.config.get("resolution", "1280x720") if self.config else "1280x720"
    
    def build_classpath(self, minecraft_dir, version):
        """Собирает ВСЕ необходимые библиотеки для запуска (с гарантированным подхватом всех JAR)"""
        classpath = []
        libraries_dir = os.path.join(minecraft_dir, "libraries")
        
        # 1. Сначала собираем библиотеки по официальному JSON-файлу
        versions_to_load = [version]
        main_json_path = os.path.join(minecraft_dir, "versions", version, f"{version}.json")
        if os.path.exists(main_json_path):
            try:
                with open(main_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "inheritsFrom" in data:
                        versions_to_load.insert(0, data["inheritsFrom"])
            except Exception as e:
                print(f"Ошибка проверки наследования версий: {e}")

        for v in versions_to_load:
            json_path = os.path.join(minecraft_dir, "versions", v, f"{v}.json")
            if not os.path.exists(json_path):
                continue
                
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                
                for lib in v_data.get("libraries", []):
                    if not self._should_include_library(lib):
                        continue
                        
                    lib_path = None
                    if "downloads" in lib and "artifact" in lib["downloads"]:
                        lib_path = lib["downloads"]["artifact"].get("path")
                    elif "name" in lib:
                        parts = lib["name"].split(":")
                        group, artifact, ver = parts[0].replace(".", "/"), parts[1], parts[2]
                        classifier = ""
                        if len(parts) > 3:
                            classifier = f"-{parts[3]}"
                        lib_path = f"{group}/{artifact}/{ver}/{artifact}-{ver}{classifier}.jar"
                    
                    if lib_path:
                        full_path = os.path.normpath(os.path.join(libraries_dir, lib_path))
                        if os.path.exists(full_path) and full_path not in classpath:
                            classpath.append(full_path)
                            
            except Exception as e:
                print(f"Ошибка чтения библиотек для {v}: {e}")

        # 2. ИСПРАВЛЕНО (Гвоздь программы): Принудительный поиск критических библиотек Forge/Ванилы,
        # которые могли потеряться из-за разницы структур лаунчеров.
        if os.path.exists(libraries_dir):
            critical_keywords = ["minecraftforge", "launchwrapper", "asm", "jline", "tweak", "guava", "netty", "gson"]
            for root, dirs, files in os.walk(libraries_dir):
                for file in files:
                    if file.endswith(".jar"):
                        file_lower = file.lower()
                        # Если библиотека относится к ядру Forge или сетевому/логическому стеку Ванилы
                        if any(kw in file_lower for kw in critical_keywords):
                            full_lib_path = os.path.normpath(os.path.join(root, file))
                            if full_lib_path not in classpath:
                                classpath.append(full_lib_path)

        # 3. Подгружаем JAR-файлы самих версий игры
        for v in versions_to_load:
            jar_path = os.path.normpath(os.path.join(minecraft_dir, "versions", v, f"{v}.jar"))
            if os.path.exists(jar_path):
                if jar_path not in classpath:
                    classpath.append(jar_path)
            else:
                vanilla_jar = os.path.normpath(os.path.join(minecraft_dir, "versions", "1.12.2", "1.12.2.jar"))
                if os.path.exists(vanilla_jar) and vanilla_jar not in classpath:
                    classpath.append(vanilla_jar)
                
        return os.pathsep.join(classpath)
    
    def _should_include_library(self, lib):
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
    
    def setup_cape(self, minecraft_dir, cape_path):
        if not cape_path or not os.path.exists(cape_path):
            return False
        
        capes_dir = os.path.join(minecraft_dir, "capes")
        os.makedirs(capes_dir, exist_ok=True)
        
        cape_name = os.path.basename(cape_path)
        dest_path = os.path.join(capes_dir, cape_name)
        shutil.copy2(cape_path, dest_path)
        
        config_path = os.path.join(minecraft_dir, "CustomSkinLoader", "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                config["loadlist"].append({
                    "name": "LocalCape",
                    "type": "LocalCape",
                    "cape": cape_name
                })
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2)
                
                print(f"Плащ настроен: {dest_path}")
                return True
            except Exception as e:
                print(f"Ошибка настройки плаща: {e}")
        
        return False

    def launch(self, minecraft_dir, nickname, memory=None, skin_path=None, skin_type="DEFAULT", cape_path=None):
        java_path = self.find_java()
        if not java_path:
            print("Java не найдена!")
            return None
            
        minecraft_dir = os.path.abspath(minecraft_dir)
        
        has_skin_mod = self.ensure_skin_mod_installed(minecraft_dir)
        if not has_skin_mod:
            print("Предупреждение: CustomSkinLoader не установлен")
        
        ram_args = self.get_ram_arguments()
        resolution = self.get_resolution_config()
        version = self.find_forge_version(minecraft_dir)
        
        if not version:
            print("Не найдено ни одной версии Minecraft!")
            return None
            
        print(f"\nИспользуется Java: {java_path}")
        print(f"Запуск версии: {version}")
        print(f"Разрешение: {resolution}")
        
        version_dir = os.path.join(minecraft_dir, "versions", version)
        version_json_path = os.path.join(version_dir, f"{version}.json")
        
        if not os.path.exists(version_json_path):
            print(f"Ошибка: Конфигурационный JSON версии не найден: {version_json_path}")
            return None
            
        try:
            with open(version_json_path, "r", encoding="utf-8") as f:
                version_data = json.load(f)
        except Exception as e:
            print(f"Не удалось прочитать JSON версии: {e}")
            return None

        main_class = version_data.get("mainClass", "net.minecraft.client.main.Main")

        if skin_path and os.path.exists(skin_path):
            self.setup_custom_skin_loader(minecraft_dir, nickname, skin_path, skin_type)
        
        if cape_path and os.path.exists(cape_path):
            self.setup_cape(minecraft_dir, cape_path)
        
        classpath = self.build_classpath(minecraft_dir, version)
        
        # Если в папке Forge нет своих natives, используем нативы из ванильной папки 1.12.2
        natives_path = os.path.join(version_dir, "natives")
        if not os.path.exists(natives_path) or not os.listdir(natives_path):
            vanilla_natives = os.path.join(minecraft_dir, "versions", "1.12.2", "natives")
            if os.path.exists(vanilla_natives) and os.listdir(vanilla_natives):
                natives_path = vanilla_natives
            else:
                os.makedirs(natives_path, exist_ok=True)
                
        print(f"Путь к нативным библиотекам (natives): {natives_path}")
        
        # Собираем аргументы запуска
        args = [java_path]
        
        # Гарантированное выделение памяти
        if ram_args and ram_args.strip():
            args.extend(ram_args.split())
        else:
            print("Предупреждение: Аргументы памяти не получены. Принудительно выделено 3 ГБ.")
            args.extend(["-Xms1G", "-Xmx3G"])
            
        args.extend([
            f"-Xbootclasspath/a:{os.path.join(minecraft_dir, 'libraries', 'net', 'sf', 'jopt-simple', 'jopt-simple', '5.0.3', 'jopt-simple-5.0.3.jar')}",
            f"-Djava.library.path={natives_path}",
            "-Dminecraft.launcher.brand=legion-nexus",
            "-Dminecraft.launcher.version=1.0",
            "-cp", classpath,
            main_class
        ])
        
        game_args_list = []
        if "arguments" in version_data and "game" in version_data["arguments"]:
            for arg in version_data["arguments"]["game"]:
                if isinstance(arg, str):
                    game_args_list.append(arg)
        elif "minecraftArguments" in version_data:
            game_args_list = version_data["minecraftArguments"].split()
        
        asset_index_id = version_data.get("assetIndex", {}).get("id", "1.12")
        assets_root_dir = os.path.join(minecraft_dir, "assets")
        
        # Добавлены токены ${game_directory} и ${game_assets} для совместимости с аргументами Forge
        replacements = {
            "${auth_player_name}": nickname,
            "${version_name}": version,
            "${game_dir}": minecraft_dir,
            "${game_directory}": minecraft_dir,
            "${assets_dir}": assets_root_dir,
            "${assets_root}": assets_root_dir,
            "${game_assets}": os.path.join(assets_root_dir, "virtual", "legacy"),
            "${asset_index}": asset_index_id,
            "${assets_index_name}": asset_index_id,
            "${auth_uuid}": "00000000-0000-0000-0000-000000000000",
            "${auth_access_token}": "null",
            "${user_type}": "legacy",
            "${version_type}": version_data.get("type", "release"),
            "${user_properties}": "{}"
        }
        
        for arg in game_args_list:
            processed_arg = arg
            for token, value in replacements.items():
                processed_arg = processed_arg.replace(token, value)
            args.append(processed_arg)
            
        if resolution == "fullscreen":
            args.extend(["--width", "1920", "--height", "1080"])
        else:
            try:
                width, height = resolution.split('x')
                args.extend(["--width", width, "--height", height])
            except:
                args.extend(["--width", "1280", "--height", "720"])
                
        print(f"\nЗапуск процесса Minecraft...")
        try:
            process = subprocess.Popen(
                args, 
                cwd=minecraft_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            
            print("--- ОТЛАДКА: ПЕРВЫЕ СТРОКИ СТАРТА ИГРЫ ---")
            for _ in range(35):
                line = process.stdout.readline()
                if not line:
                    break
                print(f"[Game Log]: {line.strip()}")
            print("-----------------------------------------")
            
            if process.poll() is not None:
                print(f"Ошибка: процесс мгновенно завершился с кодом {process.returncode}")
                return None
            
            print(f"\nMinecraft успешно запущен (PID: {process.pid})")
            return process
            
        except Exception as e:
            print(f"\nОШИБКА ЗАПУСКА: {e}")
            traceback.print_exc()
            return None
    
    def check_java_installation(self):
        java_path = self.find_java()
        if java_path:
            return True, f"Java найдена: {java_path}"
        else:
            return False, "Java не найдена"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # Инициализация атрибутов
        self.download_thread = None
        self.forge_thread = None
        self.minecraft_process = None
        self.is_game_running = False
        self.drag_pos = None
        self.skin_menu = None
        self.game_timer = None

        self.trans = {
            "ru": {
                "mods": "ФАЙЛЫ",
                "play": "ИГРАТЬ",
                "launching": "ЗАПУСК...",
                "nickname": "Никнейм",
                "downloading": "ЗАГРУЗКА",
                "installing_forge": "FORGE",
                "download_error": "Ошибка скачивания",
                "download_success": "Скачивание завершено",
                "launch_error": "Ошибка запуска",
                "no_java": "Java не найдена!\nПожалуйста, установите Java 8 или проверьте папку runtime.",
                "forge_installed": "Forge успешно установлен!",
                "game_running": "ИГРА ЗАПУЩЕНА"
            },
            "uk": {
                "mods": "ФАЙЛИ",
                "play": "ГРАТИ",
                "launching": "ЗАПУСК...",
                "nickname": "Нікнейм",
                "downloading": "ЗАВАНТАЖ.",
                "installing_forge": "FORGE",
                "download_error": "Помилка завантаження",
                "download_success": "Завантаження завершено",
                "launch_error": "Помилка запуску",
                "no_java": "Java не знайдена!\nБудь ласка, встановіть Java 8 або перевірте папку runtime.",
                "forge_installed": "Forge успішно встановлено!",
                "game_running": "ГРА ЗАПУЩЕНА"
            }
        }

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(900, 600)

        self.base_dir = os.path.dirname(os.path.abspath(__file__))

        icon_path = os.path.join(self.base_dir, "assets", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.config = ConfigManager(self.base_dir)

        # Инициализация звукового менеджера
        self.sound_manager = SoundManager.instance()
        self.sound_manager.load_sounds(self.base_dir)
        self.sound_manager.load_bgm(self.base_dir)

        self.rpc = DiscordRPCManager("1355640634031214773")
        self.rpc.start()

        self._load_fonts()
        self.settings_panel = SettingsPanel(self) 
        self._build_ui()
        self._apply_rounded_corners()

        self.central.installEventFilter(self)

        self.update_localization()
        
        self.minecraft_launcher = MinecraftLauncher(self.base_dir, self.settings_panel)
        
        self.settings_panel.minecraft_dir_changed.connect(self.on_minecraft_dir_changed)
        
        # Запускаем фоновую музыку с задержкой
        QTimer.singleShot(500, self.sound_manager.start_bgm)

        QTimer.singleShot(100, lambda: self.update_tray_language())

    def update_tray_language(self):
        """Обновляет язык в трее"""
        if hasattr(self, 'tray_manager') and self.tray_manager:
            self.tray_manager.refresh_language()

    def _load_fonts(self):
        font_path = os.path.join(self.base_dir, "assets", "fonts", "AiW.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            launcher_family = families[0] if families else "Arial"
        else:
            launcher_family = "Arial"

        self.app_font_ru = QFont(launcher_family, 12)
        self.app_font_uk = QFont(launcher_family, 12)
        self.fallback_font_ru = QFont("Segoe UI", 11)
        self.fallback_font_uk = QFont("Segoe UI", 11)
        self.fallback_font_ru.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.fallback_font_uk.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.clean_font = QFont("Segoe UI", 11)

    def get_locale_font(self):
        lang = self.settings_panel.config.get("lang", "ru")
        return self.app_font_uk if lang == "uk" else self.app_font_ru

    def _apply_rounded_corners(self):
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 18, 18)
        self.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            if self.settings_panel.is_open:
                pos = event.position().toPoint()
                if not self.settings_panel.geometry().contains(pos):
                    self.settings_panel.close_panel()
                    self.sound_manager.play_popup()
                    return True
            
            if self.skin_menu and self.skin_menu.isVisible():
                pos = event.globalPosition().toPoint()
                if not self.skin_menu.geometry().contains(pos):
                    self.skin_menu.hide()
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 60:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_pos:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def closeEvent(self, event):
        """При закрытии окна сворачиваем в трей вместо выхода"""
        event.ignore()  # Отменяем стандартное закрытие
        self.hide()     # Прячем окно
    
        # Опционально: показываем уведомление от трея
        if hasattr(self, 'tray_manager') and self.tray_manager:
            self.tray_manager.show_notification(
                "Legion Nexus Launcher",
                "Лаунчер свёрнут в системный трей"
            )

    def build_skin_preview(self, skin_path):
        if not os.path.exists(skin_path):
            return

        skin = QPixmap(skin_path)
        result = QPixmap(200, 320)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, False)

        def draw(x, y, img):
            painter.drawPixmap(x, y, img)

        def copy(x, y, w, h):
            return skin.copy(x, y, w, h)

        def draw_part(x, y, base, overlay=None, size=(32, 96)):
            base_img = base.scaled(size[0], size[1], Qt.IgnoreAspectRatio, Qt.FastTransformation)
            draw(x, y, base_img)
            if overlay is not None and not overlay.isNull():
                overlay_img = overlay.scaled(size[0], size[1], Qt.IgnoreAspectRatio, Qt.FastTransformation)
                draw(x, y, overlay_img)

        # Рендеринг скина с полной поддержкой 2-х слоев (тело + одежда/шлем)
        draw_part(68, 20, copy(8, 8, 8, 8), copy(40, 8, 8, 8), (64, 64))
        draw_part(68, 84, copy(20, 20, 8, 12), copy(20, 36, 8, 12), (64, 96))
        draw_part(36, 84, copy(44, 20, 4, 12), copy(44, 36, 4, 12), (32, 96))
        draw_part(68, 180, copy(4, 20, 4, 12), copy(4, 36, 4, 12), (32, 96))
        draw_part(132, 84, copy(36, 52, 4, 12), copy(52, 52, 4, 12), (32, 96))
        draw_part(100, 180, copy(20, 52, 4, 12), copy(4, 52, 4, 12), (32, 96))

        painter.end()
        self.skin_label.setPixmap(result)

    def load_skin(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите скин", 
            "", 
            "Images (*.png *.jpg *.jpeg)"
        )
        
        if file_path:
            self.settings_panel.config["skin_path"] = file_path
            self.settings_panel._save_config()
            self.build_skin_preview(file_path)
            self.sound_manager.play_success()
            QMessageBox.information(self, "Успех", "Скин успешно загружен!")
    
    def load_cape(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, 
            "Выберите плащ", 
            "", 
            "Images (*.png)"
        )
        
        if file_path:
            self.settings_panel.config["cape_path"] = file_path
            self.settings_panel._save_config()
            
            capes_dir = os.path.join(self.base_dir, "assets", "capes")
            os.makedirs(capes_dir, exist_ok=True)
            
            cape_name = os.path.basename(file_path)
            dest_path = os.path.join(capes_dir, cape_name)
            shutil.copy2(file_path, dest_path)
            
            self.sound_manager.play_success()
            QMessageBox.information(self, "Успех", f"Плащ успешно загружен!\nПуть: {dest_path}")

    def _build_ui(self):
        self.central = QWidget(self)
        self.setCentralWidget(self.central)

        self.central.setStyleSheet("""
            QWidget {
                background-color: #0f0f0f;
                border-radius: 18px;
            }
        """)

        bg_path = os.path.join(self.base_dir, "assets", "background.png")
        self.bg = QLabel(self.central)
        if os.path.exists(bg_path):
            self.bg.setPixmap(QPixmap(bg_path))
            self.bg.setScaledContents(True)
        self.bg.setGeometry(0, 0, 900, 600)

        self.logo_label = QLabel(self.central)
        self.logo_label.setGeometry(400, 15, 100, 100)
        logo_path = os.path.join(self.base_dir, "assets", "logo.png")
        if os.path.exists(logo_path):
            self.logo_label.setPixmap(QPixmap(logo_path))
            self.logo_label.setScaledContents(True)
        self.logo_label.setAttribute(Qt.WA_TranslucentBackground)

        self.left_lines = QLabel(self.central)
        self.left_lines.setGeometry(265, 35, 120, 60)
        left_lines_path = os.path.join(self.base_dir, "assets", "left_lines.png")
        if os.path.exists(left_lines_path):
            self.left_lines.setPixmap(QPixmap(left_lines_path))
            self.left_lines.setScaledContents(True)
        self.left_lines.setAttribute(Qt.WA_TranslucentBackground)

        self.right_lines = QLabel(self.central)
        self.right_lines.setGeometry(515, 35, 120, 60)
        right_lines_path = os.path.join(self.base_dir, "assets", "right_lines.png")
        if os.path.exists(right_lines_path):
            self.right_lines.setPixmap(QPixmap(right_lines_path))
            self.right_lines.setScaledContents(True)
        self.right_lines.setAttribute(Qt.WA_TranslucentBackground)

        self.skin_label = QLabel(self.central)
        self.skin_label.setGeometry(50, 150, 200, 320)
        self.skin_label.setAttribute(Qt.WA_TranslucentBackground)

        saved_skin = self.settings_panel.config.get("skin_path", "")
        skin_path = saved_skin if saved_skin and os.path.exists(saved_skin) else os.path.join(self.base_dir, "assets", "skin.png")
        self.build_skin_preview(skin_path)

        nickname_container = QWidget(self.central)
        nickname_container.setGeometry(50, 450, 260, 40)
        nickname_container.setStyleSheet("background: transparent;")
        
        self.nickname_input = QLineEdit(nickname_container)
        self.nickname_input.setGeometry(0, 0, 200, 40)
        self.nickname_input.setFont(self.clean_font)
        self.nickname_input.setAlignment(Qt.AlignCenter)
        self.nickname_input.setStyleSheet("""
            QLineEdit {
                background-color: rgba(30, 30, 30, 50);
                color: #ffffff;
                border: none;
                border-bottom: 1px solid rgba(139, 0, 0, 180);
                padding: 8px 10px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-bottom: 1px solid #ff2222;
                background-color: rgba(35, 35, 35, 200);
            }
            QLineEdit::placeholder {
                color: #888888;
            }
        """)
        
        self.pencil_btn = SoundButton(nickname_container, sound_id="click")
        self.pencil_btn.setGeometry(210, 0, 35, 35)
        
        pencil_icon_path = os.path.join(self.base_dir, "assets", "pencil.png")
        if os.path.exists(pencil_icon_path):
            self.pencil_btn.setIcon(QIcon(pencil_icon_path))
            self.pencil_btn.setIconSize(QSize(20, 20))
        else:
            self.pencil_btn.setText("✎")
            self.pencil_btn.setFont(QFont("Segoe UI", 16))
        
        self.pencil_btn.setCursor(Qt.PointingHandCursor)
        self.pencil_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 0, 0, 100);
                border: none;
                border-radius: 4px;
                color: #ffffff;
            }
            QPushButton:hover {
                background-color: rgba(139, 0, 0, 180);
            }
            QPushButton:pressed {
                background-color: rgba(100, 0, 0, 200);
            }
        """)
        self.pencil_btn.clicked.connect(self.show_skin_menu)
        
        self.skin_menu = SkinMenu(self)
        
        saved_nickname = self.settings_panel.config.get("nickname", "")
        if saved_nickname:
            self.nickname_input.setText(saved_nickname)
        
        self.nickname_input.textChanged.connect(self.save_nickname)

        self.right_image = QLabel(self.central)
        self.right_image.setGeometry(500, 210, 320, 300)
        right_image_path = os.path.join(self.base_dir, "assets", "right_image.png")
        if os.path.exists(right_image_path):
            pixmap = QPixmap(right_image_path)
            scaled_pixmap = pixmap.scaled(250, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.right_image.setPixmap(scaled_pixmap)
            self.right_image.setScaledContents(True)
        else:
            self.right_image.setStyleSheet("""
                color: white; 
                background-color: rgba(50, 50, 50, 100); 
                border-radius: 10px;
                font-size: 16px;
            """)
            self.right_image.setAlignment(Qt.AlignCenter)
        self.right_image.setAttribute(Qt.WA_TranslucentBackground)

        self.mods_page = AddonsPage(self)
        self.mods_page.setGeometry(0, 0, 900, 600)
        self.mods_page.hide()

        self.top_controls = QWidget(self.central)
        self.top_controls.setGeometry(0, 0, 900, 100)
        self.top_controls.setStyleSheet("background: transparent;")

        self.min_btn = SoundButton("—", self.top_controls, sound_id="click")
        self.min_btn.setGeometry(810, 10, 35, 35)
        self.min_btn.setStyleSheet("""
            QPushButton {
                color: #aaaaaa;
                background: transparent;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: white;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        self.min_btn.clicked.connect(self.showMinimized)

        self.close_btn = SoundButton("✕", self.top_controls, sound_id="click")
        self.close_btn.setGeometry(850, 10, 35, 35)
        self.close_btn.setStyleSheet("""
            QPushButton {
                color: #aaaaaa;
                background: transparent;
                border: none;
                font-family: 'Arial';
                font-size: 14px;
            }
            QPushButton:hover {
                color: white;
                background: #e81123;
                border-radius: 4px;
            }
        """)
        self.close_btn.clicked.connect(self.close)

        self.settings_btn = SoundButton(self.top_controls, sound_id="click")
        self.settings_btn.setGeometry(770, 10, 35, 35)
        gear_icon_path = os.path.join(self.base_dir, "assets", "gear.png")
        if os.path.exists(gear_icon_path):
            self.settings_btn.setIcon(QIcon(gear_icon_path))
        else:
            self.settings_btn.setText("⚙")
            self.settings_btn.setFont(QFont("Segoe UI", 16))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.setCursor(Qt.PointingHandCursor)
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
        """)
        self.settings_btn.clicked.connect(self.open_settings)

        socials_data = [
            ("website.png", "https://твой_сайт.com"),
            ("discord.png", "https://discord.gg/твой_сервер"),
            ("telegram.png", "https://t.me/твой_канал"),
            ("youtube.png", "https://youtube.com/c/твой_канал"),
            ("twitch.png", "https://twitch.tv/твой_канал")
        ]

        start_x = 735 
        for i, (icon_file, url) in enumerate(socials_data):
            soc_btn = SoundButton(self.top_controls, sound_id="click")
            soc_btn.setGeometry(start_x + (i * 30), 50, 26, 26)
            icon_full_path = os.path.join(self.base_dir, "assets", icon_file)
            if os.path.exists(icon_full_path):
                soc_btn.setIcon(QIcon(icon_full_path))
            soc_btn.setIconSize(QSize(16, 16))
            soc_btn.setCursor(Qt.PointingHandCursor)
            soc_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: none;
                    opacity: 0.7;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.1);
                    border-radius: 4px;
                }
            """)
            soc_btn.clicked.connect(lambda checked=False, link=url: QDesktopServices.openUrl(QUrl(link)))

        self.bottom_bar = QWidget(self.central)
        self.bottom_bar.setGeometry(0, 510, 900, 70)
        self.bottom_bar.setStyleSheet("""
            QWidget {
                background-color: rgba(10, 10, 10, 220);
                border-top: 1px solid rgba(139, 0, 0, 180);
            }
        """)

        self.server_status = ServerStatusWidget(self.bottom_bar)
        self.server_status.setGeometry(30, 15, 300, 40)
        self.server_status.setAttribute(Qt.WA_TranslucentBackground)
        self.server_status.setStyleSheet("border: none; background: transparent;")
        self.server_status.start_status_check()

        self.progress = QProgressBar(self.bottom_bar)
        self.progress.setGeometry(295, 20, 300, 30)
        self.progress.hide()
        self.progress.setFont(self.clean_font)
        self.progress.setAlignment(Qt.AlignCenter)
        self.progress.setTextVisible(True)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #0a0a0a;
                border: 1px solid rgba(139, 0, 0, 100);
                border-radius: 6px;
                color: white;
                font-size: 11px;
                text-align: center;
                padding: 0px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #8b0000, stop:1 #ff2222);
                border-radius: 5px;
            }
        """)

        btn_style_mods = """
            QPushButton {
                background-color: rgba(20, 20, 20, 200);
                color: #e0e0e0;
                border: 1px solid rgba(139, 0, 0, 150);
                border-radius: 6px;
                font-size: 13px;
                letter-spacing: 2px;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #8b0000;
                color: white;
                border: 1px solid #ff2222;
            }
        """
        
        btn_style_play = """
            QPushButton {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #222, stop:1 #111);
                color: white;
                border: 1px solid #8b0000;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 2px;
                padding: 0px 5px;
            }
            QPushButton:hover {
                background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #aa0000, stop:1 #660000);
                border: 1px solid #ff2222;
            }
            QPushButton:pressed {
                background-color: #550000;
            }
            QPushButton:disabled {
                background-color: #333333;
                color: #888888;
                border: 1px solid #555555;
            }
        """

        self.mods_btn = SoundButton(self.top_controls, sound_id="click")
        self.mods_btn.setGeometry(24, 11, 130, 38)
        self.mods_btn.setStyleSheet(btn_style_mods)
        self.mods_btn.setCursor(Qt.PointingHandCursor)
        self.mods_btn.clicked.connect(self.open_mods_page)

        self.play_btn = SoundButton(self.bottom_bar, sound_id="click")
        self.play_btn.setGeometry(610, 15, 260, 40)
        self.play_btn.setStyleSheet(btn_style_play)
        self.play_btn.setCursor(Qt.PointingHandCursor)
        self.play_btn.clicked.connect(self.on_play)

        self.play_btn.raise_()
        self.progress.lower()

        self.bg.lower()
        self.logo_label.raise_()
        self.left_lines.raise_()
        self.right_lines.raise_()
        self.skin_label.raise_()
        nickname_container.raise_()
        self.right_image.raise_()
        self.top_controls.raise_()
        self.bottom_bar.raise_()
        self.settings_panel.setParent(self.central)
        self.settings_panel.raise_()
        
        if hasattr(self, 'mods_page') and hasattr(self.settings_panel, 'get_minecraft_path'):
            minecraft_path = self.settings_panel.get_minecraft_path()
            self.mods_page.set_minecraft_dir(minecraft_path)

    def open_settings(self):
        self.sound_manager.play_popup()
        self.settings_panel.toggle()

    def show_skin_menu(self):
        btn_pos = self.pencil_btn.mapToGlobal(QPoint(self.pencil_btn.width(), 0))
        self.skin_menu.show_at_position(btn_pos)

    def on_minecraft_dir_changed(self, new_path):
        if hasattr(self, 'mods_page'):
            self.mods_page.set_minecraft_dir(new_path)

    def save_nickname(self, nickname):
        self.settings_panel.config["nickname"] = nickname
        self.settings_panel._save_config()

    def update_localization(self):
        lang = self.settings_panel.config.get("lang", "ru")
        tr = self.trans.get(lang, self.trans["ru"])
        locale_font = self.get_locale_font()

        self.mods_btn.setFont(locale_font)
        self.play_btn.setFont(locale_font)
        self.mods_btn.setText(tr["mods"])
        
        if hasattr(self, 'nickname_input'):
            self.nickname_input.setPlaceholderText(tr["nickname"])

        if self.is_game_running:
            self.play_btn.setText(tr["game_running"])
        elif not self.progress.isVisible():
            self.play_btn.setText(tr["play"])
        else:
            self.play_btn.setText(tr["downloading"])

    def open_mods_page(self):
        self.sound_manager.play_popup()
        if hasattr(self, 'mods_page') and hasattr(self.settings_panel, 'get_minecraft_path'):
            minecraft_path = self.settings_panel.get_minecraft_path()
            self.mods_page.set_minecraft_dir(minecraft_path)
        
        self.bg.hide()
        self.top_controls.hide()
        self.bottom_bar.hide()
        self.mods_page.show()
        self.mods_page.raise_()

    def show_main_page(self):
        self.mods_page.hide()
        self.bg.show()
        self.top_controls.show()
        self.bottom_bar.show()
    
    def check_and_install_minecraft(self, nickname, memory, skin_path, skin_type, cape_path):
        minecraft_dir = self.minecraft_launcher.get_minecraft_dir()
        
        version_dir = os.path.join(minecraft_dir, "versions", "1.12.2")
        jar_path = os.path.join(version_dir, "1.12.2.jar")
        
        if not os.path.exists(jar_path):
            lang = self.settings_panel.config.get("lang", "ru")
            tr = self.trans.get(lang, self.trans["ru"])
            self.play_btn.setText(tr["downloading"])
            self.play_btn.setEnabled(False)
            self.progress.setValue(0)
            self.progress.show()
            
            self.sound_manager.play_download_start()
            
            self.download_thread = DownloadThread("1.12.2", minecraft_dir, self.base_dir)
            self.download_thread.progress.connect(self.update_progress)
            self.download_thread.status.connect(self.update_status)
            self.download_thread.finished.connect(
                lambda success, msg: self.on_minecraft_downloaded(success, msg, nickname, memory, skin_path, skin_type, cape_path)
            )
            self.download_thread.start()
        else:
            self.check_and_install_forge(nickname, memory, skin_path, skin_type, cape_path)
    
    def on_minecraft_downloaded(self, success, message, nickname, memory, skin_path, skin_type, cape_path):
        lang = self.settings_panel.config.get("lang", "ru")
        tr = self.trans.get(lang, self.trans["ru"])
        
        if success:
            self.sound_manager.play_download_complete()
            self.check_and_install_forge(nickname, memory, skin_path, skin_type, cape_path)
        else:
            self.sound_manager.play_error()
            self.progress.hide()
            QMessageBox.critical(self, tr["download_error"], message)
            self.play_btn.setText(tr["play"])
            self.play_btn.setEnabled(True)
    
    def check_and_install_forge(self, nickname, memory, skin_path, skin_type, cape_path):
        minecraft_dir = self.minecraft_launcher.get_minecraft_dir()
        
        versions_dir = os.path.join(minecraft_dir, "versions")
        has_forge = False
        
        if os.path.exists(versions_dir):
            for version in os.listdir(versions_dir):
                if "forge" in version.lower():
                    has_forge = True
                    break
        
        if not has_forge:
            lang = self.settings_panel.config.get("lang", "ru")
            tr = self.trans.get(lang, self.trans["ru"])
            
            self.play_btn.setText(tr["installing_forge"])
            self.play_btn.setEnabled(False)
            self.progress.setValue(0)
            self.progress.show()
            
            self.forge_thread = ForgeInstaller(minecraft_dir, self.base_dir)
            self.forge_thread.progress.connect(self.update_progress)
            self.forge_thread.status.connect(self.update_status)
            self.forge_thread.finished.connect(
                lambda success, msg: self.on_forge_installed(success, msg, nickname, memory, skin_path, skin_type, cape_path)
            )
            self.forge_thread.start()
        else:
            self.launch_minecraft(nickname, memory, skin_path, skin_type, cape_path)
    
    def on_forge_installed(self, success, message, nickname, memory, skin_path, skin_type, cape_path):
        self.progress.hide()
        
        if success:
            self.sound_manager.play_success()
            print(f"Forge установлен: {message}")
        else:
            self.sound_manager.play_error()
            print(f"Ошибка установки Forge: {message}")
        
        self.launch_minecraft(nickname, memory, skin_path, skin_type, cape_path)
    
    def update_status(self, status):
        if len(status) > 12:
            status = status[:10] + "..."
        self.play_btn.setText(status)
        
    def update_progress(self, value):
        self.progress.setValue(value)
        
    def on_play(self):
        if self.is_game_running:
            QMessageBox.warning(self, "Внимание", "Игра уже запущена!")
            return
        
        lang = self.settings_panel.config.get("lang", "ru")
        tr = self.trans.get(lang, self.trans["ru"])
        
        java_installed, java_msg = self.minecraft_launcher.check_java_installation()
        if not java_installed:
            self.sound_manager.play_error()
            QMessageBox.critical(self, tr["launch_error"], tr["no_java"] + f"\n\n{java_msg}")
            return
        
        nickname = self.nickname_input.text().strip()
        if not nickname:
            QMessageBox.warning(self, tr["launch_error"], "Введите никнейм!")
            return
        
        self.play_btn.setEnabled(False)
        
        memory = self.settings_panel.config.get("ram", 4) * 1024
        skin_path = self.settings_panel.config.get("skin_path", "")
        skin_type = self.settings_panel.config.get("skin_type", "DEFAULT")
        cape_path = self.settings_panel.config.get("cape_path", "")
        
        self.check_and_install_minecraft(nickname, memory, skin_path, skin_type, cape_path)
    
    def launch_minecraft(self, nickname, memory, skin_path, skin_type, cape_path):
        lang = self.settings_panel.config.get("lang", "ru")
        tr = self.trans.get(lang, self.trans["ru"])
        
        try:
            minecraft_dir = self.minecraft_launcher.get_minecraft_dir()
            
            self.minecraft_process = self.minecraft_launcher.launch(
                minecraft_dir, 
                nickname,
                memory=memory,
                skin_path=skin_path,
                skin_type=skin_type,
                cape_path=cape_path
            )
            
            if self.minecraft_process:
                self.sound_manager.play_launch()
                self.is_game_running = True
                self.showMinimized()
                
                self.play_btn.setText(tr["game_running"])
                self.play_btn.setEnabled(False)
                self.progress.hide()
                
                QTimer.singleShot(1000, self.check_game_process)
            else:
                self.sound_manager.play_error()
                QMessageBox.critical(self, tr["launch_error"], 
                    "Не удалось запустить Minecraft!\n\n"
                    "Возможные причины:\n"
                    "1. Не установлен Forge\n"
                    "2. Повреждены файлы Minecraft\n"
                    "3. Проблемы с Java")
                self.play_btn.setText(tr["play"])
                self.play_btn.setEnabled(True)
                self.is_game_running = False
                
        except Exception as e:
            self.sound_manager.play_error()
            QMessageBox.critical(self, tr["launch_error"], f"Ошибка запуска: {str(e)}")
            self.play_btn.setText(tr["play"])
            self.play_btn.setEnabled(True)
            self.is_game_running = False
        
    def check_game_process(self):
        if self.minecraft_process and self.minecraft_process.poll() is not None:
            self.showNormal()
            self.raise_()
            self.activateWindow()
            
            lang = self.settings_panel.config.get("lang", "ru")
            tr = self.trans.get(lang, self.trans["ru"])
            
            self.play_btn.setText(tr["play"])
            self.play_btn.setEnabled(True)
            self.is_game_running = False
            self.minecraft_process = None
        else:
            QTimer.singleShot(1000, self.check_game_process)