param([switch]$SQLite)
$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $taskRoot
if(!(Get-Command uv -ErrorAction SilentlyContinue)){throw 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ and retry.'}
uv sync --extra dev --extra studio
if($LASTEXITCODE -ne 0){throw 'Python dependency installation failed.'}
npm ci --prefix frontend
if($LASTEXITCODE -ne 0){throw 'Frontend dependency installation failed.'}
npm ci --prefix tools
if($LASTEXITCODE -ne 0){throw 'Portable database dependency installation failed.'}
if(!(Test-Path -LiteralPath '.env')){Copy-Item -LiteralPath '.env.example' -Destination '.env'}
if(!$SQLite){node tools/postgres.mjs start; if($LASTEXITCODE -ne 0){throw 'PostgreSQL failed.'}; .venv\Scripts\python.exe -m scripts.use_postgres}
.venv\Scripts\python.exe -m scripts.seed_fixtures
Write-Output 'Setup complete. Add your key to ignored .env, then run scripts/start.ps1.'
