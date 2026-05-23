param(
    [string]$BindHost = "0.0.0.0",
    [int]$Port = 8010
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
Set-Location $RepoRoot

$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $VenvPython)) {
    throw ".venv was not found. Run .\scripts\setup_windows.ps1 first."
}

if (!(Test-Path (Join-Path $RepoRoot ".env"))) {
    Write-Warning ".env is missing. LLM, ASR, or TTS calls may fail."
}

$LocalIps = @()
try {
    $LocalIps = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object {
            $_.IPAddress -ne "127.0.0.1" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Select-Object -ExpandProperty IPAddress -Unique
} catch {
    Write-Warning "Could not list local IP addresses automatically."
}

Write-Host "Starting Have Some Ai on $BindHost`:$Port"
Write-Host "Controller on Lenovo: http://127.0.0.1:$Port/"
foreach ($Ip in $LocalIps) {
    Write-Host "iMac particle display: http://$Ip`:$Port/particle-display"
}
Write-Host "If the iMac cannot connect, allow TCP port $Port in Windows Firewall for Private networks."
Write-Host ""

& $VenvPython scripts\start_have_some_ai.py --host $BindHost --port $Port
