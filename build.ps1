param([string]$Python = '', [string]$DistPath = 'dist')
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not $Python) {
        $venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
        if (Test-Path -LiteralPath $venvPython) { $Python = $venvPython }
        else { $Python = (Get-Command python -ErrorAction Stop).Source }
    }
    & $Python -m PyInstaller --noconfirm --distpath $DistPath 'Melonbooks Downloader.spec'
    if ($LASTEXITCODE -ne 0) { throw 'Executable build failed.' }
} finally { Pop-Location }
