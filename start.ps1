$ErrorActionPreference = 'Stop'
$appDir = $PSScriptRoot
$pythonExe = 'C:\Users\LBJ\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$nodeDir = 'C:\Users\LBJ\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw '找不到Python运行时，请参阅README。' }
if (-not (Test-Path -LiteralPath (Join-Path $appDir 'node_modules'))) {
    New-Item -ItemType Junction -Path (Join-Path $appDir 'node_modules') -Target $nodeDir | Out-Null
}
$ready = $false
try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8877/api/state' -TimeoutSec 2; $ready = $true } catch {}
if (-not $ready) {
    $logDir = Join-Path $appDir 'data'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    Start-Process -FilePath $pythonExe -ArgumentList @('"' + (Join-Path $appDir 'app.py') + '"') -WorkingDirectory $appDir -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir 'server.log') -RedirectStandardError (Join-Path $logDir 'server-error.log') | Out-Null
    for ($tryIndex=0; $tryIndex -lt 30; $tryIndex++) {
        Start-Sleep -Milliseconds 300
        try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8877/api/state' -TimeoutSec 2; $ready=$true; break } catch {}
    }
}
if (-not $ready) { throw '本地服务启动失败，请查看data/server-error.log。' }
Start-Process 'http://127.0.0.1:8877'
Write-Host 'FriesGo已打开。首次启动及重启后，发送队列默认暂停。'
