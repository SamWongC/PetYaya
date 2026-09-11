$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
python -m pet_yaya.main

