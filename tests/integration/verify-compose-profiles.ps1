#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    # Configuration checks are always run. Runtime checks only inspect the
    # already running root stack and never start or tear it down.
    [switch]$Runtime,
    [switch]$SkipTooling,
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent (Split-Path -Parent $ScriptDir)
$ComposeFile = Join-Path $RootDir "docker-compose.yml"
$RootEnvFile = Join-Path $RootDir ".env"
$BackendEnvFile = Join-Path $RootDir "blockchain-services/.env"
$Profiles = @(
    "fmu-runner",
    "fmu-local-dev",
    "aas",
    "certbot",
    "cloudflare",
    "cloudflare-token"
)

if (-not (Test-Path -LiteralPath $RootEnvFile)) {
    throw "Missing $RootEnvFile. Run setup.bat or setup.sh first."
}
if (-not (Test-Path -LiteralPath $BackendEnvFile)) {
    throw "Missing $BackendEnvFile. Initialize the blockchain-services checkout first."
}

$PreviousBackendEnv = $env:BLOCKCHAIN_SERVICES_ENV_FILE
$PreviousComposeProfiles = $env:COMPOSE_PROFILES
$env:BLOCKCHAIN_SERVICES_ENV_FILE = $BackendEnvFile
$env:COMPOSE_PROFILES = ""

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    & docker compose --env-file $RootEnvFile -f $ComposeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Invoke-ComposeOutput {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)

    $output = @(& docker compose --env-file $RootEnvFile -f $ComposeFile @Arguments)
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
    return $output
}

function Assert-RunningRuntime {
    $running = @(Invoke-ComposeOutput @("ps", "--services", "--filter", "status=running"))
    foreach ($service in @("openresty", "ops-worker")) {
        if ($running -notcontains $service) {
            throw "Runtime check requires the '$service' service to be running."
        }
    }

    $published = @(Invoke-ComposeOutput @("port", "openresty", "443")) |
        Where-Object { $_ -and $_.Trim() } |
        Select-Object -First 1
    if (-not $published -or $published -notmatch ":(?<port>[0-9]+)$") {
        throw "Could not determine the published OpenResty HTTPS port."
    }
    $port = $Matches.port
    foreach ($path in @("/health", "/gateway/mode")) {
        $url = "https://127.0.0.1:$port$path"
        & curl.exe -kfsS --connect-timeout $TimeoutSeconds $url -H "Host: localhost" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime health request failed: $url"
        }
    }
    Write-Host "Running stack passed OpenResty /health and /gateway/mode checks." -ForegroundColor Green
}

try {
    Write-Host "Validating the base Compose configuration..."
    Invoke-Compose @("config", "-q")

    foreach ($profile in $Profiles) {
        Write-Host "Validating Compose profile: $profile"
        # Keep this explicit form visible in logs and suitable for copy/paste.
        Write-Host "docker compose --profile $profile config -q"
        Invoke-Compose @("--profile", $profile, "config", "-q")
    }

    if (-not $SkipTooling) {
        # These commands validate the optional images without starting a
        # public tunnel or requiring a Cloudflare account/token.
        Write-Host "Checking Certbot's no-op initialization path..."
        Invoke-Compose @("--profile", "certbot", "run", "--rm", "--no-deps", "certbot-init")
        Write-Host "Checking Cloudflare image availability..."
        Invoke-Compose @("--profile", "cloudflare", "run", "--rm", "--no-deps", "cloudflared", "--version")
        Invoke-Compose @("--profile", "cloudflare-token", "run", "--rm", "--no-deps", "cloudflared-token", "--version")
    }

    if ($Runtime) {
        Assert-RunningRuntime
    }

    Write-Host "Compose profile smoke checks passed." -ForegroundColor Green
}
finally {
    # `run --rm` removes its own one-shot containers. Do not call `down`: the
    # root stack may be shared with a developer session or another gate.
    $env:BLOCKCHAIN_SERVICES_ENV_FILE = $PreviousBackendEnv
    $env:COMPOSE_PROFILES = $PreviousComposeProfiles
}
