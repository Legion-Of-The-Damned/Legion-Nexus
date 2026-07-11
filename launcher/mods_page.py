import os

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QScrollArea, 
    QVBoxLayout, QHBoxLayout, QComboBox, QSpacerItem, QSizePolicy, QAbstractButton
)
from PySide6.QtGui import QFont, QPixmap, QFontDatabase, QColor, QPainter, QBrush, QPen
from PySide6.QtCore import Qt, QPropertyAnimation, QTimer, QFileSystemWatcher, Property, QEasingCurve, Signal


# ================= КРАСИВЫЙ АНИМИРОВАННЫЙ СВИТЧ =================
class AnimatedToggle(QAbstractButton):
    def __init__(self, parent=None, active_color="#8b0000", bg_color="#202020", circle_color="#ffffff"):
        super().__init__(parent)
        self.setFixedSize(58, 30)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)

        # Цвета
        self._active_color = QColor(active_color)
        self._bg_color = QColor(bg_color)
        self._circle_color = QColor(circle_color)

        # Анимационные параметры (будут меняться плавно от 0.0 до 1.0)
        self._progress = 0.0

        self.animation = QPropertyAnimation(self, b"progress", self)
        self.animation.setDuration(180)
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)

        # Переключаем состояние по клику
        self.clicked.connect(self.start_animation)

    # Делаем Qt-свойство для анимации
    @Property(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, pos):
        self._progress = pos
        self.update()  # Вызывает перерисовку (paintEvent)

    def start_animation(self, checked):
        self.animation.stop()
        self.animation.setEndValue(1.0 if checked else 0.0)
        self.animation.start()

    def set_state_animated(self, checked, trigger_callback=True):
        """Метод для программного изменения состояния (например, при сканировании диска)"""
        if self.isChecked() == checked:
            return
            
        self.blockSignals(not trigger_callback)
        self.setChecked(checked)
        self.blockSignals(False)

        self.animation.stop()
        self.animation.setEndValue(1.0 if checked else 0.0)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        # Вычисляем текущий цвет фона (интерполяция между выключенным и включенным)
        r = self._bg_color.red() + (self._active_color.red() - self._bg_color.red()) * self._progress
        g = self._bg_color.green() + (self._active_color.green() - self._bg_color.green()) * self._progress
        b = self._bg_color.blue() + (self._active_color.blue() - self._bg_color.blue()) * self._progress
        current_bg = QColor(int(r), int(g), int(b))

        # Рисуем закругленный фон задника
        painter.setBrush(QBrush(current_bg))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        # Добавим тонкую стильную обводку
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawRoundedRect(0, 0, self.width(), self.height(), self.height() / 2, self.height() / 2)

        # Вычисляем позицию кружка (ползунка)
        x_pos = 3 + (self.width() - self.height() + 2) * self._progress
        y_pos = 3
        circle_diameter = self.height() - 6

        # Рисуем кружок
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self._circle_color))
        painter.drawEllipse(x_pos, y_pos, circle_diameter, circle_diameter)

        painter.end()


