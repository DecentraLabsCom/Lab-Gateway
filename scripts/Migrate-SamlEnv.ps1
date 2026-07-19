param(
    [Parameter(Mandatory = $true)][string]$EnvPath,
    [Parameter(Mandatory = $true)][string]$TemplatePath
)

$ErrorActionPreference = 'Stop'

function Read-EnvAssignments([string]$Path) {
    $values = @{}
    if (Test-Path -LiteralPath $Path) {
        foreach ($line in Get-Content -LiteralPath $Path) {
            if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
                $values[$Matches[1]] = $Matches[2]
            }
        }
    }
    return $values
}

function Set-EnvAssignment([System.Collections.Generic.List[string]]$Lines, [string]$Key, [string]$Value) {
    $prefix = "$Key="
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        if ($Lines[$index].StartsWith($prefix, [System.StringComparison]::Ordinal)) {
            $Lines[$index] = "$Key=$Value"
            return
        }
    }
    $Lines.Add("$Key=$Value")
}

$envValues = Read-EnvAssignments $EnvPath
$templateValues = Read-EnvAssignments $TemplatePath
$lines = [System.Collections.Generic.List[string]]::new()
if (Test-Path -LiteralPath $EnvPath) {
    foreach ($line in Get-Content -LiteralPath $EnvPath) { $lines.Add($line) }
}
$changed = $false

foreach ($key in @('SAML_IDP_METADATA_OVERRIDE', 'SAML_IDP_METADATA_TLS_PROFILE')) {
    if (-not $templateValues.ContainsKey($key)) { continue }
    if (-not $envValues.ContainsKey($key)) {
        Set-EnvAssignment $lines $key $templateValues[$key]
        $changed = $true
        continue
    }
    try {
        $existing = if ([string]::IsNullOrWhiteSpace($envValues[$key])) { [pscustomobject]@{} } else { $envValues[$key] | ConvertFrom-Json }
        $template = if ([string]::IsNullOrWhiteSpace($templateValues[$key])) { [pscustomobject]@{} } else { $templateValues[$key] | ConvertFrom-Json }
        $merged = [ordered]@{}
        $template.psobject.Properties | ForEach-Object { $merged[$_.Name] = $_.Value }
        $existing.psobject.Properties | ForEach-Object { $merged[$_.Name] = $_.Value }
        $value = $merged | ConvertTo-Json -Compress
    } catch {
        throw "SAML map $key is not valid JSON: $($_.Exception.Message)"
    }
    if ($value -ne $envValues[$key]) {
        Set-EnvAssignment $lines $key $value
        $changed = $true
    }
}

if (-not $envValues.ContainsKey('SAML_METADATA_HEALTH_CACHE_MS') -and $templateValues.ContainsKey('SAML_METADATA_HEALTH_CACHE_MS')) {
    Set-EnvAssignment $lines 'SAML_METADATA_HEALTH_CACHE_MS' $templateValues['SAML_METADATA_HEALTH_CACHE_MS']
    $changed = $true
}

if ($changed) {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText((Resolve-Path -LiteralPath $EnvPath), (($lines -join [Environment]::NewLine) + [Environment]::NewLine), $utf8)
    Write-Output 'SAML environment migration applied.'
} else {
    Write-Output 'SAML environment already current.'
}
