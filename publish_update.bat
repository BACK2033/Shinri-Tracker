@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo Publish Shinri Tracker update
ECHO ==========================================
echo.
set /p VERSION=New version without v (example 0.9.1): 
if "%VERSION%"=="" exit /b 1

> version.txt echo %VERSION%
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Shinri Tracker %VERSION%"
    if errorlevel 1 goto :error
)

git push
if errorlevel 1 goto :error

git tag "v%VERSION%"
if errorlevel 1 (
    echo.
    echo Tag v%VERSION% already exists or could not be created.
    goto :error
)

git push origin "v%VERSION%"
if errorlevel 1 goto :error

echo.
echo Done. GitHub Actions will build and publish Release v%VERSION%.
echo Open the repository Actions page to watch the build.
echo.
pause
exit /b 0

:error
echo.
echo Publishing failed. Read the Git output above.
echo.
pause
exit /b 1
