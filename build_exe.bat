@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo Shinri Tracker - build EXE
echo ==========================================
echo.

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

REM Portable Tesseract is copied only on the developer/build PC.
REM End users receive it inside the EXE and do not install OCR manually.
if not exist "tesseract\tesseract.exe" (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo Copying Tesseract OCR into project...
        xcopy "C:\Program Files\Tesseract-OCR" "tesseract\" /E /I /Y >nul
    ) else if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
        echo Copying Tesseract OCR into project...
        xcopy "C:\Program Files (x86)\Tesseract-OCR" "tesseract\" /E /I /Y >nul
    ) else (
        echo ERROR: Tesseract OCR was not found on BUILD PC.
        echo Install it once on this PC, then run build_exe.bat again.
        goto :error
    )
)

if not exist "tesseract\tessdata\eng.traineddata" (
    echo ERROR: eng.traineddata is missing.
    goto :error
)

if not exist "tesseract\tessdata\rus.traineddata" (
    echo ERROR: rus.traineddata is missing.
    goto :error
)

set GOOGLE_ARG=
if exist "google_credentials.json" (
    set GOOGLE_ARG=--add-data "google_credentials.json;."
) else (
    echo.
    echo WARNING: google_credentials.json is missing.
    echo The EXE will build, but Shared Groups will stay disabled.
    echo See SETUP_GITHUB_GOOGLE.txt.
    echo.
)

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --name "ShinriTracker" ^
    --icon=icon.ico ^
    --add-data "icon.png;." ^
    --add-data "version.txt;." ^
    --add-data "update_config.json;." ^
    --add-data "tesseract;tesseract" ^
    %GOOGLE_ARG% ^
    --collect-all googleapiclient ^
    --collect-all google_auth_httplib2 ^
    --collect-all google_auth_oauthlib ^
    main.py

if errorlevel 1 goto :error

echo.
echo BUILD COMPLETE
echo dist\ShinriTracker.exe
echo.
pause
exit /b 0

:error
echo.
echo BUILD FAILED
echo.
pause
exit /b 1
