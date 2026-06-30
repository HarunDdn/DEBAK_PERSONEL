@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo Sanal ortam bulunamadi. Once install.bat calistirin.
    pause
    exit /b 1
)

if not exist ".env" (
    echo .env dosyasi bulunamadi. install.bat calistirin veya .env.example kopyalayin.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat
echo DEBAK Personel Portal baslatiliyor: http://127.0.0.1:8000
python run.py
