param(
    [Parameter(Mandatory = $true)][ValidatePattern('^[A-Za-z0-9._-]{3,128}$')][string]$GatewayId,
    [Parameter(Mandatory = $true)][ValidatePattern('^https://')][string]$FullPublicOrigin,
    [string]$OutputFile = "lite-trust-$GatewayId.env"
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $root '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Configure the Full gateway before issuing a Lite trust bundle."
}

$values = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
$redeemer = $values['AUTH_ACCESS_CODE_REDEEMER_TOKEN']
if ([string]::IsNullOrWhiteSpace($redeemer) -or $redeemer -eq 'CHANGE_ME') {
    throw 'Full gateway access-code redeemer credential is not configured.'
}

$secretBytes = New-Object byte[](32)
[System.Security.Cryptography.RandomNumberGenerator]::Fill($secretBytes)
$secret = [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
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

$origin = $FullPublicOrigin.TrimEnd('/')
@(
    "ISSUER=$origin/auth"
    "AUTH_ACCESS_CODE_REDEEMER_TOKEN=$redeemer"
    "ACCESS_AUDIT_URL=$origin/access-audit/internal/session-observed"
    "SESSION_OBSERVER_GATEWAY_ID=$GatewayId"
    "SESSION_OBSERVER_SIGNING_SECRET=$secret"
) | Set-Content -LiteralPath $OutputFile -Encoding Ascii

Write-Host "Created $OutputFile. Transfer it securely and delete it after Lite setup."
Write-Host 'Restart blockchain-services on Full so the new gateway credential is loaded.'
