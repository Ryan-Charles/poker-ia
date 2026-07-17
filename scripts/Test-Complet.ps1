$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'runtime.ps1')
$python = Resolve-PokerIaRuntime python
$pnpm = Resolve-PokerIaRuntime pnpm
$env:PATH = "$(Split-Path -Parent (Resolve-PokerIaRuntime node));$env:PATH"
$env:NODE_OPTIONS = '--use-system-ca'

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$Label
    )
    Write-Host "`n[$Label]" -ForegroundColor Cyan
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Label a échoué avec le code $LASTEXITCODE."
    }
}

Push-Location (Join-Path $root 'backend')
try {
    Invoke-Checked $python @('-m', 'alembic', 'upgrade', 'head') 'Migrations Alembic'
    Invoke-Checked $python @('-m', 'pytest', '-q') 'Tests Pytest'
    Invoke-Checked $python @('-m', 'ruff', 'check', 'app', 'tests', '..\scripts\Mesurer-Performances.py', '..\desktop\launcher.py') 'Lint Ruff'
    Invoke-Checked $python @('-m', 'ruff', 'format', '--check', 'app', 'tests', '..\scripts\Mesurer-Performances.py', '..\desktop\launcher.py') 'Format Ruff'
    Invoke-Checked $python @('-m', 'mypy', 'app') 'Typage MyPy'
} finally { Pop-Location }

Push-Location (Join-Path $root 'frontend')
try {
    Invoke-Checked $pnpm @('typecheck') 'TypeScript strict'
    Invoke-Checked $pnpm @('lint') 'Lint ESLint'
    Invoke-Checked $pnpm @('format:check') 'Format Prettier'
    Invoke-Checked $pnpm @('test') 'Tests Vitest'
    Invoke-Checked $pnpm @('build') 'Build Vite'
    Invoke-Checked $pnpm @('test:e2e') 'Scénarios Playwright'
} finally { Pop-Location }

Write-Host "`nValidation complète réussie." -ForegroundColor Green
