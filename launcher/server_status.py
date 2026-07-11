# launcher/server_status.py

import json
import urllib.request
import urllib.error
import os
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtGui import QPixmap, QPainter, QColor, QBrush


class ServerStatusWidget(QWidget):
    """Виджет для отображения статуса Minecraft сервера"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # НАСТРОЙКИ СЕРВЕРА - ИЗМЕНИТЕ НА ВАШИ
        self.server_ip = "mc.masedworld.net"  # IP или домен сервера
        self.server_port = 25565  # Порт сервера
        self.server_name = "Fire Citadel"  # Название сервера
        self.check_interval = 30000  # Интервал проверки (30 секунд)
        
        # Сначала создаем UI
        self.setup_ui()
        
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.check_server_status)
        
    def setup_ui(self):
        """Настройка интерфейса виджета - полностью прозрачный фон"""
        # Основной горизонтальный layout (все в одной строке)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Контейнер для иконки с индикатором статуса
        self.icon_container = QLabel()
        self.icon_container.setFixedSize(32, 32)
        self.icon_container.setAttribute(Qt.WA_TranslucentBackground)
        main_layout.addWidget(self.icon_container)
        
        # Загружаем иконку сервера с индикатором
        self.update_server_icon()
        
        # Название сервера
        self.server_name_label = QLabel(self.server_name)
        self.server_name_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                font-size: 15px;
                font-weight: bold;
                letter-spacing: 1px;
                background: transparent;
            }
        """)
        main_layout.addWidget(self.server_name_label)
        
        # Количество игроков онлайн (справа от названия)
        self.players_label = QLabel("Загрузка...")
        self.players_label.setStyleSheet("""
            QLabel {
                color: #b0b0b0;
                font-size: 13px;
                background: transparent;
                padding-left: 5px;
            }
        """)
        main_layout.addWidget(self.players_label)
        
        main_layout.addStretch()
        
        # Делаем фон полностью прозрачным
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        
        # Статус по умолчанию - серый
        self.current_status = "gray"
        
    def update_server_icon(self):
        """Обновляет иконку сервера с индикатором статуса"""
        # Загружаем основную иконку сервера
        icon_path = self.find_server_icon()
        
        if icon_path and os.path.exists(icon_path):
            original_pixmap = QPixmap(icon_path)
            # Масштабируем до 26x26 (оставляем место для индикатора)
            scaled_pixmap = original_pixmap.scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            # Создаем иконку по умолчанию
            scaled_pixmap = QPixmap(26, 26)
            scaled_pixmap.fill(Qt.transparent)
            painter = QPainter(scaled_pixmap)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor(139, 0, 0)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(3, 3, 20, 20, 4, 4)
            painter.end()
        
        # Создаем результирующее изображение 32x32
        result = QPixmap(32, 32)
        result.fill(Qt.transparent)
        
        painter = QPainter(result)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Рисуем основную иконку
        painter.drawPixmap(2, 2, 26, 26, scaled_pixmap)
        
        # Рисуем индикатор статуса в нижнем правом углу
        status_color = self.get_status_color()
        
        # Фон индикатора (белый ободок)
        painter.setBrush(QBrush(QColor(255, 255, 255)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(20, 20, 12, 12)
        
        # Сам индикатор статуса
        painter.setBrush(QBrush(QColor(status_color)))
        painter.drawEllipse(21, 21, 10, 10)
        
        painter.end()
        
        self.icon_container.setPixmap(result)
        
    def get_status_color(self):
        """Возвращает цвет статуса в зависимости от текущего состояния"""
        if hasattr(self, 'current_status'):
            if self.current_status == "green":
                return "#4CAF50"  # Зеленый - онлайн
            elif self.current_status == "yellow":
                return "#FFC107"  # Желтый - проблемы
            else:
                return "#9E9E9E"  # Серый - оффлайн
        return "#9E9E9E"
        
    def find_server_icon(self):
        """Ищет иконку сервера в папке launcher/assets"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        assets_dir = os.path.join(current_dir, "assets")
        
        possible_names = ["icon_server.png", "server_icon.png", "server.png"]
        
        for name in possible_names:
            path = os.path.join(assets_dir, name)
            if os.path.exists(path):
                return path
        
        parent_dir = os.path.dirname(current_dir)
        root_assets = os.path.join(parent_dir, "assets")
        
        for name in possible_names:
            path = os.path.join(root_assets, name)
            if os.path.exists(path):
                return path
                
        return None
        
    def set_status_icon(self, color):
        """Устанавливает цвет индикатора статуса и обновляет иконку"""
        self.current_status = color
        self.update_server_icon()
        
    def check_server_status(self):
        """Проверяет статус сервера через API"""
        try:
            url = f"https://api.mcsrvstat.us/2/{self.server_ip}:{self.server_port}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                if data.get('online', False):
                    self.set_status_icon("green")
                    
                    players = data.get('players', {})
                    online = players.get('online', 0)
                    max_players = players.get('max', 0)
                    
                    # Показываем онлайн справа от названия
                    self.players_label.setText(f"[{online}/{max_players}]")
                else:
                    self.set_status_icon("gray")
                    self.players_label.setText("[0/0]")
                    
        except urllib.error.URLError:
            self.set_status_icon("gray")
            self.players_label.setText("[?/?]")
        except Exception as e:
            print(f"Ошибка проверки статуса: {e}")
            self.set_status_icon("gray")
            self.players_label.setText("[!/!]")
            
    def start_status_check(self):
        """Запускает периодическую проверку статуса"""
        self.check_server_status()
        self.status_timer.start(self.check_interval)
        
    def stop_status_check(self):
        """Останавливает проверку статуса"""
        self.status_timer.stop()
        
    def set_server_address(self, ip, port=25565):
        """Устанавливает адрес сервера"""
        self.server_ip = ip
        self.server_port = port
        self.check_server_status()
        
    def set_server_name(self, name):
        """Устанавливает название сервера"""
        self.server_name = name
        self.server_name_label.setText(name)
        
    def set_check_interval(self, milliseconds):
        """Устанавливает интервал проверки"""
        self.check_interval = milliseconds
        self.status_timer.setInterval(milliseconds)