# ================= СТРАНИЦА МОДОВ И РЕСУРСПАКОВ =================
class AddonsPage(QWidget):
    minecraft_dir_changed = Signal()
    
    def __init__(self, main_window=None):
        super().__init__(main_window)

        self.main_window = main_window
        self.setGeometry(0, 0, 900, 600)
        
        self._minecraft_dir = None

        self._load_font()

        # Текущая активная вкладка: "mods" или "resourcepacks"
        self.current_tab = "mods"

        # Расширенная локализация
        self.trans = {
            "ru": {
                "tab_mods": "МОДЫ",
                "tab_packs": "РЕСУРСПАКИ",
                "back_btn": "← НАЗАД",
                "sort_az": "Сортировка: А-Я",
                "sort_enabled": "Сначала включенные"
            },
            "uk": {
                "tab_mods": "МОДИ",
                "tab_packs": "РЕСУРСПАКИ",
                "back_btn": "← НАЗАД",
                "sort_az": "Сортування: А-Я",
                "sort_enabled": "Спочатку увімкнені"
            }
        }

        # Инициализируем пути (будут обновлены при первой загрузке)
        self.paths = {}
        self._init_paths()
        
        self.sort_mode = "az"
        self.addon_cards = {} 

        # Задний фон и оверлей
        self.bg = QLabel(self)
        self.bg.setGeometry(0, 0, 900, 600)
        bg_path = os.path.join(self.main_window.base_dir, "assets", "background.png")
        if os.path.exists(bg_path):
            self.bg.setPixmap(QPixmap(bg_path))
            self.bg.setScaledContents(True)

        self.overlay = QWidget(self)
        self.overlay.setGeometry(0, 0, 900, 600)
        self.overlay.setStyleSheet("background-color: rgba(0, 0, 0, 185);")

        # Общий контейнер для вкладок
        self.tabs_container = QWidget(self)
        self.tabs_container.setGeometry(30, 15, 450, 50)
        self.tabs_layout = QHBoxLayout(self.tabs_container)
        self.tabs_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs_layout.setSpacing(25)

        # Стиль для кнопок-вкладок
        self.tab_style_active = "color: #ffffff; font-weight: bold; font-size: 24px; letter-spacing: 2px; border: none; background: transparent;"
        self.tab_style_inactive = "color: #555555; font-weight: bold; font-size: 24px; letter-spacing: 2px; border: none; background: transparent;"

        # Вкладка Моды
        self.tab_mods_btn = QPushButton(self.tabs_container)
        self.tab_mods_btn.setFont(self.font_aiw)
        self.tab_mods_btn.setCursor(Qt.PointingHandCursor)
        self.tab_mods_btn.clicked.connect(lambda: self.switch_tab("mods"))
        self.tabs_layout.addWidget(self.tab_mods_btn)

        # Вкладка Ресурспаки
        self.tab_packs_btn = QPushButton(self.tabs_container)
        self.tab_packs_btn.setFont(self.font_aiw)
        self.tab_packs_btn.setCursor(Qt.PointingHandCursor)
        self.tab_packs_btn.clicked.connect(lambda: self.switch_tab("resourcepacks"))
        self.tabs_layout.addWidget(self.tab_packs_btn)
        
        self.tabs_layout.addStretch()

        # ================= BACK =================
        self.back_btn = QPushButton(self)
        self.back_btn.setGeometry(720, 25, 140, 40)
        self.back_btn.setFont(self.font_aiw)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.go_back)

        self.back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(20, 20, 20, 200);
                color: #e0e0e0;
                border: 1px solid rgba(139, 0, 0, 160);
                border-radius: 6px;
                font-size: 14px;
                letter-spacing: 1px;
                padding-bottom: 2px;
            }
            QPushButton:hover {
                background-color: #8b0000;
                color: white;
                border: 1px solid #ff2222;
            }
        """)

        # ================= SORT MENU =================
        self.sort_box = QComboBox(self)
        self.sort_box.setGeometry(30, 75, 260, 36)
        self.sort_box.currentIndexChanged.connect(self.change_sort)
        self.sort_box.setFont(self.clean_font)
        self.sort_box.setCursor(Qt.PointingHandCursor)

        self.sort_box.setStyleSheet("""
            QComboBox {
                background-color: rgba(15, 15, 15, 240);
                color: #e0e0e0;
                border: 1px solid rgba(139, 0, 0, 140);
                border-radius: 6px;
                padding-left: 12px;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #0f0f0f;
                color: #e0e0e0;
                border: 1px solid #8b0000;
                selection-background-color: #8b0000;
                selection-color: white;
            }
        """)

        # ================= SCROLL =================
        self.scroll = QScrollArea(self)
        self.scroll.setGeometry(30, 130, 840, 435)
        self.scroll.setWidgetResizable(True)

        self.scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: rgba(0, 0, 0, 80);
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(139, 0, 0, 150);
                min-height: 25px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(255, 34, 34, 180);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.scroll.setWidget(self.container)

        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 4, 10, 4)
        self.layout.setSpacing(12)

        self.list_spacer = None

        # ================= ФАЙЛОВЫЙ НАБЛЮДАТЕЛЬ (AUTO-REFRESH) =================
        self.watcher = QFileSystemWatcher(self)
        self.watcher_timer = QTimer(self)
        self.watcher_timer.setSingleShot(True)
        self.watcher_timer.timeout.connect(self.load_addons)
        
        # Слушаем сигнал изменения папки Minecraft
        self.minecraft_dir_changed.connect(self.on_minecraft_dir_changed)
        
        self.update_localization()
        self.load_addons()

    def _get_minecraft_dir(self):
        """Получает текущую папку Minecraft из настроек"""
        if self.main_window and hasattr(self.main_window, "settings_panel"):
            # Пробуем получить путь из настроек
            config_dir = self.main_window.settings_panel.config.get("minecraft_path", "")
            if config_dir and os.path.exists(config_dir):
                return config_dir
        
        # Если путь не задан или не существует, используем стандартный
        default_dir = os.path.join(self.main_window.base_dir, "..", "Minecraft")
        if os.path.exists(default_dir):
            return default_dir
            
        # Если папки нет, создаем её
        os.makedirs(default_dir, exist_ok=True)
        return default_dir
    
    def _init_paths(self):
        """Инициализирует пути к папкам модов и ресурспаков на основе выбранной папки Minecraft"""
        new_minecraft_dir = self._get_minecraft_dir()
        
        # Если папка не изменилась, не обновляем
        if self._minecraft_dir == new_minecraft_dir and self.paths:
            return
            
        self._minecraft_dir = new_minecraft_dir
        
        # Обновляем пути (теперь с маленькой буквы!)
        self.paths = {
            "mods": {
                "enabled": os.path.join(self._minecraft_dir, "mods"),
                "disabled": os.path.join(self._minecraft_dir, "mods_disabled"),
                "ext": ".jar"
            },
            "resourcepacks": {
                "enabled": os.path.join(self._minecraft_dir, "resourcepacks"),
                "disabled": os.path.join(self._minecraft_dir, "resourcepacks_disabled"),
                "ext": ".zip"
            }
        }
        
        # Создаем папки, если их нет
        for type_key in self.paths:
            os.makedirs(self.paths[type_key]["enabled"], exist_ok=True)
            os.makedirs(self.paths[type_key]["disabled"], exist_ok=True)
        
        # Обновляем файловый наблюдатель
        self._update_watcher()
    
    def _update_watcher(self):
        """Обновляет список отслеживаемых папок в файловом наблюдателе"""
        if hasattr(self, 'watcher') and self.watcher:
            # Убираем старые пути
            watched_paths = self.watcher.directories()
            for path in watched_paths:
                try:
                    self.watcher.removePath(path)
                except:
                    pass
            
            # Добавляем новые пути
            for type_key in self.paths:
                enabled_path = self.paths[type_key]["enabled"]
                disabled_path = self.paths[type_key]["disabled"]
                if os.path.exists(enabled_path):
                    self.watcher.addPath(enabled_path)
                if os.path.exists(disabled_path):
                    self.watcher.addPath(disabled_path)
            
            # Подключаем сигнал, если еще не подключен
            try:
                self.watcher.directoryChanged.disconnect()
            except:
                pass
            self.watcher.directoryChanged.connect(self.on_directory_changed)
    
    def on_minecraft_dir_changed(self):
        """Обработчик изменения папки Minecraft"""
        self._init_paths()
        self.load_addons()
    
    def set_minecraft_dir(self, new_dir):
        """Публичный метод для изменения папки Minecraft извне (например, из настроек)"""
        if os.path.exists(new_dir) and self._minecraft_dir != new_dir:
            self._minecraft_dir = new_dir
            self._init_paths()
            self.load_addons()
            # Сохраняем в настройки, если есть такая возможность
            if self.main_window and hasattr(self.main_window, "settings_panel"):
                self.main_window.settings_panel.config["minecraft_path"] = new_dir
                self.main_window.settings_panel._save_config()

    def on_directory_changed(self, path):
        self.watcher_timer.start(150)

    def update_localization(self):
        lang = "ru"
        if self.main_window and hasattr(self.main_window, "settings_panel"):
            lang = self.main_window.settings_panel.config.get("lang", "ru")
            
        tr = self.trans[lang]

        # Обновляем текст вкладок
        self.tab_mods_btn.setText(tr["tab_mods"])
        self.tab_packs_btn.setText(tr["tab_packs"])
        
        # Визуальное выделение активной вкладки
        if self.current_tab == "mods":
            self.tab_mods_btn.setStyleSheet(self.tab_style_active)
            self.tab_packs_btn.setStyleSheet(self.tab_style_inactive)
        else:
            self.tab_mods_btn.setStyleSheet(self.tab_style_inactive)
            self.tab_packs_btn.setStyleSheet(self.tab_style_active)
        
        self.back_btn.setText(tr["back_btn"])
        self.back_btn.setFont(self.font_aiw)

        current_index = self.sort_box.currentIndex()
        if current_index == -1: 
            current_index = 0

        self.sort_box.blockSignals(True)
        self.sort_box.clear()
        self.sort_box.addItems([tr["sort_az"], tr["sort_enabled"]])
        self.sort_box.setCurrentIndex(current_index)
        
        self.sort_box.setFont(self.font_aiw)
        self.sort_box.view().setFont(self.font_aiw)
        self.sort_box.blockSignals(False)

    def _load_font(self):
        font_path = os.path.join(self.main_window.base_dir, "assets", "fonts", "AiW.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            families = QFontDatabase.applicationFontFamilies(font_id)
            self.font_aiw = QFont(families[0]) if families else QFont("Arial")
        else:
            self.font_aiw = QFont("Arial")
        self.clean_font = QFont("Segoe UI", 12)

    def switch_tab(self, tab_name):
        if self.current_tab == tab_name:
            return
        self.current_tab = tab_name
        self.update_localization()
        self.load_addons()

    def change_sort(self, index):
        self.sort_mode = "az" if index == 0 else "state"
        self.load_addons()

    # ================= LOAD & UPDATE ADDONS =================

    def load_addons(self):
        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.blockSignals(True)

        current_paths = self.paths[self.current_tab]
        enabled_dir = current_paths["enabled"]
        disabled_dir = current_paths["disabled"]
        ext = current_paths["ext"]

        current_addons = {}
        
        # Загружаем включенные аддоны
        if os.path.exists(enabled_dir):
            try:
                for f in os.listdir(enabled_dir):
                    if f.endswith(ext):
                        current_addons[f] = True
            except OSError as e:
                print(f"Ошибка чтения папки {enabled_dir}: {e}")

        # Загружаем отключенные аддоны
        if os.path.exists(disabled_dir):
            try:
                for f in os.listdir(disabled_dir):
                    if f.endswith(ext):
                        current_addons[f] = False
            except OSError as e:
                print(f"Ошибка чтения папки {disabled_dir}: {e}")

        # Удаляем карточки для файлов, которых больше нет
        for file in list(self.addon_cards.keys()):
            if file not in current_addons:
                card, _, _ = self.addon_cards.pop(file)
                self.layout.removeWidget(card)
                card.deleteLater()

        if self.list_spacer:
            self.layout.removeItem(self.list_spacer)
            self.list_spacer = None

        # Создаем или обновляем карточки
        for file, enabled in current_addons.items():
            if file in self.addon_cards:
                card, switch, old_state = self.addon_cards[file]
                if old_state != enabled:
                    switch.set_state_animated(enabled, trigger_callback=False)
                    self.addon_cards[file] = (card, switch, enabled)
            else:
                card, switch = self.create_addon_card(file, enabled, ext)
                self.addon_cards[file] = (card, switch, enabled)

        # Сортируем файлы
        sorted_files = list(current_addons.keys())
        if self.sort_mode == "az":
            sorted_files.sort(key=lambda x: x.lower())
        else:
            sorted_files.sort(key=lambda x: current_addons[x], reverse=True)

        # Вставляем карточки в правильном порядке
        for index, file in enumerate(sorted_files):
            card, _, _ = self.addon_cards[file]
            self.layout.removeWidget(card) 
            self.layout.insertWidget(index, card) 

        self.list_spacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.layout.addSpacerItem(self.list_spacer)

        if hasattr(self, 'watcher') and self.watcher:
            self.watcher.blockSignals(False)

    def create_addon_card(self, file, enabled, ext):
        display_name = file.replace(ext, "").split("-")[0]
        display_name = display_name.upper() if display_name.islower() else display_name

        card = QWidget()
        card.setFixedHeight(84)

        card.setStyleSheet("""
            QWidget {
                background-color: rgba(20, 20, 20, 170);
                border: 1px solid rgba(139, 0, 0, 85);
                border-radius: 10px;
            }
            QWidget:hover {
                background-color: rgba(32, 32, 32, 210);
                border: 1px solid rgba(255, 34, 34, 120);
            }
        """)

        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(20, 12, 20, 12)

        text_container = QWidget()
        text_container.setStyleSheet("background: transparent; border: none;")
        text_layout = QVBoxLayout(text_container)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        name = QLabel(display_name, text_container)
        name.setFont(self.font_aiw)
        name.setStyleSheet("color: #ffffff; font-size: 16px; letter-spacing: 1px; border: none; background: transparent;")

        file_label = QLabel(file, text_container)
        file_label.setFont(self.clean_font)
        file_label.setStyleSheet("color: #9e9e9e; font-size: 12px; border: none; background: transparent;")

        text_layout.addWidget(name)
        text_layout.addWidget(file_label)

        switch = AnimatedToggle(active_color="#8b0000", bg_color="#202020")
        switch.set_state_animated(enabled, trigger_callback=False)
        # Сохраняем имя файла и расширение для корректной работы
        switch.toggled.connect(lambda state, f=file, e=ext: self.toggle_addon(f, state, e))

        card_layout.addWidget(text_container)
        card_layout.addStretch()
        card_layout.addWidget(switch, alignment=Qt.AlignRight | Qt.AlignVCenter)

        return card, switch

    def toggle_addon(self, file, enabled, ext=None):
        current_paths = self.paths[self.current_tab]
        
        if enabled:
            # Включаем - перемещаем из disabled в enabled
            src = os.path.join(current_paths["disabled"], file)
            dst = os.path.join(current_paths["enabled"], file)
        else:
            # Выключаем - перемещаем из enabled в disabled
            src = os.path.join(current_paths["enabled"], file)
            dst = os.path.join(current_paths["disabled"], file)

        # Проверяем существование исходного файла
        if os.path.exists(src):
            try:
                # Убеждаемся, что целевая папка существует
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # Перемещаем файл
                os.rename(src, dst)
                print(f"Файл перемещен: {src} -> {dst}")
            except OSError as e:
                print(f"Ошибка перемещения файла {file}: {e}")
                return
        else:
            # Если файла нет в ожидаемом месте, проверяем альтернативный путь
            alt_src = None
            if enabled:
                alt_src = os.path.join(current_paths["enabled"], file)
            else:
                alt_src = os.path.join(current_paths["disabled"], file)
            
            if os.path.exists(alt_src):
                try:
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    os.rename(alt_src, dst)
                    print(f"Файл перемещен (альт): {alt_src} -> {dst}")
                except OSError as e:
                    print(f"Ошибка перемещения файла {file}: {e}")
                    return
            else:
                print(f"Файл не найден: {src} или {alt_src}")
                return

        # Обновляем состояние в кэше
        if file in self.addon_cards:
            card, switch, _ = self.addon_cards[file]
            self.addon_cards[file] = (card, switch, enabled)

        # Перезагружаем список аддонов
        self.load_addons()

    def go_back(self):
        if self.main_window:
            self.main_window.show_main_page()


# Сохраняем имя-ссылку для полной совместимости
ModsPage = AddonsPage