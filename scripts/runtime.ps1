$ErrorActionPreference = 'Stop'

function Resolve-PokerIaRuntime {
    param(
        [Parameter(Mandatory = $true)][ValidateSet('python', 'node', 'pnpm')][string]$Name,
        [switch]$SkipVenv
    )

    $projectRoot = Split-Path -Parent $PSScriptRoot
    $codexRuntime = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
    $candidates = switch ($Name) {
        'python' {
            $pythonCandidates = @()
            if (-not $SkipVenv) { $pythonCandidates += (Join-Path $projectRoot '.venv\Scripts\python.exe') }
            $pythonCandidates += @(
                (Join-Path $codexRuntime 'python\python.exe'),
                (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
                (Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
            )
            $pythonCandidates
        }
        'node' { @(
            (Join-Path $codexRuntime 'node\bin\node.exe'),
            (Get-Command node.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
        ) }
        'pnpm' { @(
            (Join-Path $codexRuntime 'bin\pnpm.cmd'),
            (Get-Command pnpm.cmd -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
            (Get-Command pnpm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue)
        ) }
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    throw "Runtime '$Name' introuvable. Exécutez scripts\Installer-Poker-IA.ps1 depuis PowerShell."
}
