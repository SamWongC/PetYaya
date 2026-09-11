@echo off
chcp 65001 >nul
start "Pet Yaya - Local" python -X utf8 "%~dp0launch_simulator.py" --local
exit /b

