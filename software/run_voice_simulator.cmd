@echo off
setlocal
chcp 65001 >nul
if not defined PET_YAYA_STT_DEVICE set "PET_YAYA_STT_DEVICE=auto"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Voice environment missing. See README voice setup.
  pause
  exit /b 1
)
start "Pet Yaya - Voice" "%~dp0.venv\Scripts\python.exe" -X utf8 "%~dp0launch_simulator.py" --local --voice
endlocal
exit /b

