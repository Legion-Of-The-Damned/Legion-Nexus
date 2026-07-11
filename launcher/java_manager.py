import os
import sys
import platform
import subprocess
import urllib.request
import ssl
import tempfile
import shutil
import ctypes
import winreg
from pathlib import Path
import time

from PySide6.QtCore import QThread, Signal, Qt, QPropertyAnimation
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QLineEdit
from PySide6.QtGui import QFont, QFontDatabase, QPainter, QColor, QBrush, QPen, QPixmap


# ================= ПЕРЕВОДЫ ДЛЯ ДИАЛОГОВ =================
JAVA_DIALOG_TRANSLATIONS = {
    "ru": {
        "title_admin": "Требуются права администратора",
        "message_admin": "Для установки Java необходимы права администратора.\n\nПродолжить?",
        "title_already": "Java уже установлена",
        "message_already": "Java 8 уже установлена в системе.\n\nЗапуск игры не требует дополнительных действий.",
        "title_confirm": "Подтверждение установки",
        "message_confirm": "Будет установлена Java 8.\n\nУстановка будет выполнена в:\nC:\\Program Files\\Eclipse Adoptium\n\nПродолжить?",
        "title_success": "Установка завершена",
        "message_success": "Java 8 успешно установлена!",
        "title_error": "Ошибка установки",
        "message_error": "Не удалось установить Java.\n\nВозможные причины:\n• Нет подключения к интернету\n• Недостаточно места на диске\n• Антивирус блокирует установку",
        "title_need_admin": "Требуются права администратора",
        "message_need_admin": "Для установки Java 8 требуются права администратора.\n\nПожалуйста, перезапустите лаунчер от имени администратора и повторите установку.",
        "btn_yes": "ДА",
        "btn_no": "НЕТ"
    },
    "uk": {
        "title_admin": "Потрібні права адміністратора",
        "message_admin": "Для встановлення Java потрібні права адміністратора.\n\nПродовжити?",
        "title_already": "Java вже встановлена",
        "message_already": "Java 8 вже встановлена в системі.\n\nЗапуск гри не потребує додаткових дій.",
        "title_confirm": "Підтвердження встановлення",
        "message_confirm": "Буде встановлено Java 8.\n\nВстановлення буде виконано в:\nC:\\Program Files\\Eclipse Adoptium\n\nПродовжити?",
        "title_success": "Встановлення завершено",
        "message_success": "Java 8 успішно встановлена!",
        "title_error": "Помилка встановлення",
        "message_error": "Не вдалося встановити Java.\n\nМожливі причини:\n• Немає підключення до інтернету\n• Недостатньо місця на диску\n• Антивірус блокує встановлення",
        "title_need_admin": "Потрібні права адміністратора",
        "message_need_admin": "Для встановлення Java 8 потрібні права адміністратора.\n\nБудь ласка, перезапустіть лаунчер від імені адміністратора та повторіть встановлення.",
        "btn_yes": "ТАК",
        "btn_no": "НІ"
    }
}


