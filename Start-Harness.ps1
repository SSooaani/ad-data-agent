param([switch]$NoOpen)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'Set-ProjectEnv.ps1')
$launcherArgs = @('--yes', '@deepseek-ai/dsh@0.2.2-rc.5', 'web', '--host', '127.0.0.1', '--port', '3080')
if ($NoOpen) { $launcherArgs += '--no-open' }
& (Join-Path $PSScriptRoot '.runtime\nodejs\npx.cmd') @launcherArgs
exit $LASTEXITCODE
