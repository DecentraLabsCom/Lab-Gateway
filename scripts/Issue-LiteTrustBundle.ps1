param(
    [Parameter(Mandatory = $true)][ValidatePattern('^https://')][string]$LitePublicOrigin,
    [Parameter(Mandatory = $true)][ValidatePattern('^https://')][string]$FullPublicOrigin,
    [string]$OutputFile
)

$ErrorActionPreference = 'Stop'
function Resolve-PublicOrigin([string]$Name, [string]$Value) {
    $uri = [Uri]$Value
    if (-not $uri.IsAbsoluteUri -or $uri.Scheme -ne 'https' -or [string]::IsNullOrWhiteSpace($uri.DnsSafeHost)) {
        throw "$Name must be an absolute https origin."
    }
    if (-not [string]::IsNullOrEmpty($uri.UserInfo) -or -not [string]::IsNullOrEmpty($uri.Query) -or
        -not [string]::IsNullOrEmpty($uri.Fragment) -or $uri.AbsolutePath -notin @('', '/')) {
        throw "$Name must not contain credentials, path, query or fragment."
    }
    $hostName = $uri.DnsSafeHost.TrimEnd('.').ToLowerInvariant()
    $origin = 'https://' + $hostName
    if (-not $uri.IsDefaultPort -and $uri.Port -ne 443) { $origin += ':' + $uri.Port }
    return @{ Origin = $origin; HostName = $hostName }
}

$lite = Resolve-PublicOrigin 'LitePublicOrigin' $LitePublicOrigin
$full = Resolve-PublicOrigin 'FullPublicOrigin' $FullPublicOrigin
$GatewayId = $lite.HostName
if ([string]::IsNullOrWhiteSpace($OutputFile)) { $OutputFile = "lite-trust-$GatewayId.env" }
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Configure the Full gateway before issuing a Lite trust bundle."
}

$values = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
$secretBytes = New-Object byte[](32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$secret = [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
$redeemerBytes = New-Object byte[](32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($redeemerBytes)
$redeemer = 'acr_' + [Convert]::ToHexString($redeemerBytes).ToLowerInvariant()
$credentials = @{}
if (-not [string]::IsNullOrWhiteSpace($values['SESSION_OBSERVER_CREDENTIALS_JSON'])) {
    $parsed = $values['SESSION_OBSERVER_CREDENTIALS_JSON'] | ConvertFrom-Json
    if ($parsed) {
        $parsed.PSObject.Properties | ForEach-Object { $credentials[$_.Name] = [string]$_.Value }
    }
}
$credentials[$GatewayId] = $secret
$values['SESSION_OBSERVER_CREDENTIALS_JSON'] = $credentials | ConvertTo-Json -Compress

$lines = @(Get-Content -LiteralPath $envFile)
$replacement = 'SESSION_OBSERVER_CREDENTIALS_JSON=' + $values['SESSION_OBSERVER_CREDENTIALS_JSON']
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^SESSION_OBSERVER_CREDENTIALS_JSON=') {
        $lines[$i] = $replacement
        $found = $true
    }
}
if (-not $found) { $lines += $replacement }
Set-Content -LiteralPath $envFile -Value $lines -Encoding Ascii

$redeemerCredentials = @{}
if (-not [string]::IsNullOrWhiteSpace($values['ACCESS_CODE_REDEEMER_CREDENTIALS_JSON'])) {
    $parsed = $values['ACCESS_CODE_REDEEMER_CREDENTIALS_JSON'] | ConvertFrom-Json
    if ($parsed) {
        $parsed.PSObject.Properties | ForEach-Object { $redeemerCredentials[$_.Name] = [string]$_.Value }
    }
}
$redeemerCredentials[$GatewayId.ToLowerInvariant()] = $redeemer
$redeemerReplacement = 'ACCESS_CODE_REDEEMER_CREDENTIALS_JSON=' + ($redeemerCredentials | ConvertTo-Json -Compress)
$lines = @(Get-Content -LiteralPath $envFile)
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^ACCESS_CODE_REDEEMER_CREDENTIALS_JSON=') {
        $lines[$i] = $redeemerReplacement
        $found = $true
    }
}
if (-not $found) { $lines += $redeemerReplacement }
Set-Content -LiteralPath $envFile -Value $lines -Encoding Ascii

$origin = $full.Origin
@(
    "ISSUER=$origin/auth"
    "SERVER_NAME=$GatewayId"
    "AUTH_ACCESS_CODE_REDEEMER_TOKEN=$redeemer"
    "ACCESS_AUDIT_URL=$origin/access-audit/internal/session-observed"
    "SESSION_OBSERVER_GATEWAY_ID=$GatewayId"
    "SESSION_OBSERVER_SIGNING_SECRET=$secret"
    "FMU_GATEWAY_ID=$GatewayId"
    "FMU_JWT_AUDIENCE=$($lite.Origin)/fmu"
    "AUTH_SESSION_TICKET_ISSUE_URL=$origin/auth/fmu/session-ticket/issue"
    "AUTH_SESSION_TICKET_REDEEM_URL=$origin/auth/fmu/session-ticket/redeem"
) | Set-Content -LiteralPath $OutputFile -Encoding Ascii

Write-Host "Created $OutputFile. Transfer it securely and delete it after Lite setup."
Write-Host 'Restart blockchain-services on Full so the new gateway credential is loaded.'
