$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'Set-ProjectEnv.ps1')
$runtimeRoot = & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'postgres_paths.py')
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare PostgreSQL path alias.' }
$pgCtl = Join-Path $runtimeRoot '.runtime\postgresql\pgsql\bin\pg_ctl.exe'
$dataDir = Join-Path $runtimeRoot 'database\pgdata'
$logFile = Join-Path $runtimeRoot 'database\logs\postgresql.log'
if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'PG_VERSION'))) {
    throw 'Initialize first: python database/setup_postgres.py'
}
& $pgCtl status -D $dataDir *> $null
if ($LASTEXITCODE -eq 0) { Write-Output 'PostgreSQL is already running.'; return }
$startup = Start-Process -FilePath $pgCtl -ArgumentList @('start', '-D', "`"$dataDir`"", '-l', "`"$logFile`"", '-w', '-t', '30') -WindowStyle Hidden -PassThru -Wait
if ($startup.ExitCode -ne 0) { throw "PostgreSQL startup failed. See $logFile" }
Write-Output 'PostgreSQL started on 127.0.0.1:5432.'
