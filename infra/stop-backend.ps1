param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$pidName = if ($Port -eq 8000) { 'api.pid' } else { "api-$Port.pid" }
$projectRoot = Split-Path $PSScriptRoot -Parent
$pidRoot = if ($env:SCHOLARLENS_LAUNCHER_DIR) { (Resolve-Path -LiteralPath $env:SCHOLARLENS_LAUNCHER_DIR).Path } else { Join-Path $projectRoot 'backend/.runtime' }
$pidFile = Join-Path $pidRoot $pidName
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No recorded API process.'; return }
$savedPid = [int](Get-Content -LiteralPath $pidFile)
$proc = Get-CimInstance Win32_Process -Filter "ProcessId=$savedPid"
if ($proc) {
    $allowedPythons = @(
        (Join-Path $projectRoot 'backend/.venv/Scripts/python.exe').Replace('/','\'),
        (Join-Path $projectRoot '.venv/Scripts/python.exe').Replace('/','\')
    )
    if ($proc.CommandLine -notlike '*uvicorn*backend.app1:app*' -or $proc.CommandLine -notlike "*--port $Port*" -or $allowedPythons -notcontains $proc.ExecutablePath) { throw 'Recorded PID no longer belongs to this ScholarLens API/port.' }
    # Windows venv python.exe starts the base interpreter as a child. Stop the
    # validated project-owned tree so no listener or inherited pipe remains.
    & taskkill.exe /PID $savedPid /T /F
    if ($LASTEXITCODE -ne 0) { throw 'Stopping the recorded API process tree failed.' }
}
Remove-Item -LiteralPath $pidFile
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { break }
    if ($attempt -eq 19) { throw "Port $Port is still listening; inspect owner before continuing." }
    Start-Sleep -Milliseconds 100
}
Write-Output 'Stopped recorded API process.'
