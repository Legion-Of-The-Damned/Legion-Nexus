import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from splash_screen import LauncherSplashScreen
from launcher.main import MainWindow
from tray_manager import TrayManager


def main():
    app = QApplication(sys.argv)
    
    # Создаем и показываем сплеш-экран
    splash = LauncherSplashScreen()
    splash.show()
    app.processEvents()
    
    # Создаем главное окно и менеджер трея
    window = MainWindow()
    tray_manager = TrayManager(app, window)
    window.tray_manager = tray_manager  # <-- ДОБАВИТЬ ЭТУ СТРОКУ
    
    # Завершение загрузки
    def finish_loading():
        splash.close()
        window.show()
    
    QTimer.singleShot(1500, finish_loading)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()