# ================= УТИЛИТА ДЛЯ ЗАГРУЗКИ КАСТОМНЫХ ШРИФТОВ =================
class FontManager:
    """Класс для управления кастомными шрифтами"""
    
    _instance = None
    _loaded_fonts = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loaded_fonts = {}
    
    def load_font(self, font_path, font_id=None):
        """
        Загружает шрифт из файла
        
        Args:
            font_path: путь к файлу шрифта (.ttf, .otf)
            font_id: идентификатор шрифта (если None, используется имя файла)
        
        Returns:
            имя семейства шрифта или None в случае ошибки
        """
        if not os.path.exists(font_path):
            print(f"[FontManager] Шрифт не найден: {font_path}")
            return None
        
        try:
            font_id = font_id or os.path.splitext(os.path.basename(font_path))[0]
            
            # Проверяем, не загружен ли уже шрифт
            if font_id in self._loaded_fonts:
                return self._loaded_fonts[font_id]
            
            # Загружаем шрифт
            font_db_id = QFontDatabase.addApplicationFont(font_path)
            
            if font_db_id == -1:
                print(f"[FontManager] Не удалось загрузить шрифт: {font_path}")
                return None
            
            families = QFontDatabase.applicationFontFamilies(font_db_id)
            if families:
                family_name = families[0]
                self._loaded_fonts[font_id] = family_name
                print(f"[FontManager] Шрифт загружен: {family_name} из {font_path}")
                return family_name
            
        except Exception as e:
            print(f"[FontManager] Ошибка загрузки шрифта: {e}")
        
        return None
    
    def load_fonts_from_dir(self, fonts_dir, extensions=None):
        """
        Загружает все шрифты из директории
        
        Args:
            fonts_dir: путь к папке со шрифтами
            extensions: список расширений (по умолчанию ['.ttf', '.otf'])
        
        Returns:
            словарь загруженных шрифтов {имя_файла: имя_семейства}
        """
        if extensions is None:
            extensions = ['.ttf', '.otf', '.TTF', '.OTF']
        
        loaded = {}
        
        if not os.path.exists(fonts_dir):
            print(f"[FontManager] Директория не найдена: {fonts_dir}")
            return loaded
        
        for filename in os.listdir(fonts_dir):
            if any(filename.endswith(ext) for ext in extensions):
                font_path = os.path.join(fonts_dir, filename)
                family = self.load_font(font_path, filename)
                if family:
                    loaded[filename] = family
        
        return loaded
    
    def get_font(self, font_id, size=12, weight=QFont.Normal, italic=False):
        """
        Возвращает QFont для загруженного шрифта
        
        Args:
            font_id: идентификатор шрифта (имя файла или кастомный ID)
            size: размер шрифта
            weight: насыщенность (QFont.Normal, QFont.Bold и т.д.)
            italic: курсив
        
        Returns:
            QFont объект
        """
        family = self._loaded_fonts.get(font_id, "Arial")
        font = QFont(family, size)
        font.setWeight(weight)
        font.setItalic(italic)
        return font
    
    def get_available_fonts(self):
        """Возвращает список загруженных шрифтов"""
        return self._loaded_fonts.copy()
    
    @staticmethod
    def get_system_font_families():
        """Возвращает список всех системных шрифтов"""
        return QFontDatabase.families()


