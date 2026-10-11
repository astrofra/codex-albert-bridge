#requires -Version 5.1
<#
.SYNOPSIS
Install Codex Albert Bridge for the current Windows user.
.DESCRIPTION
Requires Python 3.12 and Node.js 20+ (npm). Installs a private Codex CLI
and Python environment, without administrator rights or a startup service.
The Albert key is entered through a hidden prompt, never a script parameter.
#>
[CmdletBinding()]
param(
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'Programs\CodexAlbertBridge'),
    [string]$PythonExecutable,
    [string]$CodexVersion = '0.162.1',
    [ValidateRange(1024, 65535)][int]$Port = 8417,
    [switch]$SkipConfigure,
    [switch]$NoPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'This installer is for Windows. See README.md for macOS/Linux.' }
if ($CodexVersion -notmatch '^\d+\.\d+\.\d+([-.][A-Za-z0-9.-]+)?$') {
    throw 'CodexVersion must be an explicit npm version, not a URL or tag.'
}

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Executable" }
}

# Resolve a real Python executable, avoiding Microsoft Store aliases.
$pythonPath = $null
$candidates = @()
if ($PythonExecutable) {
    $candidates += ,@($PythonExecutable)
} else {
    if (Get-Command py.exe -ErrorAction SilentlyContinue) { $candidates += ,@('py.exe', '-3.12') }
    if (Get-Command python.exe -ErrorAction SilentlyContinue) { $candidates += ,@('python.exe') }
}
foreach ($candidate in $candidates) {
    $prefixArgs = @($candidate | Select-Object -Skip 1)
    try {
        $result = & ($candidate[0]) @prefixArgs -c 'import sys; assert sys.version_info[:2] == (3, 12); print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) { $pythonPath = [string]$result; break }
    } catch { continue }
}
if (-not $pythonPath) {
    throw 'Python 3.12 is required. Install it from python.org, or run: winget install --exact --id Python.Python.3.12. Then reopen PowerShell.'
}
$node = Get-Command node.exe -ErrorAction SilentlyContinue
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $node -or -not $npm) {
    throw 'Node.js 20+ and npm are required to install the private Codex CLI. Install Node.js LTS from nodejs.org and reopen PowerShell.'
}
$nodeMajor = & $node.Source -p 'process.versions.node.split(".")[0]'
if ($LASTEXITCODE -ne 0 -or [int]$nodeMajor -lt 20) { throw 'Node.js 20 or newer is required.' }

$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$marker = Join-Path $InstallDir 'bridge-install.json'
if ((Test-Path -LiteralPath $InstallDir) -and -not (Test-Path -LiteralPath $marker)) {
    throw 'InstallDir already exists and is not a bridge installation. Select a new directory.'
}
if (Test-Path -LiteralPath $marker) {
    $previousLauncher = Join-Path $InstallDir 'venv\Scripts\codex-albert.exe'
    if (Test-Path -LiteralPath $previousLauncher) {
        Invoke-Checked $previousLauncher @('stop')
    }
}
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
@{ product = 'codex-albert-bridge'; version = 1 } | ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
$venv = Join-Path $InstallDir 'venv'
$pythonInVenv = Join-Path $venv 'Scripts\python.exe'
$codexDir = Join-Path $InstallDir 'codex'
Invoke-Checked $pythonPath @('-m', 'venv', $venv)
Invoke-Checked $pythonInVenv @('-m', 'pip', '--isolated', 'install', '--upgrade', $PSScriptRoot)
Invoke-Checked $npm.Source @('install', '--prefix', $codexDir, '--no-audit', '--no-fund', '--save-exact', "@openai/codex@$CodexVersion")
# Launch the native executable directly, never a .cmd wrapper with user prompts.
$codexBinaries = @(Get-ChildItem -LiteralPath (Join-Path $codexDir 'node_modules') -Recurse -Filter codex.exe -File)
if ($codexBinaries.Count -ne 1) { throw 'Could not uniquely locate the installed native codex.exe.' }
$launcherDir = Join-Path $venv 'Scripts'
$launcher = Join-Path $launcherDir 'codex-albert.exe'
$configureArgs = @('configure', '--codex', $codexBinaries[0].FullName, '--port', [string]$Port)
if ($SkipConfigure) { $configureArgs += '--no-key' }
Invoke-Checked $launcher $configureArgs

if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
    $entries = @($userPath -split ';' | Where-Object { $_ })
    if ($entries -notcontains $launcherDir) {
        [Environment]::SetEnvironmentVariable('Path', (($entries + $launcherDir) -join ';'), 'User')
    }
    $env:Path = "$launcherDir;$env:Path"
}
Write-Host "Installed. Launcher: $launcher"
Write-Host 'Open a new terminal, run codex-albert doctor --check-api, then codex-albert in your project.'
Write-Host 'The gateway starts on demand. No administrator rights or global Codex changes were used.'
