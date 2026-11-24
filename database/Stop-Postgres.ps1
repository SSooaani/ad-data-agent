$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $root 'Set-ProjectEnv.ps1')
$runtimeRoot = & (Join-Path $root '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'postgres_paths.py')
if ($LASTEXITCODE -ne 0) { throw 'Cannot prepare PostgreSQL path alias.' }
& (Join-Path $runtimeRoot '.runtime\postgresql\pgsql\bin\pg_ctl.exe') stop -D (Join-Path $runtimeRoot 'database\pgdata') -m fast -w
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL shutdown failed.' }
