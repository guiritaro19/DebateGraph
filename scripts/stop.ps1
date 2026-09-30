$ErrorActionPreference='Stop'
$taskRoot=Split-Path -Parent $PSScriptRoot
$taskPidFile=Join-Path $taskRoot 'runtime\app-pids.json'
if(Test-Path -LiteralPath $taskPidFile){
    $taskProcesses=Get-Content -LiteralPath $taskPidFile -Raw | ConvertFrom-Json
    foreach($taskProcessId in $taskProcesses){
        $taskProcess=Get-CimInstance Win32_Process -Filter "ProcessId=$taskProcessId" -ErrorAction SilentlyContinue
        if($taskProcess -and $taskProcess.CommandLine -like "*$taskRoot*"){
            Stop-Process -Id $taskProcessId -ErrorAction SilentlyContinue
        }
    }
}
Set-Location -LiteralPath $taskRoot
if(Test-Path -LiteralPath 'runtime\postgres-data\PG_VERSION'){node tools/postgres.mjs stop}
Write-Output 'Local services stopped; database preserved.'
