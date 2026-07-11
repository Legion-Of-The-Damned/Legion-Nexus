import sys
import os
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen
from PySide6.QtWidgets import QSplashScreen, QApplication, QMainWindow
from PySide6.QtCore import Qt, QTimer, QThread, Signal

class LauncherSplashScreen(QSplashScreen):
    def __init__(self):
        self.splash_width = 220
        self.splash_height = 220
        
        # Создаем заставку
        splash_pixmap = QPixmap(self.splash_width, self.splash_height)
        splash_pixmap.fill(Qt.transparent)
        
        super().__init__(splash_pixmap)
        
        # Настройка окна заставки
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Параметры анимации
        self.current_step = 0
        self.num_segments = 8
        
        # Цвета
        self.base_red = QColor(139, 0, 0)
        self.active_red = QColor(255, 34, 34)
        
        # Таймер анимации
        self.timer = QTimer()
        self.timer.timeout.connect(self.rotate_spinner)
        self.timer.start(50)  # Уменьшил до 50ms для более плавной работы
    
    def rotate_spinner(self):
        self.current_step = (self.current_step + 1) % self.num_segments
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        center_x = self.splash_width / 2
        center_y = self.splash_height / 2
        
        outer_radius = 45.0
        inner_radius = 29.0
        mid_radius = (outer_radius + inner_radius) / 2
        
        painter.translate(center_x, center_y)
        segment_angle = (360 / self.num_segments) - 11
        
        for i in range(self.num_segments):
            painter.save()
            
            angle = (i * 360 / self.num_segments) - 90
            painter.rotate(angle)
            
            relative_index = (i - self.current_step) % self.num_segments
            factor = relative_index / (self.num_segments - 1)
            
            r = int(self.base_red.red() + (self.active_red.red() - self.base_red.red()) * factor)
            g = int(self.base_red.green() + (self.active_red.green() - self.base_red.green()) * factor)
            b = int(self.base_red.blue() + (self.active_red.blue() - self.base_red.blue()) * factor)
            alpha = int(40 + (215 * factor))
            
            pen = QPen()
            pen.setColor(QColor(r, g, b, alpha))
            pen.setWidthF(outer_radius - inner_radius)
            pen.setCapStyle(Qt.FlatCap)
            painter.setPen(pen)
            
            arc_rect = [-mid_radius, -mid_radius, mid_radius * 2, mid_radius * 2]
            painter.drawArc(
                arc_rect[0], arc_rect[1], arc_rect[2], arc_rect[3],
                0, 
                int(segment_angle * 16)
            )
            
            painter.restore()
            
        painter.end()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Главное окно")
        self.setGeometry(100, 100, 800, 600)

def main():
    app = QApplication(sys.argv)
    
    # Показываем splash screen
    splash = LauncherSplashScreen()
    splash.show()
    
    # Обрабатываем события, чтобы splash отрисовался
    app.processEvents()
    
    # Создаем главное окно
    main_window = MainWindow()
    
    # Эмулируем загрузку (замените на реальную логику)
    def finish_splash():
        splash.finish(main_window)
        main_window.show()
    
    # Запускаем загрузку с задержкой (демонстрация)
    QTimer.singleShot(2000, finish_splash)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()