$ErrorActionPreference = 'Stop'
function Test-LocalPort([int]$Port) {
    $connection = New-Object System.Net.Sockets.TcpClient
    try { $connection.Connect('127.0.0.1', $Port); return $true } catch { return $false } finally { $connection.Dispose() }
}
function Process-Record($Process) {
    return @{ Id = $Process.Id; StartedUtc = $Process.StartTime.ToUniversalTime().ToString('o'); Executable = $Process.Path }
}
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run scripts/setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 'frontend\dist\index.html')) { throw 'Frontend is not built. Run scripts/setup.ps1.' }
New-Item -ItemType Directory -Path '.local\mongo' -Force | Out-Null
$ownedProcesses = @{}
$pidFile = Join-Path $projectRoot '.local\processes.json'
if (Test-Path -LiteralPath $pidFile) {
    $existing = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
    foreach ($property in $existing.PSObject.Properties) { $ownedProcesses[$property.Name] = $property.Value }
}
if (-not (Test-LocalPort 27017)) {
    $mongoExecutable = (Get-Command mongod -ErrorAction Stop).Source
    $dataPath = Join-Path $projectRoot '.local\mongo'
    $logPath = Join-Path $projectRoot '.local\mongo.log'
    $mongoProcess = Start-Process -FilePath $mongoExecutable -ArgumentList @('--dbpath', ('"{0}"' -f $dataPath), '--bind_ip', '127.0.0.1', '--port', '27017', '--logpath', ('"{0}"' -f $logPath)) -WindowStyle Hidden -PassThru
    $ownedProcesses['mongo'] = Process-Record $mongoProcess
}
if (-not (Test-LocalPort 8000)) {
    $serverProcess = Start-Process -FilePath $projectPython -ArgumentList @('-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $projectRoot -RedirectStandardOutput (Join-Path $projectRoot '.local\server.out.log') -RedirectStandardError (Join-Path $projectRoot '.local\server.err.log') -WindowStyle Hidden -PassThru
    $ownedProcesses['server'] = Process-Record $serverProcess
}
$ownedProcesses | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidFile
$ready = $false
for ($attempt = 0; $attempt -lt 15; $attempt++) {
    try { $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health'; if ($health.status -eq 'ok') { $ready = $true; break } } catch { }
    Start-Sleep -Milliseconds 1000
}
if (-not $ready) { throw 'Server did not become ready; inspect .local/server.err.log.' }
& $projectPython scripts/seed_demo.py
if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed; inspect MongoDB configuration.' }
Write-Host 'Fieldnote is ready: http://localhost:8000'
Write-Host 'Development demo account: demo / Fieldnote2026!'
Write-Host 'Stop only project-owned processes: scripts/stop-local.ps1'
