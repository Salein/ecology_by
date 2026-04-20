param(
    [switch]$Deep,
    [switch]$NoBuild,
    [switch]$NoPruneBuilder,
    [switch]$NoPruneSystem,
    [switch]$NoUp,
    [ValidateSet("none", "tunnel", "tunnel-token")]
    [string]$Profile = "none"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Text)
    Write-Host ""
    Write-Host "==> $Text" -ForegroundColor Cyan
}

function Invoke-Docker {
    param([string]$Command)
    Write-Host ">> $Command" -ForegroundColor DarkGray
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed (exit code $LASTEXITCODE): $Command"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Step "Stopping and removing project containers"
Invoke-Docker "docker compose down --remove-orphans"

if (-not $NoPruneBuilder) {
    Write-Step "Pruning Docker build cache"
    Invoke-Docker "docker builder prune -f"
}

if (-not $NoPruneSystem) {
    if ($Deep) {
        Write-Step "Deep Docker prune (images + volumes)"
        Invoke-Docker "docker system prune -a --volumes -f"
    }
    else {
        Write-Step "Safe Docker prune (without volumes)"
        Invoke-Docker "docker system prune -f"
    }
}

if ($NoUp) {
    Write-Step "Compose up skipped by -NoUp"
    exit 0
}

$profileArg = ""
if ($Profile -ne "none") {
    $profileArg = "--profile $Profile"
}

$buildArg = "--build"
if ($NoBuild) {
    $buildArg = ""
}

Write-Step "Starting project with docker compose"
$upCmd = "docker compose $profileArg up -d $buildArg".Trim()
Invoke-Docker $upCmd

Write-Step "Done"
Write-Host "Project is up. Verify with: docker compose ps" -ForegroundColor Green
