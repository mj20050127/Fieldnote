param([switch]$KeepDatabase)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$pidFile = Join-Path $projectRoot '.local\processes.json'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Host 'No processes started by start-local.ps1 were recorded.'; exit }
$owned = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
$remaining = @{}
foreach ($entry in $owned.PSObject.Properties) {
    if ($KeepDatabase -and $entry.Name -eq 'mongo') { $remaining[$entry.Name] = $entry.Value; continue }
    $record = $entry.Value
    if (-not $record.Id -or -not $record.StartedUtc -or -not $record.Executable) {
        Write-Warning 'Legacy process record is missing identity information; refusing to stop it.'
        $remaining[$entry.Name] = $record
        continue
    }
    try { $process = Get-Process -Id ([int]$record.Id) -ErrorAction Stop }
    catch {
        if ($_.CategoryInfo.Category -ne 'ObjectNotFound') { $remaining[$entry.Name] = $record; Write-Warning 'Could not inspect a recorded process; it was left running.' }
        continue
    }
    $sameStart = $process.StartTime.ToUniversalTime().Ticks -eq ([datetime]$record.StartedUtc).ToUniversalTime().Ticks
    $samePath = $process.Path -and $process.Path.Equals([string]$record.Executable, [System.StringComparison]::OrdinalIgnoreCase)
    $isProjectPython = $entry.Name -eq 'server' -and $samePath -and $process.Path.StartsWith($projectRoot + '\', [System.StringComparison]::OrdinalIgnoreCase)
    $isProjectMongo = $entry.Name -eq 'mongo' -and $samePath -and $process.ProcessName -eq 'mongod'
    if ($sameStart -and ($isProjectPython -or $isProjectMongo)) {
        # Windows venv python.exe can redirect to a child interpreter. Stop the verified process tree.
        taskkill.exe /PID $process.Id /T /F | Out-Null
        if ($LASTEXITCODE -eq 0) { Write-Host "Stopped project process tree $($process.Id)" } else { $remaining[$entry.Name] = $record }
    } else { Write-Warning 'Process identity changed; refusing to stop a reused PID.' }
}
if ($remaining.Count -gt 0) {
    $remaining | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $pidFile
} else {
    Remove-Item -LiteralPath $pidFile
}
