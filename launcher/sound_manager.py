import os
import random
from PySide6.QtCore import QUrl, QTimer
from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QPushButton


class SoundManager:
    """Менеджер звуковых эффектов и фоновой музыки"""
    
    _instance = None
    _sounds = {}
    _bgm_player = None
    _bgm_output = None
    _bgm_enabled = True
    _sfx_enabled = True
    _current_track_index = 0
    _playlist = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._sounds = {}
        self._bgm_player = None
        self._bgm_output = None
        self._playlist = []
        self._current_track_index = 0
    
    def _find_file(self, base_dir, *paths):
        """Ищет файл по нескольким возможным путям"""
        for path in paths:
            full_path = os.path.join(base_dir, path)
            if os.path.exists(full_path):
                return full_path
        return None
    
    def load_sounds(self, base_dir):
        """Загружает звуковые эффекты"""
        # Поиск папки со звуками в разных местах
        sounds_dirs = [
            os.path.join(base_dir, "assets", "sounds"),
            os.path.join(base_dir, "launcher", "assets", "sounds"),
            os.path.join(base_dir, "..", "assets", "sounds"),
        ]
        
        sounds_dir = None
        for s_dir in sounds_dirs:
            if os.path.exists(s_dir):
                sounds_dir = s_dir
                break
        
        if not sounds_dir:
            sounds_dir = os.path.join(base_dir, "assets", "sounds")
            os.makedirs(sounds_dir, exist_ok=True)
            print(f"[SoundManager] Папка со звуками создана: {sounds_dir}")
            return
        
        sound_files = {
            "click": ["click.wav", "click.mp3"],
            "hover": ["hover.wav", "hover.mp3"],
            "popup": ["popup.wav", "popup.mp3"],
            "success": ["success.wav", "success.mp3"],
            "error": ["error.wav", "error.mp3"],
            "launch": ["launch.wav", "launch.mp3"],
            "download_start": ["download_start.wav", "download_start.mp3"],
            "download_complete": ["download_complete.wav", "download_complete.mp3"]
        }
        
        for sound_id, filenames in sound_files.items():
            sound_path = None
            for filename in filenames:
                test_path = os.path.join(sounds_dir, filename)
                if os.path.exists(test_path):
                    sound_path = test_path
                    break
            
            if sound_path:
                sound = QSoundEffect()
                sound.setSource(QUrl.fromLocalFile(sound_path))
                sound.setVolume(0.7)
                self._sounds[sound_id] = sound
                print(f"[SoundManager] Загружен звук: {sound_id} из {os.path.basename(sound_path)}")
    
    def load_bgm(self, base_dir):
        """Загружает плейлист фоновой музыки"""
        music_dirs = [
            os.path.join(base_dir, "assets", "music"),
            os.path.join(base_dir, "launcher", "assets", "music"),
            os.path.join(base_dir, "assets", "sounds"),
            os.path.join(base_dir, "launcher", "assets", "sounds"),
            os.path.join(base_dir, "..", "assets", "music"),
            os.path.join(base_dir, "..", "launcher", "assets", "music"),
        ]
        
        music_dir = None
        for m_dir in music_dirs:
            if os.path.exists(m_dir):
                music_dir = m_dir
                break
        
        if not music_dir:
            music_dir = os.path.join(base_dir, "assets", "music")
            os.makedirs(music_dir, exist_ok=True)
            print(f"[SoundManager] Папка с музыкой создана: {music_dir}")
            return
        
        self._playlist = []
        audio_extensions = ('.mp3', '.wav', '.ogg', '.flac')
        
        for file in os.listdir(music_dir):
            if file.lower().endswith(audio_extensions):
                # Пропускаем звуковые эффекты
                if any(sfx in file.lower() for sfx in ['click', 'hover', 'popup', 'success', 'error', 'launch']):
                    continue
                self._playlist.append(os.path.join(music_dir, file))
        
        if self._playlist:
            print(f"[SoundManager] Найдено треков в плейлисте: {len(self._playlist)}")
            for track in self._playlist:
                print(f"  - {os.path.basename(track)}")
            
            random.shuffle(self._playlist)
            
            self._bgm_output = QAudioOutput()
            self._bgm_output.setVolume(0.3)
            
            self._bgm_player = QMediaPlayer()
            self._bgm_player.setAudioOutput(self._bgm_output)
            
            self._bgm_player.mediaStatusChanged.connect(self._on_media_status_changed)
            
            self._play_next_track()
        else:
            print(f"[SoundManager] Музыка не найдена в: {music_dir}")
    
    def _play_next_track(self):
        """Воспроизводит следующий трек из плейлиста"""
        if not self._playlist or not self._bgm_enabled:
            return
        
        if self._current_track_index >= len(self._playlist):
            random.shuffle(self._playlist)
            self._current_track_index = 0
        
        track_path = self._playlist[self._current_track_index]
        self._bgm_player.setSource(QUrl.fromLocalFile(track_path))
        self._bgm_player.play()
        print(f"[SoundManager] Воспроизведение: {os.path.basename(track_path)}")
    
    def _on_media_status_changed(self, status):
        """Обработчик изменения статуса медиаплеера"""
        if status == QMediaPlayer.EndOfMedia:
            self._current_track_index += 1
            self._play_next_track()
    
    def play_sound(self, sound_id):
        """Воспроизводит звуковой эффект"""
        if not self._sfx_enabled:
            return
        
        sound = self._sounds.get(sound_id)
        if sound and sound.isLoaded():
            sound.play()
            return True
        return False
    
    def play_hover(self):
        self.play_sound("hover")
    
    def play_click(self):
        self.play_sound("click")
    
    def play_popup(self):
        self.play_sound("popup")
    
    def play_success(self):
        self.play_sound("success")
    
    def play_error(self):
        self.play_sound("error")
    
    def play_launch(self):
        self.play_sound("launch")
    
    def play_download_start(self):
        self.play_sound("download_start")
    
    def play_download_complete(self):
        self.play_sound("download_complete")
    
    def start_bgm(self):
        if self._bgm_enabled and self._playlist and self._bgm_player:
            self._bgm_player.play()
    
    def stop_bgm(self):
        if self._bgm_player:
            self._bgm_player.stop()
    
    def pause_bgm(self):
        if self._bgm_player:
            self._bgm_player.pause()
    
    def resume_bgm(self):
        if self._bgm_player and self._bgm_enabled:
            self._bgm_player.play()
    
    def next_track(self):
        self._current_track_index += 1
        self._play_next_track()
    
    def previous_track(self):
        if self._current_track_index > 0:
            self._current_track_index -= 1
        else:
            self._current_track_index = len(self._playlist) - 1
        self._play_next_track()
    
    def set_bgm_volume(self, volume):
        if self._bgm_output:
            self._bgm_output.setVolume(max(0.0, min(1.0, volume)))
    
    def set_sfx_volume(self, volume):
        for sound in self._sounds.values():
            sound.setVolume(max(0.0, min(1.0, volume)))
    
    def set_bgm_enabled(self, enabled):
        self._bgm_enabled = enabled
        if enabled:
            self.start_bgm()
        else:
            self.stop_bgm()
    
    def set_sfx_enabled(self, enabled):
        self._sfx_enabled = enabled
    
    def is_bgm_playing(self):
        if self._bgm_player:
            return self._bgm_player.playbackState() == QMediaPlayer.PlayingState
        return False
    
    def get_current_track_name(self):
        if self._current_track_index < len(self._playlist):
            return os.path.basename(self._playlist[self._current_track_index])
        return None
    
    @staticmethod
    def instance():
        if SoundManager._instance is None:
            SoundManager()
        return SoundManager._instance


# ================= КНОПКА СО ЗВУКОМ =================
class SoundButton(QPushButton):
    """Кнопка с поддержкой звуков"""
    
    def __init__(self, text="", parent=None, sound_id="click", hover_sound="hover"):
        super().__init__(text, parent)
        self.sound_id = sound_id
        self.hover_sound = hover_sound
        self._hover_played = False
    
    def enterEvent(self, event):
        if not self._hover_played and self.isEnabled():
            SoundManager.instance().play_sound(self.hover_sound)
            self._hover_played = True
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self._hover_played = False
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if self.isEnabled():
            SoundManager.instance().play_sound(self.sound_id)
        super().mousePressEvent(event)