# ================= КРАСИВЫЙ ДИАЛОГ =================
class AdminRightsDialog(QDialog):
    """Красивый диалог в стиле лаунчера"""
    
    def __init__(self, parent=None, title="Подтверждение", 
                 message="Продолжить?",
                 btn_yes="ДА", btn_no="НЕТ"):
        super().__init__(parent)
        
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(450, 280)
        
        self.title_text = title
        self.message_text = message
        self.btn_yes_text = btn_yes
        self.btn_no_text = btn_no
        
        self.font_manager = FontManager()
        self._load_fonts(parent)
        self._init_ui()
        
        # Анимация появления
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.start()
    
    def _load_fonts(self, parent):
        """Загружает шрифты в стиле лаунчера"""
        custom_font = "Arial"
        
        font_paths = []
        
        if parent and hasattr(parent, "base_dir"):
            font_paths.append(os.path.join(parent.base_dir, "assets", "fonts", "AiW.ttf"))
            font_paths.append(os.path.join(parent.base_dir, "launcher", "assets", "fonts", "AiW.ttf"))
        
        current_dir = os.path.dirname(os.path.abspath(__file__))
        font_paths.append(os.path.join(current_dir, "assets", "fonts", "AiW.ttf"))
        font_paths.append(os.path.join(current_dir, "launcher", "assets", "fonts", "AiW.ttf"))
        font_paths.append(os.path.join(current_dir, "..", "assets", "fonts", "AiW.ttf"))
        font_paths.append(os.path.join(current_dir, "..", "launcher", "assets", "fonts", "AiW.ttf"))
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                family = self.font_manager.load_font(font_path, "AiW")
                if family:
                    custom_font = family
                    break
        
        self.font_title = QFont(custom_font, 16)
        self.font_title.setBold(True)
        self.font_title.setLetterSpacing(QFont.AbsoluteSpacing, 1)
        
        self.font_message = QFont(custom_font, 11)
        self.font_message.setLetterSpacing(QFont.AbsoluteSpacing, 0.3)
        
        self.font_button = QFont(custom_font, 12)
        self.font_button.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    
    def _init_ui(self):
        from PySide6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QPolygon
        from PySide6.QtCore import QPoint
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(20)
        
        # Заголовок
        self.title_label = QLabel(self.title_text)
        self.title_label.setFont(self.font_title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self.title_label)
        
        # Иконка
        icon_layout = QHBoxLayout()
        icon_layout.setAlignment(Qt.AlignCenter)
        
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(48, 48)
        self.icon_label.setStyleSheet("""
            QLabel {
                background-color: rgba(139, 0, 0, 30);
                border-radius: 24px;
            }
        """)
        
        pixmap = QPixmap(48, 48)
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setPen(QPen(QColor(139, 0, 0, 200), 2))
        painter.setBrush(QBrush(QColor(139, 0, 0, 100)))
        
        polygon = QPolygon()
        polygon.append(QPoint(24, 5))
        polygon.append(QPoint(40, 8))
        polygon.append(QPoint(42, 20))
        polygon.append(QPoint(24, 43))
        polygon.append(QPoint(6, 20))
        polygon.append(QPoint(8, 8))
        
        painter.drawPolygon(polygon)
        
        painter.setPen(QPen(QColor(255, 255, 255, 220), 3))
        painter.drawLine(18, 24, 24, 30)
        painter.drawLine(24, 30, 34, 18)
        
        painter.end()
        
        self.icon_label.setPixmap(pixmap)
        icon_layout.addWidget(self.icon_label)
        layout.addLayout(icon_layout)
        
        # Сообщение
        self.message_label = QLabel(self.message_text)
        self.message_label.setFont(self.font_message)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("color: #c0c0c0; background: transparent;")
        layout.addWidget(self.message_label)
        
        layout.addStretch()
        
        # Кнопки
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(15)
        
        self.no_btn = QPushButton(self.btn_no_text)
        self.no_btn.setFont(self.font_button)
        self.no_btn.setCursor(Qt.PointingHandCursor)
        self.no_btn.setFixedHeight(42)
        self.no_btn.clicked.connect(self.reject)
        self.no_btn.setFocusPolicy(Qt.ClickFocus)
        self.no_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(30, 30, 30, 200);
                color: #a0a0a0;
                border: 1px solid rgba(139, 0, 0, 100);
                border-radius: 6px;
                font-size: 13px;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background-color: rgba(50, 50, 50, 220);
                border: 1px solid rgba(139, 0, 0, 180);
                color: #e0e0e0;
            }
            QPushButton:pressed {
                background-color: rgba(20, 20, 20, 200);
            }
        """)
        
        self.yes_btn = QPushButton(self.btn_yes_text)
        self.yes_btn.setFont(self.font_button)
        self.yes_btn.setCursor(Qt.PointingHandCursor)
        self.yes_btn.setFixedHeight(42)
        self.yes_btn.clicked.connect(self.accept)
        self.yes_btn.setFocusPolicy(Qt.ClickFocus)
        self.yes_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(139, 0, 0, 180);
                color: #ffffff;
                border: 1px solid rgba(255, 34, 34, 100);
                border-radius: 6px;
                font-size: 13px;
                letter-spacing: 2px;
            }
            QPushButton:hover {
                background-color: #8b0000;
                border: 1px solid #ff2222;
            }
            QPushButton:pressed {
                background-color: rgba(100, 0, 0, 200);
            }
        """)
        
        buttons_layout.addWidget(self.no_btn)
        buttons_layout.addWidget(self.yes_btn)
        layout.addLayout(buttons_layout)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        painter.setBrush(QBrush(QColor(0, 0, 0, 235)))
        painter.setPen(QPen(QColor(139, 0, 0, 160), 2))
        painter.drawRoundedRect(self.rect(), 12, 12)
        
        painter.setPen(QPen(QColor(139, 0, 0, 200), 1))
        painter.drawLine(10, 50, self.width() - 10, 50)
        painter.end()
    
    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)
    
    @staticmethod
    def ask(parent=None, title="Подтверждение", message="Продолжить?",
            btn_yes="ДА", btn_no="НЕТ"):
        dialog = AdminRightsDialog(parent, title, message, btn_yes, btn_no)
        return dialog.exec() == QDialog.Accepted


