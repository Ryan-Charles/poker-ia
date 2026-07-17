$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$releaseRoot = Join-Path $root 'desktop\releases'
$exe = $null
if (Test-Path -LiteralPath $releaseRoot) {
    $exe = Get-ChildItem -LiteralPath $releaseRoot -Directory |
        Sort-Object Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'Poker IA\Poker IA.exe' } |
        Where-Object { Test-Path -LiteralPath $_ } |
        Select-Object -First 1
}
if (-not $exe) {
    $exe = Join-Path $root 'desktop\dist\Poker IA\Poker IA.exe'
}
if (Test-Path -LiteralPath $exe) {
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe)
    exit 0
}
. (Join-Path $PSScriptRoot 'runtime.ps1')
$python = Resolve-PokerIaRuntime python
$env:POKER_IA_PROJECT_ROOT = $root
$env:POKER_IA_DATA_DIR = Join-Path $root 'data'
& $python (Join-Path $root 'desktop\launcher.py')
