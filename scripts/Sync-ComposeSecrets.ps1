[CmdletBinding()]
param(
    [string]$EnvFile = (Join-Path (Get-Location) '.env')
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $EnvFile -PathType Leaf)) {
    throw "Environment file not found: $EnvFile"
}

$rootDirectory = Split-Path -Parent (Resolve-Path -LiteralPath $EnvFile)
$secretsDirectory = Join-Path $rootDirectory 'secrets'
New-Item -ItemType Directory -Path $secretsDirectory -Force | Out-Null

$values = @{}
foreach ($line in Get-Content -LiteralPath $EnvFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $values[$matches[1]] = $matches[2]
    }
}

$secretMappings = [ordered]@{
    mysql_root_password = 'MYSQL_ROOT_PASSWORD'
    guacamole_mysql_password = 'GUACAMOLE_MYSQL_PASSWORD'
    blockchain_mysql_password = 'BLOCKCHAIN_MYSQL_PASSWORD'
    ops_backend_mysql_password = 'OPS_BACKEND_MYSQL_PASSWORD'
    ops_guacamole_mysql_password = 'OPS_GUACAMOLE_MYSQL_PASSWORD'
    guac_admin_pass = 'GUAC_ADMIN_PASS'
    admin_access_token = 'ADMIN_ACCESS_TOKEN'
    lab_manager_token = 'LAB_MANAGER_TOKEN'
    ops_internal_auth_token = 'OPS_INTERNAL_AUTH_TOKEN'
    ops_secrets_key = 'OPS_SECRETS_KEY'
    auth_access_code_redeemer_token = 'AUTH_ACCESS_CODE_REDEEMER_TOKEN'
    session_observation_ingest_token = 'SESSION_OBSERVATION_INGEST_TOKEN'
    guacamole_provisioner_token = 'GUACAMOLE_PROVISIONER_TOKEN'
    aas_service_token = 'AAS_SERVICE_TOKEN'
    lab_admin_backend_token = 'LAB_ADMIN_BACKEND_TOKEN'
    fmu_station_internal_token = 'FMU_STATION_INTERNAL_TOKEN'
    auth_session_ticket_internal_token = 'AUTH_SESSION_TICKET_INTERNAL_TOKEN'
    session_observer_signing_secret = 'SESSION_OBSERVER_SIGNING_SECRET'
    fmu_proxy_signing_key = 'FMU_PROXY_SIGNING_KEY'
}

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
foreach ($mapping in $secretMappings.GetEnumerator()) {
    $value = if ($values.ContainsKey($mapping.Value)) { $values[$mapping.Value] } else { '' }
    $target = Join-Path $secretsDirectory $mapping.Key
    [System.IO.File]::WriteAllText($target, $value, $utf8NoBom)
}

Write-Output "Compose secret files synchronized in $secretsDirectory."