# ================= УПРАВЛЕНИЕ JAVA =================
class JavaManager:
    """Класс для управления Java (проверка, установка, пути)"""
    
    def __init__(self):
        self.system = platform.system().lower()
        
        self.installer_urls = {
            'windows': "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u442-b06/OpenJDK8U-jre_x64_windows_hotspot_8u442b06.msi",
            'windows_x86': "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u442-b06/OpenJDK8U-jre_x86-32_windows_hotspot_8u442b06.msi",
            'linux': "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u442-b06/OpenJDK8U-jre_x64_linux_hotspot_8u442b06.tar.gz",
            'darwin': "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u442-b06/OpenJDK8U-jre_x64_mac_hotspot_8u442b06.pkg"
        }
        
        self.install_paths = {
            'windows': [
                Path("C:/Program Files/Eclipse Adoptium/jre-8.0.442.6-hotspot/bin/java.exe"),
                Path("C:/Program Files/Eclipse Adoptium/jre-8.0.442.6-hotspot"),
                Path("C:/Program Files/Java/jre8/bin/java.exe"),
                Path("C:/Program Files/Java/jre1.8.0/bin/java.exe")
            ],
            'darwin': [
                Path("/Library/Java/JavaVirtualMachines/temurin-8.jre/Contents/Home/bin/java"),
                Path("/Library/Java/JavaVirtualMachines/jdk8.jre/Contents/Home/bin/java")
            ],
            'linux': [
                Path("/usr/lib/jvm/temurin-8-jre/bin/java"),
                Path("/usr/lib/jvm/jre-8-openjdk/bin/java")
            ]
        }
    
    def is_java_installed(self):
        """Проверяет, установлена ли Java 8"""
        try:
            java_cmd = 'java' if self.system != 'windows' else 'java.exe'
            result = subprocess.run([java_cmd, '-version'], 
                                  capture_output=True, text=True, timeout=5, shell=True)
            if result.returncode == 0 and ('1.8' in result.stderr or 'openjdk version "1.8' in result.stderr):
                return True
        except:
            pass
        
        if self.system == 'windows':
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                    r"SOFTWARE\Eclipse Adoptium\jre-8.0.442.6-hotspot")
                winreg.CloseKey(key)
                return True
            except:
                pass
            
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                    r"SOFTWARE\JavaSoft\Java Runtime Environment\1.8")
                winreg.CloseKey(key)
                return True
            except:
                pass
        
        for path in self.get_java_paths():
            if os.path.exists(path):
                return True
        
        return False
    
    def get_java_paths(self):
        """Возвращает список возможных путей к Java"""
        paths = []
        
        for path in self.install_paths.get(self.system, []):
            if path.exists():
                paths.append(str(path))
        
        additional_paths = {
            'windows': [
                "C:/Program Files/Eclipse Adoptium/jre-8.0.442.6-hotspot/bin/java.exe",
                "C:/Program Files/Java/jre8/bin/java.exe",
                "C:/Program Files/Java/jre1.8.0/bin/java.exe",
                "C:/Program Files (x86)/Java/jre1.8.0/bin/java.exe"
            ],
            'darwin': [
                "/usr/bin/java",
                "/Library/Java/JavaVirtualMachines/temurin-8.jre/Contents/Home/bin/java"
            ],
            'linux': [
                "/usr/bin/java",
                "/usr/lib/jvm/temurin-8-jre/bin/java"
            ]
        }
        
        paths.extend([p for p in additional_paths.get(self.system, []) if os.path.exists(p)])
        
        java_home = os.environ.get('JAVA_HOME', '')
        if java_home:
            java_exe = os.path.join(java_home, 'bin', 'java.exe' if self.system == 'windows' else 'java')
            if os.path.exists(java_exe):
                paths.append(java_exe)
        
        return paths
    
    def get_java_home(self):
        """Возвращает путь к JAVA_HOME"""
        if self.system == 'windows':
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                                    r"SOFTWARE\Eclipse Adoptium\jre-8.0.442.6-hotspot")
                java_home, _ = winreg.QueryValueEx(key, "JavaHome")
                winreg.CloseKey(key)
                if os.path.exists(java_home):
                    return java_home
            except:
                pass
        
        for path in self.get_java_paths():
            if os.path.exists(path):
                return os.path.dirname(os.path.dirname(path))
        
        return None
    
    def need_admin_for_install(self):
        """Проверяет, требуются ли права администратора для установки"""
        if self.system == 'windows':
            try:
                return ctypes.windll.shell32.IsUserAnAdmin() == 0
            except:
                return True
        elif self.system in ['linux', 'darwin']:
            return os.geteuid() != 0 if hasattr(os, 'geteuid') else False
        return False


