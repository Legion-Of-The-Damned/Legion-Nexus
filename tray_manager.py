from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon, QAction


class TrayManager(QObject):
    """Класс для управления иконкой в трее"""
    
    def __init__(self, app, main_window):
        super().__init__()
        self.app = app
        self.main_window = main_window
        self.tray_icon = None
        self.show_action = None
        self.hide_action = None
        self.quit_action = None
        self.setup_tray()
    
    def get_current_lang(self):
        """Получает текущий язык из конфига"""
        try:
            if hasattr(self.main_window, 'settings_panel') and self.main_window.settings_panel:
                lang = self.main_window.settings_panel.config.get("lang", "ru")
            else:
                import json
                import os
                
                appdata = os.environ.get('APPDATA', '')
                if appdata:
                    config_path = os.path.join(appdata, 'LegionNexus', 'config.json')
                    if os.path.exists(config_path):
                        with open(config_path, 'r', encoding='utf-8') as f:
                            config = json.load(f)
                            lang = config.get("lang", "ru")
                    else:
                        lang = "ru"
                else:
                    lang = "ru"
        except:
            lang = "ru"
        
        return lang
    
    def get_translations(self):
        """Возвращает переводы для меню трея"""
        lang = self.get_current_lang()
        translations = {
            "ru": {
                "show": "Показать окно",
                "hide": "Скрыть окно",
                "quit": "Выход",
                "startup_title": "Legion Nexus Launcher",
                "startup_message": "Лаунчер успешно запущен и работает в фоновом режиме"
            },
            "uk": {
                "show": "Показати вікно",
                "hide": "Сховати вікно",
                "quit": "Вихід",
                "startup_title": "Legion Nexus Launcher",
                "startup_message": "Лаунчер успішно запущено та працює у фоновому режимі"
            }
        }
        return translations.get(lang, translations["ru"])
    
    def update_menu_language(self):
        """Обновляет язык меню трея"""
        if not self.tray_icon:
            return
        
        tr = self.get_translations()
        
        if self.show_action:
            self.show_action.setText(tr["show"])
        if self.hide_action:
            self.hide_action.setText(tr["hide"])
        if self.quit_action:
            self.quit_action.setText(tr["quit"])
    
    def setup_tray(self):
        # Создаем иконку в трее
        self.tray_icon = QSystemTrayIcon(self.main_window)
        self.tray_icon.setIcon(QIcon("launcher/assets/icon.png"))
        
        # Получаем переводы
        tr = self.get_translations()
        
        # Создаем контекстное меню в стиле лаунчера
        tray_menu = QMenu()
        
        tray_menu.setStyleSheet("""
            QMenu {
                background-color: rgba(20, 20, 20, 240);
                border: 1px solid rgba(139, 0, 0, 180);
                border-radius: 8px;
                padding: 5px;
            }
            QMenu::item {
                background-color: transparent;
                color: #e0e0e0;
                padding: 8px 30px 8px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QMenu::item:selected {
                background-color: rgba(139, 0, 0, 150);
                color: white;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(139, 0, 0, 100);
                margin: 5px 10px;
            }
        """)
        
        self.show_action = QAction(tr["show"], self)
        self.show_action.triggered.connect(self.show_window)
        tray_menu.addAction(self.show_action)
        
        self.hide_action = QAction(tr["hide"], self)
        self.hide_action.triggered.connect(self.hide_window)
        tray_menu.addAction(self.hide_action)
        
        tray_menu.addSeparator()
        
        self.quit_action = QAction(tr["quit"], self)
        self.quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(self.quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()
        
        # Показываем уведомление о запуске
        self.tray_icon.showMessage(
            tr["startup_title"],
            tr["startup_message"],
            QSystemTrayIcon.Information,
            2000
        )
    
    def refresh_language(self):
        """Обновляет язык меню (вызывается при смене языка в настройках)"""
        self.update_menu_language()
    
    def show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        
        # Анимация - показываем окно на переднем плане
        self.main_window.setWindowOpacity(0.95)
        self.main_window.setWindowOpacity(1.0)
    
    def hide_window(self):
        self.main_window.hide()
    
    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.main_window.isVisible():
                self.hide_window()
            else:
                self.show_window()
        elif reason == QSystemTrayIcon.Trigger:
            self.show_window()
    
    def quit_application(self):
        """Выход из приложения без подтверждения"""
        if self.tray_icon:
            self.tray_icon.hide()
        self.app.quit()
    
    def show_notification(self, title, message, icon_type=QSystemTrayIcon.Information):
        """Показать всплывающее уведомление"""
        if self.tray_icon and self.tray_icon.isSystemTrayAvailable():
            self.tray_icon.showMessage(title, message, icon_type, 3000)