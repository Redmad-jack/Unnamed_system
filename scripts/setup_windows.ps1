param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @("py", "-3")
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @("python")
    }

    throw "Python was not found. Install Python 3.11+ x64 first."
}

$PythonCommand = @(Resolve-PythonCommand)
$PythonArgs = @()
if ($PythonCommand.Length -gt 1) {
    $PythonArgs = $PythonCommand[1..($PythonCommand.Length - 1)]
}
$PythonExe = $PythonCommand[0]
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (!(Test-Path $VenvPython)) {
    Write-Host "Creating .venv..."
    & $PythonExe @PythonArgs -m venv .venv
}

if (!(Test-Path $VenvPython)) {
    throw "Virtual environment was not created at .venv."
}

Write-Host "Upgrading pip..."
& $VenvPython -m pip install --upgrade pip

Write-Host "Installing project dependencies..."
& $VenvPython -m pip install -e ".[api,dev]"

if (!(Test-Path (Join-Path $RepoRoot ".env"))) {
    Write-Warning ".env is missing. Copy it from the Mac by USB or another secure method before live testing."
}

if (!$SkipTests) {
    Write-Host "Running Have Some Ai API tests..."
    & $VenvPython -m pytest tests/unit/test_have_some_ai_api.py -q
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "Start the exhibition host with:"
Write-Host "  .\scripts\start_have_some_ai_windows.ps1"