class JavaInstaller(QThread):
    """Поток для установки Java"""
    status_signal = Signal(str)
    progress_signal = Signal(int)
    
    def __init__(self):
        super().__init__()
        self.manager = JavaManager()
        self.process = None
        self._is_cancelled = False
    
    def run(self):
        try:
            if self.manager.is_java_installed():
                self.status_signal.emit("already_installed")
                return
            
            if self.manager.need_admin_for_install():
                self.status_signal.emit("need_admin")
                return
            
            if self._is_cancelled:
                return
            
            if self.manager.system == 'windows':
                self._install_windows()
            elif self.manager.system == 'darwin':
                self._install_macos()
            elif self.manager.system == 'linux':
                self._install_linux()
            else:
                self.status_signal.emit("error")
                
        except Exception as e:
            print(f"Ошибка установки Java: {e}")
            self.status_signal.emit("error")
    
    def _install_windows(self):
        """Установка Java на Windows через MSI"""
        try:
            is_64bit = platform.machine().endswith('64')
            url_key = 'windows' if is_64bit else 'windows_x86'
            url = self.manager.installer_urls.get(url_key, self.manager.installer_urls['windows'])
            
            self.status_signal.emit("downloading")
            
            if self._is_cancelled:
                return
            
            installer_path = self._download_installer(url, ".msi")
            
            if self._is_cancelled:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                return
            
            self.status_signal.emit("installing")
            
            cmd = ["msiexec.exe", "/i", installer_path, "/quiet", "/qn", "/norestart",
                   "INSTALL_SILENT=1", "STATISTICS=0"]
            
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
            
            try:
                self.process.wait(timeout=120)
            except subprocess.TimeoutExpired:
                self.process.kill()
                raise Exception("Время установки истекло")
            
            if self._is_cancelled:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                return
            
            if self.process.returncode == 0:
                time.sleep(2)
                self._setup_windows_env()
                self.status_signal.emit("success")
            else:
                raise Exception(f"Ошибка установки, код: {self.process.returncode}")
            
            if os.path.exists(installer_path):
                os.remove(installer_path)
                
        except Exception as e:
            print(f"Ошибка установки Windows: {e}")
            self.status_signal.emit("error")
    
    def _install_macos(self):
        """Установка Java на macOS"""
        try:
            url = self.manager.installer_urls['darwin']
            self.status_signal.emit("downloading")
            
            if self._is_cancelled:
                return
            
            installer_path = self._download_installer(url, ".pkg")
            
            if self._is_cancelled:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                return
            
            self.status_signal.emit("installing")
            
            cmd = ["sudo", "installer", "-pkg", installer_path, "-target", "/"]
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            self.process.wait(timeout=180)
            
            if self._is_cancelled:
                if os.path.exists(installer_path):
                    os.remove(installer_path)
                return
            
            if self.process.returncode == 0:
                self.status_signal.emit("success")
            else:
                raise Exception("Ошибка установки")
            
            if os.path.exists(installer_path):
                os.remove(installer_path)
                
        except Exception as e:
            print(f"Ошибка установки macOS: {e}")
            self.status_signal.emit("error")
    
    def _install_linux(self):
        """Установка Java на Linux"""
        try:
            self.status_signal.emit("installing")
            
            if self._is_cancelled:
                return
            
            if shutil.which("apt-get"):
                cmd = ["sudo", "apt-get", "install", "-y", "openjdk-8-jre"]
            elif shutil.which("yum"):
                cmd = ["sudo", "yum", "install", "-y", "java-1.8.0-openjdk"]
            elif shutil.which("dnf"):
                cmd = ["sudo", "dnf", "install", "-y", "java-1.8.0-openjdk"]
            elif shutil.which("pacman"):
                cmd = ["sudo", "pacman", "-S", "--noconfirm", "java8-openjdk"]
            else:
                self._install_linux_archive()
                return
            
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.process.wait(timeout=300)
            
            if self._is_cancelled:
                return
            
            if self.process.returncode == 0:
                self.status_signal.emit("success")
            else:
                raise Exception("Ошибка установки")
                
        except Exception as e:
            print(f"Ошибка установки Linux: {e}")
            self.status_signal.emit("error")
    
    def _install_linux_archive(self):
        """Альтернативная установка Linux через архив"""
        try:
            url = self.manager.installer_urls['linux']
            self.status_signal.emit("downloading")
            
            if self._is_cancelled:
                return
            
            archive_path = self._download_installer(url, ".tar.gz")
            
            if self._is_cancelled:
                if os.path.exists(archive_path):
                    os.remove(archive_path)
                return
            
            self.status_signal.emit("installing")
            
            extract_dir = "/opt/jre8"
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)
            
            import tarfile
            with tarfile.open(archive_path, 'r:gz') as tf:
                tf.extractall(extract_dir)
            
            if self._is_cancelled:
                shutil.rmtree(extract_dir, ignore_errors=True)
                if os.path.exists(archive_path):
                    os.remove(archive_path)
                return
            
            java_bin = None
            for root, dirs, files in os.walk(extract_dir):
                if 'java' in files:
                    java_bin = os.path.join(root, 'java')
                    break
            
            if java_bin:
                subprocess.run(['sudo', 'ln', '-sf', java_bin, '/usr/bin/java'])
                subprocess.run(['sudo', 'chmod', '+x', java_bin])
            
            if os.path.exists(archive_path):
                os.remove(archive_path)
            
            self.status_signal.emit("success")
            
        except Exception as e:
            print(f"Ошибка установки Linux архива: {e}")
            self.status_signal.emit("error")
    
    def _download_installer(self, url, extension):
        """Скачивает установщик"""
        temp_file = os.path.join(tempfile.gettempdir(), f"java_installer{extension}")
        
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except:
                pass
        
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        context = ssl._create_unverified_context()
        
        with urllib.request.urlopen(req, context=context) as response:
            total = int(response.info().get('Content-Length', 0))
            downloaded = 0
            
            with open(temp_file, "wb") as f:
                while True:
                    if self._is_cancelled:
                        f.close()
                        os.remove(temp_file)
                        return None
                    
                    chunk = response.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        self.progress_signal.emit(int((downloaded / total) * 100))
        
        return temp_file
    
    def _setup_windows_env(self):
        """Настраивает переменные окружения Windows"""
        try:
            java_path = None
            for path in self.manager.install_paths['windows']:
                if path.exists():
                    java_path = str(path.parent.parent)
                    break
            
            if not java_path:
                java_path = "C:/Program Files/Eclipse Adoptium/jre-8.0.442.6-hotspot"
            
            java_bin = os.path.join(java_path, "bin")
            
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                                0, winreg.KEY_SET_VALUE | winreg.KEY_READ | winreg.KEY_WRITE)
            
            winreg.SetValueEx(key, "JAVA_HOME", 0, winreg.REG_SZ, java_path)
            
            try:
                current_path, _ = winreg.QueryValueEx(key, "Path")
            except:
                current_path = ""
            
            if java_bin not in current_path:
                new_path = f"{current_path};{java_bin}"
                winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
            
            winreg.CloseKey(key)
            
            HWND_BROADCAST = 0xFFFF
            WM_SETTINGCHANGE = 0x001A
            ctypes.windll.user32.SendMessageW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment")
            
        except Exception as e:
            print(f"Ошибка настройки переменных: {e}")
    
    def cancel(self):
        """Отменяет установку"""
        self._is_cancelled = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            time.sleep(1)
            if self.process.poll() is None:
                self.process.kill()