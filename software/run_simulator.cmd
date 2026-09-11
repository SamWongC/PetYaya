@echo off
setlocal
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONPATH=%~dp0src"
start "Pet Yaya" python -X utf8 "%~dp0launch_simulator.py"
endlocal

