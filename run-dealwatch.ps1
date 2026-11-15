# Entry point for Task Scheduler: one `dealwatch run`, logged next to the database.
$project = $PSScriptRoot
$dataDir = Join-Path $env:LOCALAPPDATA "dealwatch"
New-Item -ItemType Directory -Force $dataDir | Out-Null
$log = Join-Path $dataDir "dealwatch.log"

# Keep the log from growing without bound.
if ((Test-Path $log) -and (Get-Item $log).Length -gt 2MB) { Move-Item -Force $log "$log.old" }

Set-Location $project
$env:PYTHONPATH = Join-Path $project "src"
$env:PYTHONUTF8 = "1"
& (Join-Path $project ".venv\Scripts\python.exe") -m dealwatch.cli --log-file $log -v run | Out-Null
exit $LASTEXITCODE
