$ErrorActionPreference = "Stop"

$lmsCandidates = @(
    (Get-Command lms -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
    (Join-Path $env:USERPROFILE ".lmstudio\bin\lms.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$lms = $lmsCandidates | Select-Object -First 1
if (-not $lms) {
    throw "LM Studio CLI (lms) was not found. Install LM Studio first."
}

& $lms daemon up | Out-Host
& $lms server start --port 1234 --bind 127.0.0.1 | Out-Host

$model = if ($env:PET_YAYA_LOCAL_MODEL) {
    $env:PET_YAYA_LOCAL_MODEL
} else {
    "qwen/qwen3.5-9b"
}

$loadedModels = @(& $lms ps --json | ConvertFrom-Json)
$modelIsLoaded = $loadedModels | Where-Object {
    $_.modelKey -eq $model -or $_.identifier -eq $model
}
if ($modelIsLoaded) {
    Write-Host "Local model is already loaded: $model"
} else {
    & $lms load $model --gpu max --context-length 8192 --yes | Out-Host
}

$env:PET_YAYA_DIALOGUE_MODE = "local"
$env:PET_YAYA_LOCAL_MODEL = $model
$env:PET_YAYA_LOCAL_BASE_URL = "http://127.0.0.1:1234/v1"
$env:PET_YAYA_LOCAL_API_TOKEN = "lm-studio"

& (Join-Path $PSScriptRoot "run_simulator.ps1")

