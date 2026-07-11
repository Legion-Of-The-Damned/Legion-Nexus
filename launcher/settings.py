import os
import json
import hashlib
import sys
import subprocess
import urllib.request
import ssl
import platform
import tempfile
import shutil
import time
from pathlib import Path
from threading import Thread

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QSlider, QFileDialog, QCheckBox, QLineEdit,
    QApplication, QProgressBar, QScrollArea, QVBoxLayout, QHBoxLayout
)
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QColor, QScreen
from PySide6.QtCore import Qt, QPropertyAnimation, QRect, QThread, Signal, QEvent, QTimer
from launcher.java_manager import JavaManager, JavaInstaller, AdminRightsDialog, JAVA_DIALOG_TRANSLATIONS


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def resource_path(relative_path):
    """Получает путь к ресурсу (работает и в EXE, и в разработке)"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def get_appdata_path():
    """Возвращает путь к папке приложения в AppData"""
    app_data = os.environ.get('APPDATA', '')
    if app_data:
        return os.path.join(app_data, 'LegionNexus')
    else:
        return os.path.dirname(sys.argv[0])


# ================= ПОТОК ОБНОВЛЕНИЯ ЛАУНЧЕРА =================
class LauncherUpdater(QThread):
    status_signal = Signal(str)
    progress_signal = Signal(int)
    update_ready = Signal(str)

    def __init__(self, current_version, repo_owner, repo_name):
        super().__init__()
        self.current_version = current_version.strip('v')
        self.repo_owner = repo_owner
        self.repo_name = repo_name

    def run(self):
        try:
            self.status_signal.emit("checking")
            url = f"https://api.github.com/repos/{self.repo_owner}/{self.repo_name}/releases/latest"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            context = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            latest_version = data.get("tag_name", "v1.0.0").strip('v')
            
            if self._compare_versions(latest_version, self.current_version) <= 0:
                self.status_signal.emit("up_to_date")
                return

            self.status_signal.emit("update_available")
            assets = data.get("assets", [])
            
            if not assets:
                self.status_signal.emit("error")
                return
            
            download_url = None
            file_name = None
            
            for asset in assets:
                name = asset["name"].lower()
                if platform.system().lower() == "windows" and name.endswith(".exe"):
                    download_url = asset["browser_download_url"]
                    file_name = asset["name"]
                    break
            
            if not download_url:
                download_url = assets[0]["browser_download_url"]
                file_name = assets[0]["name"]
            
            self.status_signal.emit("downloading")
            
            current_dir = os.path.dirname(sys.argv[0])
            update_dir = os.path.join(current_dir, "updates")
            os.makedirs(update_dir, exist_ok=True)
            
            output_path = os.path.join(update_dir, file_name)
            
            req_file = urllib.request.Request(download_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req_file, context=context) as dl_stream:
                total = int(dl_stream.info().get('Content-Length', 0))
                downloaded = 0
                
                with open(output_path, "wb") as f:
                    while True:
                        chunk = dl_stream.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int((downloaded / total) * 100)
                            self.progress_signal.emit(percent)
            
            self.update_ready.emit(output_path)
            
        except Exception as e:
            print(f"Ошибка обновления: {e}")
            self.status_signal.emit("error")
    
    def _compare_versions(self, v1, v2):
        try:
            v1_parts = [int(x) for x in v1.split('.')]
            v2_parts = [int(x) for x in v2.split('.')]
            
            for i in range(max(len(v1_parts), len(v2_parts))):
                a = v1_parts[i] if i < len(v1_parts) else 0
                b = v2_parts[i] if i < len(v2_parts) else 0
                if a > b:
                    return 1
                elif a < b:
                    return -1
            return 0
        except:
            return 0


# ================= ЗАГРУЗЧИК ИГРЫ =================
class GameDownloader(QThread):
    status_signal = Signal(str, int)

    def __init__(self, base_dir, manifest_path, download_base_url):
        super().__init__()
        self.base_dir = base_dir
        self.manifest_path = manifest_path
        self.download_base_url = download_base_url

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
        context = ssl._create_unverified_context()
        
        try:
            manifest_url = self.download_base_url + "launcher_manifest.json"
            req = urllib.request.Request(manifest_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=context) as response:
                manifest = json.loads(response.read().decode("utf-8"))
        except Exception as e:
            print(f"Манифест не найден: {e}")
            self.status_signal.emit("manifest_missing", 0)
            return
        
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=4, ensure_ascii=False)
        except:
            pass
        
        for folder in manifest.get("folders", []):
            os.makedirs(os.path.join(self.base_dir, folder), exist_ok=True)
        
        missing = []
        corrupted = []
        
        for file_path, expected_hash in manifest.get("files", {}).items():
            full_path = os.path.join(self.base_dir, file_path)
            
            if not os.path.isfile(full_path):
                missing.append(file_path)
            elif self._calculate_sha256(full_path) != expected_hash:
                corrupted.append(file_path)
        
        files_to_download = missing + corrupted
        
        if not files_to_download:
            self.status_signal.emit("launcher_ok", 0)
            return
        
        for idx, file_path in enumerate(files_to_download, 1):
            self.status_signal.emit("downloading_files", len(files_to_download) - idx + 1)
            
            full_path = os.path.join(self.base_dir, file_path)
            file_url = self.download_base_url + file_path.replace(" ", "%20")
            
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            try:
                req = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, context=context) as stream, open(full_path, "wb") as f:
                    f.write(stream.read())
            except Exception as e:
                print(f"Ошибка загрузки {file_path}: {e}")
                self.status_signal.emit("check_failed", 0)
                return
        
        self.status_signal.emit("launcher_ok", 0)


# ================= ПАНЕЛЬ НАСТРОЕК =================
class SettingsPanel(QWidget):
    minecraft_dir_changed = Signal(str)
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        
        self.config_dir = get_appdata_path()
        os.makedirs(self.config_dir, exist_ok=True)
        self.config_path = os.path.join(self.config_dir, "config.json")
        
        self.config = self._load_config()
        self.last_check_status = None
        self.missing_count = 0
        self.file_worker = None
        self.update_worker = None
        self.java_installer = None
        self.java_manager = JavaManager()
        
        self.CURRENT_VERSION = "1.0.0"
        self.REPO_OWNER = "Legion-Of-The-Damned"
        self.REPO_NAME = "Legion-Nexus"
        self.download_base_url = "https://raw.githubusercontent.com/Legion-Of-The-Damned/Legion-Nexus/main/"
        
        self.trans = {
            "ru": {
                "title": "НАСТРОЙКИ", "ram": "Выделение ОЗУ", "ram_value_gb": "ГБ",
                "ram_auto": "Auto (Java сама выбирает)", "res": "Разрешение",
                "fullscreen": "Полноэкранный режим", "lang": "Язык",
                "install_path": "Папка Minecraft", "select_folder": "...",
                "check_btn": "Проверить файлы игры", "checking": "Проверка...",
                "manifest_missing": "Манифест не найден", "launcher_ok": "Файлы в норме",
                "downloading_files": "Скачивание файлов: ", "check_failed": "Ошибка проверки",
                "update_btn": "Обновить лаунчер", "up_to_date": "Лаунчер обновлен",
                "update_err": "Ошибка обновления", "java_btn": "Установить Java 8",
                "java_installed": "Java 8 установлена", "java_not_installed": "Java 8 не найдена",
                "java_downloading": "Скачивание Java...", "java_installing": "Установка Java...",
                "java_success": "Java установлена", "java_error": "Ошибка установки",
                "java_already": "Java уже установлена"
            },
            "uk": {
                "title": "НАЛАШТУВАННЯ", "ram": "Виділення ОЗУ", "ram_value_gb": "ГБ",
                "ram_auto": "Auto (Java сама обирає)", "res": "Роздільна здатність",
                "fullscreen": "Повноекранний режим", "lang": "Мова",
                "install_path": "Папка Minecraft", "select_folder": "...",
                "check_btn": "Перевірити файли гри", "checking": "Перевірка...",
                "manifest_missing": "Маніфест не знайдено", "launcher_ok": "Файли у нормі",
                "downloading_files": "Завантаження файлів: ", "check_failed": "Помилка перевірки",
                "update_btn": "Оновити лаунчер", "up_to_date": "Лаунчер оновлено",
                "update_err": "Помилка оновлення", "java_btn": "Встановити Java 8",
                "java_installed": "Java 8 встановлена", "java_not_installed": "Java 8 не знайдено",
                "java_downloading": "Завантаження Java...", "java_installing": "Встановлення Java...",
                "java_success": "Java встановлено", "java_error": "Помилка встановлення",
                "java_already": "Java вже встановлена"
            }
        }
        
        self.setGeometry(900, 0, 300, 600)
        self.setAutoFillBackground(True)
        
        self.anim = None
        self.is_open = False
        
        self._init_ui()
        self._apply_config_to_ui()
        self.update_localization()
        self.check_java()
        
        QTimer.singleShot(3000, self.check_for_updates_auto)
    
    def _get_lang(self):
        """Возвращает текущий язык"""
        return self.config.get("lang", "ru")
    
    def _block_global_inputs(self, block):
        """Блокирует/разблокирует все поля ввода на главном окне"""
        if not self.main_window:
            return
        
        for widget in self.main_window.findChildren(QLineEdit):
            widget.setEnabled(not block)
            if block:
                widget.clearFocus()
        
        if hasattr(self, 'install_path_input'):
            self.install_path_input.setEnabled(not block)
            if block:
                self.install_path_input.clearFocus()
        
        for widget in self.main_window.findChildren(QComboBox):
            widget.setEnabled(not block)
        
        if block:
            if hasattr(self, 'close_btn'):
                self.close_btn.setFocus()
            else:
                self.setFocus()
        else:
            QTimer.singleShot(50, self._restore_focus)
    
    def _restore_focus(self):
        """Восстанавливает фокус на главном окне"""
        if self.main_window:
            self.main_window.setFocus()
            for widget in self.main_window.findChildren(QLineEdit):
                widget.clearFocus()
    
    def _get_screen_resolutions(self):
        """Возвращает список доступных разрешений с учётом монитора пользователя"""
        base_resolutions = [
            "800x600",
            "1024x768", 
            "1280x720",
            "1366x768",
            "1600x900",
            "1920x1080"
        ]
        
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                screen_width = screen_geometry.width()
                screen_height = screen_geometry.height()
                native_res = f"{screen_width}x{screen_height}"
                
                if native_res not in base_resolutions:
                    if screen_width <= 2560 and screen_height <= 1600:
                        base_resolutions.append(native_res)
                        base_resolutions.sort(key=lambda x: int(x.split('x')[0]))
        except Exception as e:
            print(f"Ошибка получения разрешения экрана: {e}")
        
        return base_resolutions
    
    def _init_ui(self):
        self._load_fonts()
        
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setGeometry(0, 0, 300, 600)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical { background: rgba(0,0,0,100); width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #8b0000; min-height: 30px; border-radius: 4px; }
            QScrollBar::handle:vertical:hover { background: #ff2222; }
        """)
        
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        self.scroll_widget = QWidget()
        self.scroll_widget.setStyleSheet("background: transparent;")
        self.scroll_area.setWidget(self.scroll_widget)
        
        self.scroll_area.viewport().installEventFilter(self)
        self.scroll_widget.installEventFilter(self)
        
        layout = QVBoxLayout(self.scroll_widget)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(15)
        
        # Заголовок
        title_layout = QHBoxLayout()
        self.title = QLabel()
        self.title.setFont(self.font_custom)
        self.title.setStyleSheet("color: white; font-size: 16px; letter-spacing: 1px;")
        
        self.close_btn = QPushButton("←")
        self.close_btn.setFixedSize(38, 38)
        self.close_btn.setFont(self.font_normal)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet("""
            QPushButton { color: #e0e0e0; background: rgba(20,20,20,220); border: 1px solid #8b0000; border-radius: 6px; font-size: 16px; font-weight: bold; }
            QPushButton:hover { background: #8b0000; color: white; border: 1px solid #ff2222; }
        """)
        self.close_btn.clicked.connect(self.close_panel)
        
        title_layout.addWidget(self.title)
        title_layout.addStretch()
        title_layout.addWidget(self.close_btn)
        layout.addLayout(title_layout)
        
        # RAM
        self.ram_label = QLabel()
        self.ram_label.setFont(self.font_custom)
        self.ram_label.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(self.ram_label)
        
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setMinimum(2)
        self.ram_slider.setMaximum(16)
        self.ram_slider.valueChanged.connect(self._save_ram)
        self.ram_slider.setStyleSheet(self._get_ram_slider_style())
        self.ram_slider.installEventFilter(self)
        layout.addWidget(self.ram_slider)
        
        self.ram_value = QLabel()
        self.ram_value.setFont(self.font_small)
        self.ram_value.setStyleSheet("color: #8c8c8c;")
        layout.addWidget(self.ram_value)
        
        self.auto_ram_checkbox = QCheckBox()
        self.auto_ram_checkbox.setFont(self.font_small)
        self.auto_ram_checkbox.toggled.connect(self._toggle_auto_ram)
        self.auto_ram_checkbox.setStyleSheet("""
            QCheckBox { color: #e0e0e0; spacing: 8px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #8b0000; border-radius: 3px; background: #0f0f0f; }
            QCheckBox::indicator:checked { background: #8b0000; }
            QCheckBox::indicator:hover { border: 1px solid #ff2222; }
        """)
        self.auto_ram_checkbox.installEventFilter(self)
        layout.addWidget(self.auto_ram_checkbox)
        
        # Resolution
        self.res_label = QLabel()
        self.res_label.setFont(self.font_custom)
        self.res_label.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(self.res_label)
        
        self.res_box = QComboBox()
        self.res_box.setFont(self.font_normal)
        self.res_box.addItems(self._get_screen_resolutions())
        self.res_box.currentTextChanged.connect(self._save_res)
        self.res_box.setStyleSheet(self._combobox_style())
        self.res_box.installEventFilter(self)
        layout.addWidget(self.res_box)
        
        # Fullscreen
        self.fullscreen_checkbox = QCheckBox()
        self.fullscreen_checkbox.setFont(self.font_custom)
        self.fullscreen_checkbox.toggled.connect(self._save_fullscreen)
        self.fullscreen_checkbox.setStyleSheet(self._checkbox_style())
        self.fullscreen_checkbox.installEventFilter(self)
        layout.addWidget(self.fullscreen_checkbox)
        
        # Minecraft path
        self.install_path_label = QLabel()
        self.install_path_label.setFont(self.font_custom)
        self.install_path_label.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(self.install_path_label)
        
        path_layout = QHBoxLayout()
        self.install_path_input = QLineEdit()
        self.install_path_input.setFont(self.font_normal)
        self.install_path_input.textChanged.connect(self._save_minecraft_path)
        self.install_path_input.setStyleSheet("""
            QLineEdit { background: #0f0f0f; color: #e0e0e0; border: 1px solid #8b0000; border-radius: 6px; padding: 8px; font-size: 12px; }
            QLineEdit:focus { border: 1px solid #ff2222; }
        """)
        self.install_path_input.installEventFilter(self)
        path_layout.addWidget(self.install_path_input)
        
        self.select_path_btn = QPushButton("...")
        self.select_path_btn.setFixedSize(40, 36)
        self.select_path_btn.setFont(self.font_bold)
        self.select_path_btn.clicked.connect(self._select_minecraft_folder)
        self.select_path_btn.setStyleSheet(self._button_style())
        self.select_path_btn.installEventFilter(self)
        path_layout.addWidget(self.select_path_btn)
        layout.addLayout(path_layout)
        
        # Language
        self.lang_label = QLabel()
        self.lang_label.setFont(self.font_custom)
        self.lang_label.setStyleSheet("color: white; font-size: 13px;")
        layout.addWidget(self.lang_label)
        
        self.lang_box = QComboBox()
        self.lang_box.setFont(self.font_custom)
        self.lang_box.addItems(["Русский", "Українська"])
        self.lang_box.currentIndexChanged.connect(self._save_lang)
        self.lang_box.setStyleSheet(self._combobox_style())
        self.lang_box.installEventFilter(self)
        layout.addWidget(self.lang_box)
        
        btn_style = self._button_style()
        
        self.check_btn = QPushButton()
        self.check_btn.setFont(self.font_custom)
        self.check_btn.clicked.connect(self.check_files)
        self.check_btn.setStyleSheet(btn_style)
        self.check_btn.installEventFilter(self)
        layout.addWidget(self.check_btn)
        
        self.update_btn = QPushButton()
        self.update_btn.setFont(self.font_custom)
        self.update_btn.clicked.connect(self.start_update)
        self.update_btn.setStyleSheet(btn_style)
        self.update_btn.installEventFilter(self)
        layout.addWidget(self.update_btn)
        
        self.java_btn = QPushButton()
        self.java_btn.setFont(self.font_custom)
        self.java_btn.clicked.connect(self.install_java)
        self.java_btn.setStyleSheet(btn_style)
        self.java_btn.installEventFilter(self)
        self.java_btn.setFocusPolicy(Qt.ClickFocus)
        layout.addWidget(self.java_btn)
        
        self.java_progress = QProgressBar()
        self.java_progress.setVisible(False)
        self.java_progress.setFixedHeight(10)
        self.java_progress.setStyleSheet("""
            QProgressBar { border: none; background: #1a1a1a; border-radius: 3px; }
            QProgressBar::chunk { background: #8b0000; border-radius: 3px; }
        """)
        self.java_progress.installEventFilter(self)
        layout.addWidget(self.java_progress)
        
        layout.addStretch()
    
    def _get_ram_slider_style(self):
        """Возвращает стиль для слайдера ОЗУ в зависимости от режима Auto"""
        is_auto = self.config.get("ram_auto", False)
        
        if is_auto:
            return """
                QSlider::groove:horizontal { height: 6px; background: #1a1a1a; border-radius: 3px; }
                QSlider::sub-page:horizontal { background: #3a3a3a; border-radius: 3px; }
                QSlider::handle:horizontal { background: #6a6a6a; width: 14px; margin: -4px 0; border-radius: 7px; }
                QSlider::handle:horizontal:hover { background: #8a8a8a; }
            """
        else:
            return """
                QSlider::groove:horizontal { height: 6px; background: #1a1a1a; border-radius: 3px; }
                QSlider::sub-page:horizontal { background: #8b0000; border-radius: 3px; }
                QSlider::handle:horizontal { background: white; width: 14px; margin: -4px 0; border-radius: 7px; }
                QSlider::handle:horizontal:hover { background: #ff2222; }
            """
    
    def _update_ram_slider_style(self):
        """Обновляет стиль слайдера ОЗУ"""
        self.ram_slider.setStyleSheet(self._get_ram_slider_style())
    
    def eventFilter(self, obj, event):
        """Перехватываем событие колесика мыши и передаём его скролл области"""
        if event.type() == QEvent.Wheel:
            self.scroll_area.wheelEvent(event)
            return True
        return super().eventFilter(obj, event)
    
    def wheelEvent(self, event):
        """Передаём событие прокрутки скролл области"""
        self.scroll_area.wheelEvent(event)
    
    def _load_fonts(self):
        font_path = resource_path(os.path.join("launcher", "assets", "fonts", "AiW.ttf"))
    
        if not os.path.exists(font_path):
            font_path = resource_path(os.path.join("assets", "fonts", "AiW.ttf"))
    
        if not os.path.exists(font_path):
            local_path = os.path.join(os.path.dirname(__file__), "assets", "fonts", "AiW.ttf")
            if os.path.exists(local_path):
                font_path = local_path
            else:
                local_path = os.path.join(os.path.dirname(__file__), "launcher", "assets", "fonts", "AiW.ttf")
                if os.path.exists(local_path):
                    font_path = local_path
    
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            custom_family = families[0] if families else "Arial"
        else:
            custom_family = "Arial"
    
        self.font_custom = QFont(custom_family, 12)
        self.font_custom.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
        self.font_normal = QFont("Segoe UI", 11)
        self.font_small = QFont("Segoe UI", 10)
        self.font_bold = QFont("Segoe UI", 11)
        self.font_bold.setBold(True)
        self.font_title = QFont(custom_family, 14)
        self.font_title.setBold(True)
        self.font_title.setLetterSpacing(QFont.AbsoluteSpacing, 1)
    
    def _load_config(self):
        default_minecraft_path = os.path.join(
            os.environ.get('APPDATA', ''), 
            '.legionnexus', 
            'Minecraft'
        )
        
        default_resolution = "1920x1080"
        try:
            screen = QApplication.primaryScreen()
            if screen:
                screen_geometry = screen.availableGeometry()
                default_resolution = f"{screen_geometry.width()}x{screen_geometry.height()}"
        except:
            pass
        
        default_config = {
            "ram_value": 4, 
            "ram_auto": False, 
            "resolution": default_resolution,
            "fullscreen": False, 
            "skin_path": "", 
            "skin_type": "DEFAULT",
            "lang": "ru", 
            "minecraft_path": default_minecraft_path
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    default_config.update(config)
            except Exception as e:
                print(f"Ошибка загрузки конфига: {e}")
        
        return default_config
    
    def _save_config(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
    
    def _button_style(self):
        return """
            QPushButton { background: #0f0f0f; color: #e0e0e0; border: 1px solid #8b0000; border-radius: 6px; padding: 8px; font-size: 13px; }
            QPushButton:hover { background: #8b0000; color: white; border: 1px solid #ff2222; }
            QPushButton:disabled { color: #555; border-color: #222; background: #0a0a0a; }
        """
    
    def _combobox_style(self):
        return """
            QComboBox { background: #0f0f0f; color: #e0e0e0; border: 1px solid #8b0000; border-radius: 6px; padding: 6px; font-size: 12px; }
            QComboBox:hover { border: 1px solid #ff2222; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #0f0f0f; color: #e0e0e0; border: 1px solid #8b0000; selection-background-color: #8b0000; }
        """
    
    def _checkbox_style(self):
        return """
            QCheckBox { color: #e0e0e0; spacing: 8px; font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #8b0000; border-radius: 3px; background: #0f0f0f; }
            QCheckBox::indicator:checked { background: #8b0000; }
            QCheckBox::indicator:hover { border: 1px solid #ff2222; }
        """
    
    def _save_ram(self, value):
        self.config["ram_value"] = value
        self._save_config()
        self._update_ram_display()
    
    def _toggle_auto_ram(self, checked):
        self.config["ram_auto"] = checked
        self.ram_slider.setEnabled(not checked)
        self._save_config()
        self._update_ram_display()
        self._update_ram_slider_style()
    
    def _save_res(self, value):
        self.config["resolution"] = value
        self._save_config()
    
    def _save_fullscreen(self, checked):
        self.config["fullscreen"] = checked
        self._save_config()
    
    def _save_lang(self, index):
        self.config["lang"] = "uk" if index == 1 else "ru"
        self._save_config()
        self.update_localization()
        if hasattr(self.main_window, "update_localization"):
            self.main_window.update_localization()

        if hasattr(self.main_window, 'tray_manager') and self.main_window.tray_manager:
            self.main_window.tray_manager.refresh_language()
    
    def _save_minecraft_path(self, text):
        old = self.config.get("minecraft_path", "")
        self.config["minecraft_path"] = text
        self._save_config()
        if old != text and text:
            self.minecraft_dir_changed.emit(text)
    
    def _select_minecraft_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку", self.install_path_input.text() or os.path.expanduser("~"))
        if folder:
            self.install_path_input.setText(folder)
    
    def _update_ram_display(self):
        lang = self._get_lang()
        if self.config.get("ram_auto", False):
            self.ram_value.setText(self.trans[lang]["ram_auto"])
            self.ram_value.setStyleSheet("color: #ff8888; font-size: 11px;")
        else:
            self.ram_value.setText(f"{self.config['ram_value']} {self.trans[lang]['ram_value_gb']}")
            self.ram_value.setStyleSheet("color: #8c8c8c; font-size: 11px;")
    
    def _apply_config_to_ui(self):
        self.ram_slider.setValue(self.config.get("ram_value", 4))
        self.ram_slider.setEnabled(not self.config.get("ram_auto", False))
        self.auto_ram_checkbox.setChecked(self.config.get("ram_auto", False))
        
        current_resolutions = [self.res_box.itemText(i) for i in range(self.res_box.count())]
        new_resolutions = self._get_screen_resolutions()
        
        if current_resolutions != new_resolutions:
            self.res_box.blockSignals(True)
            self.res_box.clear()
            self.res_box.addItems(new_resolutions)
            self.res_box.blockSignals(False)
        
        saved_resolution = self.config.get("resolution", "1920x1080")
        idx = self.res_box.findText(saved_resolution)
        
        if idx >= 0:
            self.res_box.setCurrentIndex(idx)
        else:
            if self.res_box.count() > 0:
                self.res_box.setCurrentIndex(self.res_box.count() - 1)
                self.config["resolution"] = self.res_box.currentText()
                self._save_config()
        
        self.fullscreen_checkbox.setChecked(self.config.get("fullscreen", False))
        self.install_path_input.setText(self.config.get("minecraft_path", ""))
        
        self._update_ram_display()
        self._update_ram_slider_style()
    
    def get_minecraft_path(self):
        return self.config.get("minecraft_path", os.path.join(os.environ.get('APPDATA', ''), '.legionnexus', 'Minecraft'))
    
    def get_java_path(self):
        paths = self.java_manager.get_java_paths()
        return paths[0] if paths else "java"
    
    def get_ram_argument(self):
        if self.config.get("ram_auto", False):
            return ""
        ram = self.config.get("ram_value", 4)
        if platform.system().lower() in ['linux', 'darwin'] and ram > 8:
            ram = 8
        return f"-Xms{ram}G -Xmx{ram}G"
    
    def check_java(self):
        installed = self.java_manager.is_java_installed()
        self._set_java_installed(installed)
        return installed
    
    def _set_java_installed(self, installed):
        lang = self._get_lang()
        if installed:
            self.java_btn.setText(self.trans[lang]["java_installed"])
            self.java_btn.setEnabled(False)
        else:
            self.java_btn.setText(self.trans[lang]["java_not_installed"])
            self.java_btn.setEnabled(True)
    
    def install_java(self):
        """Запускает установку Java через JavaManager"""
        if self.java_installer and self.java_installer.isRunning():
            return
        
        lang = self._get_lang()
        tr = JAVA_DIALOG_TRANSLATIONS.get(lang, JAVA_DIALOG_TRANSLATIONS["ru"])
        
        # Проверяем, установлена ли Java
        if self.check_java():
            self._block_global_inputs(True)
            AdminRightsDialog.ask(
                self.main_window,
                title=tr["title_already"],
                message=tr["message_already"],
                btn_yes=tr["btn_yes"],
                btn_no=tr["btn_no"]
            )
            self._block_global_inputs(False)
            return
        
        # Диалог подтверждения установки
        self._block_global_inputs(True)
        reply = AdminRightsDialog.ask(
            self.main_window,
            title=tr["title_confirm"],
            message=tr["message_confirm"],
            btn_yes=tr["btn_yes"],
            btn_no=tr["btn_no"]
        )
        self._block_global_inputs(False)
        
        if not reply:
            return
        
        # Проверяем права администратора
        if self.java_manager.need_admin_for_install():
            self._block_global_inputs(True)
            reply_admin = AdminRightsDialog.ask(
                self.main_window,
                title=tr["title_admin"],
                message=tr["message_admin"],
                btn_yes=tr["btn_yes"],
                btn_no=tr["btn_no"]
            )
            self._block_global_inputs(False)
            if not reply_admin:
                return
        
        # Запускаем установку
        self.java_btn.setEnabled(False)
        self.java_progress.setVisible(True)
        self.java_progress.setValue(0)
        
        self.java_installer = JavaInstaller()
        self.java_installer.status_signal.connect(self._on_java_status)
        self.java_installer.progress_signal.connect(self.java_progress.setValue)
        self.java_installer.start()
    
    def _on_java_status(self, status):
        """Обработка статуса установки Java"""
        lang = self._get_lang()
        tr = self.trans[lang]
        dialog_tr = JAVA_DIALOG_TRANSLATIONS.get(lang, JAVA_DIALOG_TRANSLATIONS["ru"])
        
        status_map = {
            "downloading": (tr["java_downloading"], True),
            "installing": (tr["java_installing"], True),
            "already_installed": (tr["java_installed"], False),
            "success": (tr["java_success"], False),
            "error": (tr["java_error"], True),
            "need_admin": (dialog_tr["title_need_admin"], True)
        }
        
        text, enable = status_map.get(status, (tr["java_error"], True))
        self.java_btn.setText(text)
        
        if status in ["already_installed", "success"]:
            self.java_progress.setVisible(False)
            self.java_btn.setEnabled(False)
            if status == "success":
                self._block_global_inputs(True)
                AdminRightsDialog.ask(
                    self.main_window,
                    title=dialog_tr["title_success"],
                    message=dialog_tr["message_success"],
                    btn_yes=dialog_tr["btn_yes"],
                    btn_no=dialog_tr["btn_no"]
                )
                self._block_global_inputs(False)
        elif status == "need_admin":
            self.java_progress.setVisible(False)
            self.java_btn.setEnabled(True)
            self._block_global_inputs(True)
            AdminRightsDialog.ask(
                self.main_window,
                title=dialog_tr["title_need_admin"],
                message=dialog_tr["message_need_admin"],
                btn_yes=dialog_tr["btn_yes"],
                btn_no=dialog_tr["btn_no"]
            )
            self._block_global_inputs(False)
        elif status == "error":
            self.java_progress.setVisible(False)
            self.java_btn.setEnabled(True)
            self._block_global_inputs(True)
            AdminRightsDialog.ask(
                self.main_window,
                title=dialog_tr["title_error"],
                message=dialog_tr["message_error"],
                btn_yes=dialog_tr["btn_yes"],
                btn_no=dialog_tr["btn_no"]
            )
            self._block_global_inputs(False)
        else:
            self.java_btn.setEnabled(not enable)
    
    def check_files(self):
        if self.file_worker and self.file_worker.isRunning():
            return
        
        self.last_check_status = "checking"
        self.update_localization()
        
        self.file_worker = GameDownloader(
            self.get_minecraft_path(),
            os.path.join(self.get_minecraft_path(), "launcher_manifest.json"),
            self.download_base_url
        )
        self.file_worker.status_signal.connect(self._on_game_check)
        self.file_worker.start()
    
    def _on_game_check(self, status, count):
        self.last_check_status = status
        self.missing_count = count
        self.update_localization()
        
        if status in ["launcher_ok", "check_failed", "manifest_missing"] and self.file_worker:
            self.file_worker.deleteLater()
            self.file_worker = None
    
    def check_for_updates_auto(self):
        def check():
            try:
                url = f"https://api.github.com/repos/{self.REPO_OWNER}/{self.REPO_NAME}/releases/latest"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                context = ssl._create_unverified_context()
                
                with urllib.request.urlopen(req, context=context, timeout=10) as response:
                    data = json.loads(response.read().decode("utf-8"))
                
                latest_version = data.get("tag_name", "v1.0.0").strip('v')
                
                if self._compare_versions(latest_version, self.CURRENT_VERSION) > 0:
                    QTimer.singleShot(0, lambda: self._ask_for_update(latest_version))
            except Exception as e:
                print(f"Ошибка проверки обновлений: {e}")
        
        Thread(target=check, daemon=True).start()
    
    def _compare_versions(self, v1, v2):
        try:
            v1_parts = [int(x) for x in v1.split('.')]
            v2_parts = [int(x) for x in v2.split('.')]
            
            for i in range(max(len(v1_parts), len(v2_parts))):
                a = v1_parts[i] if i < len(v1_parts) else 0
                b = v2_parts[i] if i < len(v2_parts) else 0
                if a > b:
                    return 1
                elif a < b:
                    return -1
            return 0
        except:
            return 0
    
    def _ask_for_update(self, new_version):
        lang = self._get_lang()
        tr = JAVA_DIALOG_TRANSLATIONS.get(lang, JAVA_DIALOG_TRANSLATIONS["ru"])
        
        self._block_global_inputs(True)
        reply = AdminRightsDialog.ask(
            self.main_window,
            title="Доступно обновление",
            message=f"Доступна новая версия лаунчера {new_version}!\n\nОбновить сейчас?",
            btn_yes=tr["btn_yes"],
            btn_no=tr["btn_no"]
        )
        self._block_global_inputs(False)
        
        if reply:
            self.start_update()
    
    def start_update(self):
        if self.update_worker and self.update_worker.isRunning():
            return
        
        self.update_btn.setEnabled(False)
        self.update_worker = LauncherUpdater(self.CURRENT_VERSION, self.REPO_OWNER, self.REPO_NAME)
        self.update_worker.status_signal.connect(self._on_update_status)
        self.update_worker.progress_signal.connect(self._on_update_progress)
        self.update_worker.update_ready.connect(self._on_update_ready)
        self.update_worker.start()
    
    def _on_update_status(self, status):
        lang = self._get_lang()
        tr = self.trans[lang]
        
        if status == "checking":
            self.update_btn.setText(tr["checking"])
        elif status == "up_to_date":
            self.update_btn.setText(tr["up_to_date"])
            self.update_btn.setEnabled(True)
        elif status == "update_available":
            self.update_btn.setText("Обновление найдено!")
        elif status == "error":
            self.update_btn.setText(tr["update_err"])
            self.update_btn.setEnabled(True)
    
    def _on_update_progress(self, percent):
        self.update_btn.setText(f"Загрузка: {percent}%")
    
    def _on_update_ready(self, new_file_path):
        current_exe = sys.argv[0]
        current_dir = os.path.dirname(current_exe)
        
        if not os.path.exists(new_file_path):
            print(f"Ошибка: файл обновления не найден: {new_file_path}")
            self.update_btn.setEnabled(True)
            return
        
        system = platform.system().lower()
        
        if system == "windows":
            script_path = os.path.join(current_dir, "update_launcher.ps1")
            
            new_file_esc = new_file_path.replace("'", "''")
            current_exe_esc = current_exe.replace("'", "''")
            
            ps_script = f'''# Скрипт автообновления лаунчера
$ErrorActionPreference = "Stop"
$newFile = '{new_file_esc}'
$currentExe = '{current_exe_esc}'

Write-Host "=== НАЧАЛО ОБНОВЛЕНИЯ ЛАУНЧЕРА ==="
Start-Sleep -Seconds 2

$processName = [System.IO.Path]::GetFileNameWithoutExtension($currentExe)
$processes = Get-Process -Name $processName -ErrorAction SilentlyContinue
if ($processes) {{
    $processes | ForEach-Object {{ 
        try {{ 
            $_.Kill() 
            $_.WaitForExit(2000)
        }} catch {{ }}
    }}
    Start-Sleep -Seconds 1
}}

$backupFile = "$currentExe.backup"
if (Test-Path $backupFile) {{ Remove-Item $backupFile -Force }}
if (Test-Path $currentExe) {{
    Move-Item $currentExe $backupFile -Force
}}

try {{
    Copy-Item $newFile $currentExe -Force
}} catch {{
    if (Test-Path $backupFile) {{
        Move-Item $backupFile $currentExe -Force
    }}
    exit 1
}}

Remove-Item $backupFile -Force -ErrorAction SilentlyContinue
Remove-Item $newFile -Force -ErrorAction SilentlyContinue
Start-Process -FilePath $currentExe -WorkingDirectory (Split-Path $currentExe -Parent)
Start-Sleep -Seconds 2
Remove-Item $MyInvocation.MyCommand.Path -Force
'''
            with open(script_path, "w", encoding='utf-8-sig') as f:
                f.write(ps_script)
            
            subprocess.Popen([
                "powershell.exe",
                "-ExecutionPolicy", "Bypass",
                "-WindowStyle", "Hidden",
                "-File", script_path
            ], creationflags=subprocess.CREATE_NO_WINDOW)
            
        else:
            script_path = os.path.join(current_dir, "update_launcher.sh")
            
            sh_script = f'''#!/bin/bash
sleep 2
PROCESS_NAME=$(basename "{current_exe}")
pkill -f "$PROCESS_NAME" 2>/dev/null
sleep 1
if [ -f "{current_exe}" ]; then
    mv "{current_exe}" "{current_exe}.backup"
fi
cp "{new_file_path}" "{current_exe}"
chmod +x "{current_exe}"
rm -f "{current_exe}.backup"
rm -f "{new_file_path}"
"{current_exe}" &
rm -f "$0"
'''
            with open(script_path, "w") as f:
                f.write(sh_script)
            
            os.chmod(script_path, 0o755)
            subprocess.Popen(["bash", script_path])
        
        self.main_window.close()
        QApplication.quit()
    
    def update_localization(self):
        lang = self._get_lang()
        tr = self.trans[lang]
        
        self.title.setText(tr["title"])
        self.ram_label.setText(tr["ram"])
        self.res_label.setText(tr["res"])
        self.fullscreen_checkbox.setText(tr["fullscreen"])
        self.install_path_label.setText(tr["install_path"])
        self.select_path_btn.setText(tr["select_folder"])
        self.lang_label.setText(tr["lang"])
        self.update_btn.setText(tr["update_btn"])
        self.auto_ram_checkbox.setText(tr["ram_auto"])
        
        status_text = {
            "downloading_files": f"{tr['downloading_files']}{self.missing_count}",
            "checking": tr["checking"],
            "launcher_ok": tr["launcher_ok"],
            "manifest_missing": tr["manifest_missing"],
            "check_failed": tr["check_failed"]
        }.get(self.last_check_status, tr["check_btn"])
        
        self.check_btn.setText(status_text)
        
        self.lang_box.blockSignals(True)
        self.lang_box.setCurrentIndex(1 if lang == "uk" else 0)
        self.lang_box.blockSignals(False)
        
        self._update_ram_display()
        self._set_java_installed(self.check_java())
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 225))
    
    def open_panel(self):
        if self.is_open:
            return
        self.raise_()
        self.is_open = True
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(250)
        self.anim.setStartValue(QRect(900, 0, 300, 600))
        self.anim.setEndValue(QRect(600, 0, 300, 600))
        self.anim.start()
    
    def close_panel(self):
        if not self.is_open:
            return
        self.is_open = False
        self.anim = QPropertyAnimation(self, b"geometry")
        self.anim.setDuration(200)
        self.anim.setStartValue(self.geometry())
        self.anim.setEndValue(QRect(900, 0, 300, 600))
        self.anim.start()
    
    def toggle(self):
        self.close_panel() if self.is_open else self.open_panel()