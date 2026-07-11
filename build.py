import os
import shutil
import subprocess

def build():
    print("🚀 Начинаю сборку Legion Nexus Launcher...")
    
    # Очистка
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"✓ Очищена папка {folder}")
    
    # Ищем ICO иконку
    icon_path = None
    if os.path.exists('launcher/assets/icon.ico'):
        icon_path = 'launcher/assets/icon.ico'
        print(f"✓ Найдена иконка: {icon_path}")
    elif os.path.exists('assets/icon.ico'):
        icon_path = 'assets/icon.ico'
        print(f"✓ Найдена иконка: {icon_path}")
    else:
        print("⚠️ Иконка не найдена, будет стандартная")
    
    # Базовая команда сборки
    cmd = [
        'pyinstaller',
        '--name=LegionNexus',
        '--windowed',
        '--onefile',
        '--add-data=launcher/assets;assets',
        '--add-data=launcher;launcher',
        '--hidden-import=PySide6.QtCore',
        '--hidden-import=PySide6.QtGui',
        '--hidden-import=PySide6.QtWidgets',
        '--hidden-import=requests',
        '--hidden-import=pypresence',
    ]
    
    # Безопасное добавление иконки (как два отдельных аргумента)
    if icon_path:
        cmd.extend(['--icon', icon_path])
    
    # В самом конце добавляем главный скрипт
    cmd.append('run.py')
    
    print("\n📦 Запуск PyInstaller...")
    print("   Это может занять 2-5 минут...\n")
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("\n" + "="*50)
        print("✅ СБОРКА УСПЕШНО ЗАВЕРШЕНА!")
        print("="*50)
        
        exe_path = os.path.join('dist', 'LegionNexus.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / 1024 / 1024
            print(f"📁 Файл: {exe_path}")
            print(f"📏 Размер: {size_mb:.2f} MB")
            print(f"🖼️  Иконка: {'встроена' if icon_path else 'стандартная'}")
        
        # Копируем runtime если есть
        if os.path.exists('runtime'):
            print("\n📦 Копируем runtime папку...")
            dist_runtime = os.path.join('dist', 'runtime')
            if os.path.exists(dist_runtime):
                shutil.rmtree(dist_runtime)
            shutil.copytree('runtime', dist_runtime)
            print("✓ Runtime скопирована")
        
        print("\n📋 ДЛЯ ЗАПУСКА:")
        print("   1. Откройте папку dist")
        print("   2. Запустите LegionNexus.exe")
        
    else:
        print("\n❌ ОШИБКА СБОРКИ:")
        # Показываем последние строки ошибки для диагностики
        error_lines = result.stderr.split('\n')
        for line in error_lines[-20:]:  # Увеличил до 20 строк, чтобы точно видеть суть проблемы
            if line.strip():
                print(line)

if __name__ == "__main__":
    build()