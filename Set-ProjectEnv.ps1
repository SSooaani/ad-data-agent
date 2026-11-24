$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
foreach ($folder in @('.tmp', '.cache\pip', '.cache\npm', '.cache\huggingface', '.cache\torch', '.cache\sentence-transformers')) {
    New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot $folder) -Force | Out-Null
}
$env:VIRTUAL_ENV = Join-Path $PSScriptRoot '.venv'
$env:Path = (Join-Path $PSScriptRoot '.venv\Scripts') + ';' + (Join-Path $PSScriptRoot '.runtime\nodejs') + ';' + $env:Path
$env:PIP_CACHE_DIR = Join-Path $PSScriptRoot '.cache\pip'
$env:npm_config_cache = Join-Path $PSScriptRoot '.cache\npm'
$env:HF_HOME = Join-Path $PSScriptRoot '.cache\huggingface'
$env:TORCH_HOME = Join-Path $PSScriptRoot '.cache\torch'
$env:SENTENCE_TRANSFORMERS_HOME = Join-Path $PSScriptRoot '.cache\sentence-transformers'
$env:ANONYMIZED_TELEMETRY = 'False'
$env:DSH_HOME = Join-Path $PSScriptRoot '.dsh'
$env:TEMP = Join-Path $PSScriptRoot '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:Path = (Join-Path $PSScriptRoot '.runtime\postgresql\pgsql\bin') + ';' + $env:Path
