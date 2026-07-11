import os
import sys
import json
import hashlib
import urllib.request
import ssl
import platform
import tempfile
import shutil
import subprocess
import time
from pathlib import Path
from threading import Thread
from dataclasses import dataclass
from typing import Optional, Callable, Dict, List
from enum import Enum


# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================
def resource_path(relative_path):
    """Получает путь к ресурсу (работает и в EXE, и в разработке)"""
    try:
        # PyInstaller создает временную папку _MEIPASS
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


class UpdateStatus(Enum):
    """Статусы обновления"""
    CHECKING = "checking"
    UP_TO_DATE = "up_to_date"
    UPDATE_AVAILABLE = "update_available"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    SUCCESS = "success"
    ERROR = "error"
    NEED_RESTART = "need_restart"


@dataclass
class ReleaseInfo:
    """Информация о релизе"""
    version: str
    download_url: str
    file_name: str
    file_size: int
    release_notes: str
    published_at: str


class UpdaterError(Exception):
    """Исключения обновления"""
    pass


class FileDownloader:
    """Скачивание файлов с прогрессом"""
    
    def __init__(self, url: str, output_path: str, progress_callback: Optional[Callable] = None):
        self.url = url
        self.output_path = output_path
        self.progress_callback = progress_callback
    
    def download(self) -> bool:
        """Скачивает файл с прогрессом"""
        try:
            req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            context = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=context) as response:
                total_size = int(response.info().get('Content-Length', 0))
                downloaded = 0
                
                # Создаем директорию если нужно
                os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
                
                with open(self.output_path, "wb") as f:
                    while True:
                        chunk = response.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if self.progress_callback and total_size > 0:
                            percent = int((downloaded / total_size) * 100)
                            self.progress_callback(percent)
                
                return True
                
        except Exception as e:
            raise UpdaterError(f"Ошибка скачивания: {e}")
    
    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        """Вычисляет SHA256 хеш файла"""
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for byte_block in iter(lambda: f.read(65536), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return ""


class GitHubReleaseChecker:
    """Проверка обновлений на GitHub"""
    
    def __init__(self, repo_owner: str, repo_name: str, current_version: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version.strip('v')
        self.api_url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/releases/latest"
    
    def check(self) -> Optional[ReleaseInfo]:
        """Проверяет наличие обновлений"""
        try:
            req = urllib.request.Request(self.api_url, headers={"User-Agent": "Mozilla/5.0"})
            context = ssl._create_unverified_context()
            
            with urllib.request.urlopen(req, context=context, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
            
            latest_version = data.get("tag_name", "v1.0.0").strip('v')
            
            if self._compare_versions(latest_version, self.current_version) <= 0:
                return None
            
            # Находим подходящий файл для текущей ОС
            assets = data.get("assets", [])
            download_info = self._find_asset_for_os(assets)
            
            if not download_info:
                # Если не нашли специфичный файл, берем первый
                if assets:
                    download_info = {
                        'url': assets[0]['browser_download_url'],
                        'name': assets[0]['name'],
                        'size': assets[0].get('size', 0)
                    }
                else:
                    return None
            
            return ReleaseInfo(
                version=latest_version,
                download_url=download_info['url'],
                file_name=download_info['name'],
                file_size=download_info.get('size', 0),
                release_notes=data.get("body", ""),
                published_at=data.get("published_at", "")
            )
            
        except Exception as e:
            raise UpdaterError(f"Ошибка проверки обновлений: {e}")
    
    def _compare_versions(self, v1: str, v2: str) -> int:
        """Сравнивает версии"""
        def normalize(v):
            try:
                return [int(x) for x in v.split('.')]
            except:
                return [0]
        
        try:
            v1_parts = normalize(v1)
            v2_parts = normalize(v2)
            
            for i in range(max(len(v1_parts), len(v2_parts))):
                v1_val = v1_parts[i] if i < len(v1_parts) else 0
                v2_val = v2_parts[i] if i < len(v2_parts) else 0
                
                if v1_val > v2_val:
                    return 1
                elif v1_val < v2_val:
                    return -1
            return 0
        except:
            return 0
    
    def _find_asset_for_os(self, assets: List[Dict]) -> Optional[Dict]:
        """Находит подходящий файл для текущей ОС"""
        system = platform.system().lower()
        
        patterns = {
            'windows': ['.exe'],
            'darwin': ['.dmg', '.app.zip', '.pkg'],
            'linux': ['.appimage', '.tar.gz', '.deb', '.rpm']
        }
        
        os_patterns = patterns.get(system, [])
        
        # Ищем точное соответствие
        for asset in assets:
            name_lower = asset['name'].lower()
            for pattern in os_patterns:
                if name_lower.endswith(pattern):
                    return {
                        'url': asset['browser_download_url'],
                        'name': asset['name'],
                        'size': asset.get('size', 0)
                    }
        
        return None


class UpdaterScriptGenerator:
    """Генератор скриптов обновления для разных ОС"""
    
    def __init__(self):
        self.system = platform.system().lower()
    
    def generate(self, downloaded_file: str, current_exe: str) -> str:
        """Генерирует скрипт обновления"""
        if self.system == "windows":
            return self._generate_windows_script(downloaded_file, current_exe)
        elif self.system == "darwin":
            return self._generate_macos_script(downloaded_file, current_exe)
        else:
            return self._generate_linux_script(downloaded_file, current_exe)
    
    def _generate_windows_script(self, downloaded_file: str, current_exe: str) -> str:
        """Генерирует PowerShell скрипт для Windows"""
        current_dir = os.path.dirname(current_exe)
        script_name = f"update_script_{int(time.time())}.ps1"
        script_path = os.path.join(current_dir, script_name)
        
        # Экранируем пути
        downloaded_file_esc = downloaded_file.replace("'", "''")
        current_exe_esc = current_exe.replace("'", "''")
        
        ps_script = f'''#Auto-generated update script
$ErrorActionPreference = "Stop"
$downloadedFile = '{downloaded_file_esc}'
$currentExe = '{current_exe_esc}'

Write-Host "=== Starting update process ==="

# Wait for main app to close
Start-Sleep -Seconds 2

# Kill process if running
$processName = [System.IO.Path]::GetFileNameWithoutExtension($currentExe)
$processes = Get-Process -Name $processName -ErrorAction SilentlyContinue
if ($processes) {{
    Write-Host "Killing existing process: $processName"
    $processes | ForEach-Object {{ 
        try {{ $_.Kill(); $_.WaitForExit(2000) }} catch {{ }}
    }}
    Start-Sleep -Seconds 1
}}

# Backup old file
$backupFile = "$currentExe.backup"
if (Test-Path $backupFile) {{ Remove-Item $backupFile -Force }}
if (Test-Path $currentExe) {{
    Write-Host "Creating backup: $backupFile"
    Move-Item $currentExe $backupFile -Force
}}

# Copy new file
Write-Host "Copying new file: $downloadedFile -> $currentExe"
try {{
    Copy-Item $downloadedFile $currentExe -Force
    Write-Host "File copied successfully"
}} catch {{
    Write-Host "ERROR copying file: $_"
    if (Test-Path $backupFile) {{
        Write-Host "Restoring from backup"
        Move-Item $backupFile $currentExe -Force
    }}
    exit 1
}}

# Cleanup
if (Test-Path $backupFile) {{ Remove-Item $backupFile -Force }}
if (Test-Path $downloadedFile) {{ Remove-Item $downloadedFile -Force }}

# Launch updated launcher
Write-Host "Launching updated launcher: $currentExe"
Start-Process -FilePath $currentExe -WorkingDirectory (Split-Path $currentExe -Parent)

# Self-delete
Start-Sleep -Seconds 2
Remove-Item $MyInvocation.MyCommand.Path -Force

Write-Host "Update completed successfully"
'''
        
        # Сохраняем с UTF-8 BOM для PowerShell
        with open(script_path, 'w', encoding='utf-8-sig') as f:
            f.write(ps_script)
        
        return script_path
    
    def _generate_macos_script(self, downloaded_file: str, current_exe: str) -> str:
        """Генерирует bash скрипт для macOS"""
        current_dir = os.path.dirname(current_exe)
        script_name = f"update_script_{int(time.time())}.sh"
        script_path = os.path.join(current_dir, script_name)
        
        bash_script = f'''#!/bin/bash

DOWNLOADED_FILE="{downloaded_file}"
CURRENT_EXE="{current_exe}"

log() {{
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}}

log "=== Starting update process ==="
sleep 2

# Kill process if running
PROCESS_NAME=$(basename "$CURRENT_EXE" .app)
if pgrep -f "$PROCESS_NAME" > /dev/null 2>&1; then
    log "Killing existing process: $PROCESS_NAME"
    pkill -f "$PROCESS_NAME"
    sleep 1
fi

# Backup
BACKUP_FILE="$CURRENT_EXE.backup"
[ -f "$BACKUP_FILE" ] && rm -f "$BACKUP_FILE"
if [ -e "$CURRENT_EXE" ]; then
    log "Creating backup: $BACKUP_FILE"
    mv "$CURRENT_EXE" "$BACKUP_FILE" 2>/dev/null
fi

# Handle different file types
if [[ "$DOWNLOADED_FILE" == *.dmg ]]; then
    log "DMG file detected, mounting..."
    MOUNT_POINT="/Volumes/LauncherUpdate"
    hdiutil attach "$DOWNLOADED_FILE" -mountpoint "$MOUNT_POINT" -nobrowse
    APP_IN_DMG=$(find "$MOUNT_POINT" -maxdepth 1 -name "*.app" -type d | head -1)
    if [ -n "$APP_IN_DMG" ]; then
        log "Copying app from DMG"
        cp -R "$APP_IN_DMG" "$CURRENT_EXE"
    fi
    hdiutil detach "$MOUNT_POINT" -force 2>/dev/null
elif [[ "$DOWNLOADED_FILE" == *.tar.gz ]]; then
    log "Extracting archive"
    tar -xzf "$DOWNLOADED_FILE" -C "$(dirname "$CURRENT_EXE")"
    EXTRACTED_APP=$(find "$(dirname "$CURRENT_EXE")" -maxdepth 2 -name "*.app" -type d | head -1)
    if [ -n "$EXTRACTED_APP" ] && [ "$EXTRACTED_APP" != "$CURRENT_EXE" ]; then
        rm -rf "$CURRENT_EXE" 2>/dev/null
        mv "$EXTRACTED_APP" "$CURRENT_EXE"
    fi
else
    log "Copying file"
    cp "$DOWNLOADED_FILE" "$CURRENT_EXE"
    chmod +x "$CURRENT_EXE" 2>/dev/null
fi

# Cleanup
rm -f "$BACKUP_FILE" 2>/dev/null
rm -f "$DOWNLOADED_FILE" 2>/dev/null

# Launch
log "Launching updated launcher"
open "$CURRENT_EXE" 2>/dev/null || "$CURRENT_EXE" &

# Self-delete
rm -f "$0"

log "Update completed"
'''
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(bash_script)
        
        os.chmod(script_path, 0o755)
        return script_path
    
    def _generate_linux_script(self, downloaded_file: str, current_exe: str) -> str:
        """Генерирует bash скрипт для Linux"""
        current_dir = os.path.dirname(current_exe)
        script_name = f"update_script_{int(time.time())}.sh"
        script_path = os.path.join(current_dir, script_name)
        
        bash_script = f'''#!/bin/bash

DOWNLOADED_FILE="{downloaded_file}"
CURRENT_EXE="{current_exe}"

log() {{
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}}

log "=== Starting update process ==="
sleep 2

# Kill process if running
PROCESS_NAME=$(basename "$CURRENT_EXE")
if pgrep -f "$PROCESS_NAME" > /dev/null 2>&1; then
    log "Killing existing process: $PROCESS_NAME"
    pkill -f "$PROCESS_NAME"
    sleep 1
fi

# Backup
BACKUP_FILE="$CURRENT_EXE.backup"
[ -f "$BACKUP_FILE" ] && rm -f "$BACKUP_FILE"
if [ -f "$CURRENT_EXE" ]; then
    log "Creating backup: $BACKUP_FILE"
    mv "$CURRENT_EXE" "$BACKUP_FILE"
fi

# Handle different file types
if [[ "$DOWNLOADED_FILE" == *.tar.gz ]]; then
    log "Extracting archive"
    tar -xzf "$DOWNLOADED_FILE" -C "$(dirname "$CURRENT_EXE")"
    EXTRACTED_FILE=$(find "$(dirname "$CURRENT_EXE")" -maxdepth 2 -type f -executable | head -1)
    if [ -n "$EXTRACTED_FILE" ] && [ "$EXTRACTED_FILE" != "$BACKUP_FILE" ]; then
        mv "$EXTRACTED_FILE" "$CURRENT_EXE"
    fi
elif [[ "$DOWNLOADED_FILE" == *.AppImage ]]; then
    log "Copying AppImage"
    cp "$DOWNLOADED_FILE" "$CURRENT_EXE"
    chmod +x "$CURRENT_EXE"
else
    log "Copying binary file"
    cp "$DOWNLOADED_FILE" "$CURRENT_EXE"
    chmod +x "$CURRENT_EXE"
fi

# Cleanup
rm -f "$BACKUP_FILE" 2>/dev/null
rm -f "$DOWNLOADED_FILE" 2>/dev/null

# Launch
log "Launching updated launcher"
"$CURRENT_EXE" &

# Self-delete
rm -f "$0"

log "Update completed"
'''
        
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(bash_script)
        
        os.chmod(script_path, 0o755)
        return script_path


class AutoUpdater:
    """Основной класс автообновления"""
    
    def __init__(self, repo_owner: str, repo_name: str, current_version: str):
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.current_version = current_version
        self.release_checker = GitHubReleaseChecker(repo_owner, repo_name, current_version)
        self.script_generator = UpdaterScriptGenerator()
        self._status_callbacks = []
        self._progress_callbacks = []
    
    def on_status(self, callback: Callable):
        """Подписка на статус обновления"""
        self._status_callbacks.append(callback)
        return self
    
    def on_progress(self, callback: Callable):
        """Подписка на прогресс обновления"""
        self._progress_callbacks.append(callback)
        return self
    
    def _emit_status(self, status: UpdateStatus, message: str = ""):
        """Вызывает колбэки статуса"""
        for callback in self._status_callbacks:
            try:
                callback(status, message)
            except Exception as e:
                print(f"Ошибка в callback статуса: {e}")
    
    def _emit_progress(self, percent: int):
        """Вызывает колбэки прогресса"""
        for callback in self._progress_callbacks:
            try:
                callback(percent)
            except Exception as e:
                print(f"Ошибка в callback прогресса: {e}")
    
    def check_for_updates(self) -> Optional[ReleaseInfo]:
        """Проверяет наличие обновлений"""
        self._emit_status(UpdateStatus.CHECKING, "Проверка обновлений...")
        
        try:
            release = self.release_checker.check()
            
            if release:
                self._emit_status(UpdateStatus.UPDATE_AVAILABLE, 
                                f"Доступна версия {release.version}")
                return release
            else:
                self._emit_status(UpdateStatus.UP_TO_DATE, "У вас последняя версия")
                return None
                
        except UpdaterError as e:
            self._emit_status(UpdateStatus.ERROR, str(e))
            return None
        except Exception as e:
            self._emit_status(UpdateStatus.ERROR, f"Неизвестная ошибка: {e}")
            return None
    
    def download_update(self, release: ReleaseInfo) -> Optional[str]:
        """Скачивает обновление"""
        self._emit_status(UpdateStatus.DOWNLOADING, f"Скачивание {release.file_name}...")
        
        # Создаем папку для временных файлов
        temp_dir = os.path.join(tempfile.gettempdir(), "launcher_updates")
        os.makedirs(temp_dir, exist_ok=True)
        
        output_path = os.path.join(temp_dir, release.file_name)
        
        downloader = FileDownloader(
            release.download_url, 
            output_path, 
            self._emit_progress
        )
        
        try:
            if downloader.download():
                self._emit_status(UpdateStatus.DOWNLOADING, "Скачивание завершено")
                return output_path
            else:
                self._emit_status(UpdateStatus.ERROR, "Ошибка скачивания")
                return None
                
        except UpdaterError as e:
            self._emit_status(UpdateStatus.ERROR, str(e))
            return None
    
    def install_update(self, downloaded_file: str) -> bool:
        """Устанавливает обновление"""
        self._emit_status(UpdateStatus.INSTALLING, "Установка обновления...")
        
        try:
            current_exe = os.path.abspath(sys.argv[0])
            script_path = self.script_generator.generate(downloaded_file, current_exe)
            
            system = platform.system().lower()
            
            if system == "windows":
                # Запускаем PowerShell скрипт
                subprocess.Popen([
                    "powershell.exe",
                    "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden",
                    "-File", script_path
                ], creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                # Запускаем bash скрипт
                subprocess.Popen(["bash", script_path])
            
            self._emit_status(UpdateStatus.SUCCESS, "Обновление установлено")
            return True
            
        except Exception as e:
            self._emit_status(UpdateStatus.ERROR, f"Ошибка установки: {e}")
            return False
    
    def update(self) -> bool:
        """Полный цикл обновления"""
        # Проверяем обновления
        release = self.check_for_updates()
        if not release:
            return False
        
        # Скачиваем
        downloaded_file = self.download_update(release)
        if not downloaded_file:
            return False
        
        # Устанавливаем
        return self.install_update(downloaded_file)