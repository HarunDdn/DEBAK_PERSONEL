@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ============================================
echo  DEBAK Personel Portal - Kurulum
echo ============================================
echo.

where python >nul 2>&1
if errorlevel 1 (
    echo HATA: Python bulunamadi. Python 3.10+ kurun ve PATH'e ekleyin.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo .env dosyasi olusturuldu. CANIAS_DB_PASSWORD degerini duzenleyin.
    ) else (
        echo UYARI: .env.example bulunamadi.
    )
)

if not exist "venv\Scripts\python.exe" (
    echo Sanal ortam olusturuluyor...
    python -m venv venv
    if errorlevel 1 (
        echo HATA: venv olusturulamadi.
        pause
        exit /b 1
    )
)

echo Bagimliliklar yukleniyor...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo HATA: pip install basarisiz.
    pause
    exit /b 1
)

echo.
echo Kurulum tamamlandi.
echo Sonraki adim: .env dosyasindaki veritabani sifresini girin.
echo Portal baslatmak icin start_portal.bat calistirin.
echo.
pause
