$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    Write-Host "[$Label]" -ForegroundColor DarkCyan
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label a échoué avec le code $LASTEXITCODE."
    }
}

Write-Host 'Installation de Poker IA…' -ForegroundColor Cyan
$venvDir = Join-Path $root '.venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
$bootstrapPython = Resolve-PokerIaRuntime python -SkipVenv
if (-not (Test-Path -LiteralPath $venvPython)) {
    Invoke-Checked $bootstrapPython @('-m', 'venv', '--without-pip', $venvDir) 'Création de l’environnement Python'
}
if (-not (Test-Path -LiteralPath (Join-Path $venvDir 'Scripts\pip.exe'))) {
    # Le runtime embarqué de Codex peut créer le venv sans parvenir à exécuter
    # ensurepip dans son sous-processus. pip sait cibler directement ce venv.
    Invoke-Checked $bootstrapPython @('-m', 'pip', '--python', $venvDir, 'install', '--upgrade', 'pip') 'Installation de pip'
}
Invoke-Checked $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip') 'Mise à jour de pip'
Invoke-Checked $venvPython @('-m', 'pip', 'install', '-r', (Join-Path $root 'backend\requirements.txt')) 'Dépendances backend'
Invoke-Checked $venvPython @('-m', 'pip', 'install', 'pywebview', 'pyinstaller', 'pillow') 'Dépendances application Windows'

Push-Location (Join-Path $root 'backend')
try {
    Invoke-Checked $venvPython @('-m', 'alembic', 'upgrade', 'head') 'Migrations Alembic'
} finally { Pop-Location }

$pnpm = Resolve-PokerIaRuntime pnpm
$env:PATH = "$(Split-Path -Parent (Resolve-PokerIaRuntime node));$env:PATH"
$env:NODE_OPTIONS = '--use-system-ca'
Push-Location (Join-Path $root 'frontend')
try {
    Invoke-Checked $pnpm @('install', '--frozen-lockfile=false') 'Dépendances frontend'
    Invoke-Checked $pnpm @('exec', 'playwright', 'install', 'chromium') 'Navigateur Playwright'
    Invoke-Checked $pnpm @('build') 'Build frontend'
} finally { Pop-Location }

Write-Host 'Création de l’application Windows…' -ForegroundColor Cyan
$pyInstallerWork = Join-Path ([IO.Path]::GetTempPath()) "Poker-IA-PyInstaller-$PID"
$releaseTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$releaseDist = Join-Path $root "desktop\releases\$releaseTag"
Push-Location (Join-Path $root 'desktop')
try {
    $pyInstallerArguments = @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--name', 'Poker IA',
        '--workpath', $pyInstallerWork,
        '--distpath', $releaseDist,
        '--specpath', (Join-Path $root 'desktop'),
        '--icon', (Join-Path $root 'desktop\Poker IA.ico'),
        '--paths', (Join-Path $root 'backend'),
        '--add-data', "$(Join-Path $root 'frontend\dist');frontend\dist",
        '--collect-submodules', 'app',
        '--hidden-import', 'app.main',
        '--hidden-import', 'aiosqlite',
        '--hidden-import', 'webview.platforms.edgechromium',
        '--hidden-import', 'webview.platforms.winforms',
        (Join-Path $root 'desktop\launcher.py')
    )
    Invoke-Checked $venvPython $pyInstallerArguments 'Packaging PyInstaller'
} finally {
    Pop-Location
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedWork = [IO.Path]::GetFullPath($pyInstallerWork)
    if ($resolvedWork.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedWork -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$exe = Join-Path $releaseDist 'Poker IA\Poker IA.exe'
if (-not (Test-Path -LiteralPath $exe)) { throw "L'exécutable n'a pas été créé : $exe" }

$smokeData = Join-Path ([IO.Path]::GetTempPath()) "Poker-IA-Smoke-$PID"
$previousSmoke = $env:POKER_IA_SMOKE_TEST
$previousData = $env:POKER_IA_DATA_DIR
try {
    $env:POKER_IA_SMOKE_TEST = '1'
    $env:POKER_IA_DATA_DIR = $smokeData
    Invoke-Checked -FilePath $exe -Arguments @() -Label 'Auto-test de l’exécutable Windows'
} finally {
    if ($null -eq $previousSmoke) { Remove-Item Env:POKER_IA_SMOKE_TEST -ErrorAction SilentlyContinue }
    else { $env:POKER_IA_SMOKE_TEST = $previousSmoke }
    if ($null -eq $previousData) { Remove-Item Env:POKER_IA_DATA_DIR -ErrorAction SilentlyContinue }
    else { $env:POKER_IA_DATA_DIR = $previousData }
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $resolvedSmoke = [IO.Path]::GetFullPath($smokeData)
    if ($resolvedSmoke.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force -ErrorAction SilentlyContinue
    }
}

$desktop = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktop 'Poker IA.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = Split-Path -Parent $exe
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = 'Poker IA — entraînement No-Limit Texas Hold’em fictif'
$shortcut.Save()

Write-Host "Installation terminée. Raccourci : $shortcutPath" -ForegroundColor Green
