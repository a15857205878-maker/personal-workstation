@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -B launch.py %*
exit /b %errorlevel%
