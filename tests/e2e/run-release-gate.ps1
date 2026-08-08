[CmdletBinding()]
param(
    [string]$ProjectName = "decentralabs-release-gate-$PID",
    [int]$TimeoutSeconds = 180,
    [switch]$KeepStack
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$composeFile = Join-Path $scriptRoot "docker-compose.release-gate.yml"

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & docker compose -p $ProjectName -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

try {
    $env:RELEASE_GATE_ENABLED = "1"
    $env:COMPOSE_FILE = $composeFile
    $env:COMPOSE_PROJECT_NAME = $ProjectName
    $env:REDIS_REST_URL = "http://127.0.0.1:16380"
    $env:REDIS_REST_TOKEN = if ($env:REDIS_REST_TOKEN) { $env:REDIS_REST_TOKEN } else { "release-gate-token" }
    $env:ANVIL_RPC_URL = "http://127.0.0.1:18545"
    $env:MYSQL_TEST_ENABLED = "1"
    $env:MYSQL_TEST_USER = "release_gate"
    $env:MYSQL_TEST_PASSWORD = "release-gate-password"
    $env:MYSQL_TEST_DATABASE = "blockchain_services"

    Invoke-Compose up --build --detach --wait --wait-timeout $TimeoutSeconds

    python (Join-Path $scriptRoot "release_gate.py")
    if ($LASTEXITCODE -ne 0) { throw "Release gate failed with exit code $LASTEXITCODE" }
}
finally {
    if (-not $KeepStack) {
        & docker compose -p $ProjectName -f $composeFile down --volumes --remove-orphans | Out-Host
    }
}
