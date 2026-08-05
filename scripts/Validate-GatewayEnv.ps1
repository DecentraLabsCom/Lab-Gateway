param(
    [Parameter(Mandatory = $true)][string]$EnvPath
)

$ErrorActionPreference = 'Stop'

$values = @{}
Get-Content -LiteralPath $EnvPath | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}

function Read-JsonMap([string]$Key) {
    $raw = if ($values.ContainsKey($Key)) { $values[$Key] } else { '{}' }
    try {
        $json = if ([string]::IsNullOrWhiteSpace($raw)) { '{}' } else { $raw }
        $parsed = $json | ConvertFrom-Json
    } catch {
        throw "$Key must be a JSON object keyed by gateway ID"
    }
    $result = @{}
    if ($null -ne $parsed) {
        foreach ($property in $parsed.PSObject.Properties) {
            if ([string]::IsNullOrWhiteSpace($property.Name) -or
                [string]::IsNullOrWhiteSpace([string]$property.Value)) {
                throw "$Key must be a JSON object keyed by gateway ID"
            }
            $result[$property.Name.Trim().ToLowerInvariant()] = [string]$property.Value
        }
    }
    return $result
}

function Get-CanonicalGatewayId {
    $serverName = ([string]$values['SERVER_NAME']).Trim().TrimEnd('.').ToLowerInvariant()
    if ([string]::IsNullOrWhiteSpace($serverName)) {
        throw 'SERVER_NAME is required in Full mode'
    }
    $rawPort = ([string]$values['HTTPS_PORT']).Trim()
    if ([string]::IsNullOrWhiteSpace($rawPort)) { $rawPort = '443' }
    [int]$httpsPort = 0
    if (-not [int]::TryParse($rawPort, [ref]$httpsPort) -or $httpsPort -lt 1 -or $httpsPort -gt 65535) {
        throw 'HTTPS_PORT must be an integer between 1 and 65535'
    }
    if ($httpsPort -eq 443) { return $serverName }
    return "$serverName`:$httpsPort"
}

$redeemers = Read-JsonMap 'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON'
$observers = Read-JsonMap 'SESSION_OBSERVER_CREDENTIALS_JSON'

if (-not [string]::IsNullOrWhiteSpace($values['ISSUER'])) {
    exit 0
}

$gatewayId = Get-CanonicalGatewayId

$redeemer = ([string]$values['AUTH_ACCESS_CODE_REDEEMER_TOKEN']).Trim()
if ([string]::IsNullOrWhiteSpace($redeemer) -or $redeemer -in @('CHANGE_ME', 'changeme')) {
    throw 'AUTH_ACCESS_CODE_REDEEMER_TOKEN must be configured in Full mode'
}
if (-not $redeemers.ContainsKey($gatewayId) -or $redeemers[$gatewayId] -cne $redeemer) {
    throw 'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON must contain the canonical gateway ID (SERVER_NAME plus non-default HTTPS_PORT) mapped to AUTH_ACCESS_CODE_REDEEMER_TOKEN'
}

$observerId = ([string]$values['SESSION_OBSERVER_GATEWAY_ID']).Trim().TrimEnd('.').ToLowerInvariant()
if ($observerId -cne $gatewayId) {
    throw 'SESSION_OBSERVER_GATEWAY_ID must match the canonical gateway ID in Full mode'
}
$observerSecret = ([string]$values['SESSION_OBSERVER_SIGNING_SECRET']).Trim()
if ([string]::IsNullOrWhiteSpace($observerSecret) -or $observerSecret -in @('CHANGE_ME', 'changeme')) {
    throw 'SESSION_OBSERVER_SIGNING_SECRET must be configured in Full mode'
}
if (-not $observers.ContainsKey($gatewayId) -or $observers[$gatewayId] -cne $observerSecret) {
    throw 'SESSION_OBSERVER_CREDENTIALS_JSON must contain the canonical gateway ID (SERVER_NAME plus non-default HTTPS_PORT) mapped to SESSION_OBSERVER_SIGNING_SECRET'
}

$fmuGatewayId = ([string]$values['FMU_GATEWAY_ID']).Trim().TrimEnd('.').ToLowerInvariant()
if (-not [string]::IsNullOrWhiteSpace($fmuGatewayId) -and $fmuGatewayId -cne $gatewayId) {
    throw 'FMU_GATEWAY_ID must match the canonical gateway ID in Full mode'
}
