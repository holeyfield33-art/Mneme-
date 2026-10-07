param(
    [ValidateSet('init', 'start', 'stop', 'restart', 'status')]
    [string]$Action = 'status'
)
$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$privatePath = Join-Path $repoPath '.local'
$pythonPath = Join-Path $repoPath '.venv-local\Scripts\python.exe'
$configPath = Join-Path $privatePath 'settings.json'
$pidPath = Join-Path $privatePath 'service.json'
$runnerPath = Join-Path $PSScriptRoot 'run_local.py'

function Initialize-Local {
    & $pythonPath (Join-Path $PSScriptRoot 'setup_local.py') init
    if ($LASTEXITCODE -ne 0) { throw 'Local initialization failed.' }
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls.exe $privatePath /inheritance:r /grant:r "${identity}:(OI)(CI)F" 'SYSTEM:(OI)(CI)F' /T /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict local credential directory permissions.' }
    Get-ChildItem -LiteralPath $privatePath -File -Recurse | ForEach-Object {
        & icacls.exe $_.FullName /inheritance:e /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "Failed to restore restricted inheritance on $($_.Name)." }
    }
}

function Get-ManagedProcess {
    if (-not (Test-Path -LiteralPath $pidPath)) { return $null }
    $record = Get-Content -LiteralPath $pidPath -Raw | ConvertFrom-Json
    $proc = Get-Process -Id $record.process_id -ErrorAction SilentlyContinue
    if (-not $proc) { return $null }
    if ($proc.StartTime.ToUniversalTime().ToString('o') -ne $record.started_utc) {
        throw 'PID was reused by another process; refusing to control it.'
    }
    return $proc
}

function Stop-Local {
    $proc = Get-ManagedProcess
    if ($proc) { Stop-Process -Id $proc.Id; $proc.WaitForExit(10000) | Out-Null }
    if (Test-Path -LiteralPath $pidPath) { Remove-Item -LiteralPath $pidPath }
    Write-Output 'Mneme API stopped. Database and durable volume are preserved.'
}

function Start-Local {
    Initialize-Local
    if (Get-ManagedProcess) { Show-Status; return }
    & docker compose -f (Join-Path $privatePath 'compose.json') up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Database startup failed. Ensure Docker Desktop is running.' }
    & $pythonPath (Join-Path $PSScriptRoot 'setup_local.py') migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    if (Get-NetTCPConnection -LocalPort $config.service_port -State Listen -ErrorAction SilentlyContinue) {
        throw 'Configured API port is already in use; refusing to start a second service.'
    }
    $stdoutPath = Join-Path $privatePath 'service.stdout.log'
    $stderrPath = Join-Path $privatePath 'service.stderr.log'
    New-Item -ItemType File -Force -Path $stdoutPath | Out-Null
    New-Item -ItemType File -Force -Path $stderrPath | Out-Null
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    foreach ($logPath in @($stdoutPath, $stderrPath)) {
        & icacls.exe $logPath /inheritance:r /grant:r "${identity}:F" 'SYSTEM:F' /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Failed to restrict local log permissions.' }
    }
    $proc = Start-Process -FilePath $pythonPath -ArgumentList ('"' + $runnerPath + '"') -WorkingDirectory $repoPath -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath
    @{process_id=$proc.Id; started_utc=$proc.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $pidPath -Encoding UTF8
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($proc.HasExited) { throw 'Mneme failed to start; inspect .local/service.stderr.log.' }
        try {
            $health = Invoke-RestMethod -Uri $config.health_endpoint -TimeoutSec 1
            if ($health.status -eq 'ok' -and $health.offline) { Show-Status; return }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    throw 'Mneme did not become healthy; inspect .local/service.stderr.log.'
}

function Show-Status {
    if (-not (Test-Path -LiteralPath $configPath)) { Write-Output 'Mneme local setup is not initialized.'; return }
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    try {
        $health = Invoke-RestMethod -Uri $config.health_endpoint -TimeoutSec 3
        [pscustomobject]@{endpoint=$config.endpoint; status=$health.status; database=$health.database; offline=$health.offline; search=$health.search_mode} | Format-List
    } catch { Write-Output 'Mneme API is not reachable.' }
}

switch ($Action) {
    'init' { Initialize-Local }
    'start' { Start-Local }
    'stop' { Stop-Local }
    'restart' { Stop-Local; Start-Local }
    'status' { Show-Status }
}
