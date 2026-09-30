param([switch]$SQLite, [switch]$Studio)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONUTF8='1'
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $taskPython)) { throw 'Run scripts/setup.ps1 first.' }
if (!$SQLite) {
    node tools/postgres.mjs start
    if ($LASTEXITCODE -ne 0) { throw 'Portable PostgreSQL did not start.' }
    & $taskPython -m scripts.use_postgres
}
New-Item -ItemType Directory -Force -Path runtime | Out-Null
$taskBackend = Start-Process -FilePath $taskPython -ArgumentList '-m','uvicorn','app.api.main:app','--host','127.0.0.1','--port','8000','--loop','app.services.loops:postgres_loop' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$taskRoot\runtime\backend.log" -RedirectStandardError "$taskRoot\runtime\backend-error.log"
$taskNext = Join-Path $taskRoot 'frontend\node_modules\next\dist\bin\next'
$taskFrontend = Start-Process -FilePath 'node' -ArgumentList $taskNext,'dev','--hostname','127.0.0.1' -WorkingDirectory "$taskRoot\frontend" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$taskRoot\runtime\frontend.log" -RedirectStandardError "$taskRoot\runtime\frontend-error.log"
$taskPids = @($taskBackend.Id, $taskFrontend.Id)
if ($Studio) {
    $taskStudio = Start-Process -FilePath "$taskRoot\.venv\Scripts\langgraph.exe" -ArgumentList 'dev','--no-browser','--allow-blocking' -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput "$taskRoot\runtime\studio.log" -RedirectStandardError "$taskRoot\runtime\studio-error.log"
    $taskPids += $taskStudio.Id
}
$taskPids | ConvertTo-Json | Set-Content -LiteralPath "$taskRoot\runtime\app-pids.json"
Write-Output 'DebateGraph: http://127.0.0.1:3000 | API: http://127.0.0.1:8000/docs'

