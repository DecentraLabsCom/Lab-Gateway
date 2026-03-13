param(
    [int]$Port = 8443,
    [string]$LabId = "lab-1",
    [string]$ReservationKey = "reservation-1",
    [string]$BearerToken = "",
    [int]$ExpectedFmuCount = 1,
    [string]$ProxyOutputPath = "",
    [switch]$SkipProxyDownload
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Split-Path (Split-Path $ScriptDir -Parent) -Parent
$LiveComposeFile = Join-Path $RepoRoot "docker-compose.yml"
$ArtifactsDir = Join-Path $ScriptDir "artifacts"

if (-not $ProxyOutputPath) {
    $ProxyOutputPath = Join-Path $ArtifactsDir "fmu-proxy-lab-$LabId.fmu"
}

$Passed = 0
$Failed = 0
$Skipped = 0
$BaseUrl = "https://127.0.0.1:$Port"
$SessionTicket = $null

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Log-Pass([string]$Message) {
    Write-Host "  PASS: $Message" -ForegroundColor Green
    $script:Passed++
}

function Log-Fail([string]$Message) {
    Write-Host "  FAIL: $Message" -ForegroundColor Red
    $script:Failed++
}

function Log-Skip([string]$Message) {
    Write-Host "  SKIP: $Message" -ForegroundColor Yellow
    $script:Skipped++
}

function Quote-CommandArg([string]$Value) {
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }

    return $Value
}

function Invoke-HttpJson {
    param(
        [string]$Uri,
        [string]$Method = "GET",
        [hashtable]$Headers = @{},
        [string]$Body = "",
        [string]$OutFile = ""
    )

    $headerFile = [System.IO.Path]::GetTempFileName()
    $bodyFile = [System.IO.Path]::GetTempFileName()
    $targetBodyFile = if ($OutFile -ne "") { $OutFile } else { $bodyFile }

    try {
        $argList = New-Object System.Collections.Generic.List[string]
        foreach ($arg in @("-k", "-sS", "-X", $Method, "-D", $headerFile, "-o", $targetBodyFile, "-w", "HTTP_STATUS:%{http_code}", $Uri)) {
            [void]$argList.Add([string]$arg)
        }

        foreach ($entry in $Headers.GetEnumerator()) {
            $argList.Add("-H")
            $argList.Add("$($entry.Key): $($entry.Value)")
        }

        if ($Body -ne "") {
            $argList.Add("-H")
            $argList.Add("Content-Type: application/json")
            $argList.Add("--data")
            $argList.Add($Body)
        }

        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = "curl.exe"
        $psi.Arguments = (($argList | ForEach-Object { Quote-CommandArg $_ }) -join " ")
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true

        $process = [System.Diagnostics.Process]::Start($psi)
        $stdout = $process.StandardOutput.ReadToEnd()
        $stderr = $process.StandardError.ReadToEnd()
        $process.WaitForExit()

        $statusCode = 0
        if ($stdout -match "HTTP_STATUS:(\d{3})") {
            $statusCode = [int]$Matches[1]
        }

        $responseBody = ""
        if ($OutFile -eq "" -and (Test-Path $bodyFile)) {
            $responseBody = Get-Content $bodyFile -Raw
        }

        return [pscustomobject]@{
            StatusCode = $statusCode
            Body = $responseBody
            Headers = if (Test-Path $headerFile) { Get-Content $headerFile -Raw } else { "" }
            Error = ([string]$stderr).Trim()
        }
    } finally {
        if (Test-Path $headerFile) {
            Remove-Item $headerFile -Force -ErrorAction SilentlyContinue
        }
        if ($OutFile -eq "" -and (Test-Path $bodyFile)) {
            Remove-Item $bodyFile -Force -ErrorAction SilentlyContinue
        }
    }
}

function Invoke-ComposeCapture {
    param([string[]]$ComposeArgs)

    $quotedArgs = @("compose", "-f", $LiveComposeFile) + $ComposeArgs

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "docker"
    $psi.Arguments = (($quotedArgs | ForEach-Object { Quote-CommandArg $_ }) -join " ")
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true

    $process = [System.Diagnostics.Process]::Start($psi)
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    $output = @($stdout, $stderr) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    $normalizedOutput = (($output -join "`n") -split "`r?`n" | Where-Object {
        $_ -notmatch '^time=".*level=warning msg="The .* variable is not set\. Defaulting to a blank string\."$'
    }) -join "`n"
    return [pscustomobject]@{
        ExitCode = $process.ExitCode
        Output = $normalizedOutput.Trim()
    }
}

function Parse-JsonOrNull([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return $null
    }

    try {
        return $Text | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Normalize-DescribeStartValue($Value) {
    if ($null -eq $Value) {
        return $null
    }
    if ($Value -is [System.Array]) {
        return (($Value | ForEach-Object { Normalize-DescribeStartValue $_ }) -join " ")
    }
    if ($Value -is [bool]) {
        return $Value.ToString().ToLowerInvariant()
    }
    return [string]$Value
}

function Normalize-VariableType([string]$TypeName, [string]$FmiVersion) {
    if ($FmiVersion -like "3*" -and $TypeName -eq "Integer") {
        return "Int32"
    }
    return $TypeName
}

function Get-ProxyModelDescriptionSnapshot([string]$ProxyPath) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ProxyPath)
    try {
        $entry = $archive.GetEntry("modelDescription.xml")
        if ($null -eq $entry) {
            throw "modelDescription.xml is missing from proxy artifact"
        }
        $reader = New-Object System.IO.StreamReader($entry.Open())
        try {
            [xml]$xml = $reader.ReadToEnd()
        } finally {
            $reader.Dispose()
        }
    } finally {
        $archive.Dispose()
    }

    $root = $xml.fmiModelDescription
    $variables = @{}
    foreach ($node in $root.ModelVariables.ChildNodes) {
        if ($node.NodeType -ne [System.Xml.XmlNodeType]::Element) {
            continue
        }
        $typeName = $node.LocalName
        $startValue = $null
        if ($node.LocalName -eq "ScalarVariable") {
            $typedChild = @($node.ChildNodes | Where-Object { $_ -is [System.Xml.XmlElement] })[0]
            if ($null -eq $typedChild) {
                continue
            }
            $typeName = $typedChild.LocalName
            if ($typedChild.Attributes["start"]) {
                $startValue = $typedChild.Attributes["start"].Value
            }
        } else {
            if ($node.Attributes["start"]) {
                $startValue = $node.Attributes["start"].Value
            }
        }
        $dimensions = @()
        foreach ($dimension in $node.ChildNodes | Where-Object { $_.NodeType -eq [System.Xml.XmlNodeType]::Element -and $_.Name -eq "Dimension" }) {
            $parts = @()
            foreach ($attrName in @("start", "valueReference", "variableName")) {
                if ($dimension.Attributes[$attrName]) {
                    $parts += "$attrName=$($dimension.Attributes[$attrName].Value)"
                }
            }
            $dimensions += ($parts -join ";")
        }
        $variables[$node.Attributes["name"].Value] = [ordered]@{
            name = $node.Attributes["name"].Value
            type = Normalize-VariableType $typeName $root.fmiVersion
            causality = if ($node.Attributes["causality"]) { $node.Attributes["causality"].Value } else { "local" }
            variability = if ($node.Attributes["variability"]) { $node.Attributes["variability"].Value } else { "continuous" }
            initial = if ($node.Attributes["initial"]) { $node.Attributes["initial"].Value } else { $null }
            start = $startValue
            dimensions = $dimensions
        }
    }

    return [pscustomobject]@{
        FmiVersion = [string]$root.fmiVersion
        Variables = $variables
    }
}

function Get-HashtableValue($Hashtable, [string]$Key) {
    if ($null -eq $Hashtable) {
        return $null
    }
    if ($Hashtable.Contains($Key)) {
        return $Hashtable[$Key]
    }
    return $null
}

function Assert-ComposeExecSuccess([string[]]$ComposeArgs, [string]$SuccessMessage, [string]$FailureMessage) {
    $result = Invoke-ComposeCapture -ComposeArgs $ComposeArgs
    if ($result.ExitCode -eq 0) {
        Log-Pass $SuccessMessage
        return $result.Output
    }

    Log-Fail "$FailureMessage`n$result.Output"
    return $null
}

if (-not (Test-Path $ArtifactsDir)) {
    New-Item -ItemType Directory -Path $ArtifactsDir | Out-Null
}

Write-Host "=================================================="
Write-Host "DecentraLabs Gateway - FMU Live Verification"
Write-Host "=================================================="
Write-Host "Repo root: $RepoRoot"
Write-Host "Base URL:  $BaseUrl"
Write-Host ""

$psResult = Invoke-ComposeCapture -ComposeArgs @("ps")
if ($psResult.ExitCode -eq 0) {
    Log-Pass "docker compose is reachable for the live stack"
} else {
    Log-Fail "docker compose is not reachable for the live stack`n$($psResult.Output)"
}

$healthResponse = Invoke-HttpJson -Uri "$BaseUrl/fmu/health"
$healthJson = Parse-JsonOrNull $healthResponse.Body
if ($healthResponse.StatusCode -eq 200 -and $healthJson -and $healthJson.status -eq "UP") {
    Log-Pass "FMU runner health is UP through the gateway"
} else {
    Log-Fail "Unexpected /fmu/health response: status=$($healthResponse.StatusCode) body=$($healthResponse.Body)"
}

if ($healthJson -and $null -ne $healthJson.fmuCount) {
    if ([int]$healthJson.fmuCount -ge $ExpectedFmuCount) {
        Log-Pass "FMU runner exposes $($healthJson.fmuCount) FMUs (expected at least $ExpectedFmuCount)"
    } else {
        Log-Fail "FMU runner exposes $($healthJson.fmuCount) FMUs, expected at least $ExpectedFmuCount"
    }
} else {
    Log-Fail "FMU runner health payload does not include fmuCount"
}

$runtimeFiles = Assert-ComposeExecSuccess `
    -ComposeArgs @("exec", "-T", "fmu-runner", "sh", "-lc", "find /app/fmu-proxy-runtime/binaries -maxdepth 2 -type f ! -name '.*' | sort") `
    -SuccessMessage "Connected to the fmu-runner container" `
    -FailureMessage "Could not inspect the fmu-runner container"

if ($null -ne $runtimeFiles) {
    if ([string]::IsNullOrWhiteSpace($runtimeFiles)) {
        Log-Fail "No proxy runtime binaries found in /app/fmu-proxy-runtime/binaries"
    } else {
        $runtimeList = $runtimeFiles -split "`r?`n" | Where-Object { $_ -like "/app/*" }
        if ($runtimeList.Count -gt 0) {
            Log-Pass "Proxy runtime binaries present: $($runtimeList.Count)"
        } else {
            Log-Fail "No proxy runtime binaries found in /app/fmu-proxy-runtime/binaries"
        }
    }
}

$fmuFiles = Assert-ComposeExecSuccess `
    -ComposeArgs @("exec", "-T", "fmu-runner", "sh", "-lc", "find /app/fmu-data -maxdepth 2 -type f -name '*.fmu' | sort") `
    -SuccessMessage "Connected to the FMU data directory inside fmu-runner" `
    -FailureMessage "Could not inspect /app/fmu-data inside fmu-runner"

if ($null -ne $fmuFiles) {
    if ([string]::IsNullOrWhiteSpace($fmuFiles)) {
        Log-Fail "No .fmu files found in /app/fmu-data"
    } else {
        $fmuList = $fmuFiles -split "`r?`n" | Where-Object { $_ -like "/app/*" }
        if ($fmuList.Count -gt 0) {
            Log-Pass "Provisioned FMUs present: $($fmuList.Count)"
        } else {
            Log-Fail "No .fmu files found in /app/fmu-data"
        }
    }
}

if ($fmuList -and $fmuList.Count -gt 0) {
    $expiryScript = Join-Path $ScriptDir "verify-fmu-session-expiry.ps1"
    if (Test-Path $expiryScript) {
        $shellPath = (Get-Process -Id $PID).Path
        $expiryAccessKey = [System.IO.Path]::GetFileName($fmuList[0])
        $expiryOutput = & $shellPath -NoProfile -ExecutionPolicy Bypass -File $expiryScript -Port $Port -LabId $LabId -AccessKey $expiryAccessKey 2>&1
        if ($LASTEXITCODE -eq 0) {
            Log-Pass "Forced expiry closes attached realtime sessions with reason=expired"
        } else {
            Log-Fail ("Forced expiry verification failed`n" + ($expiryOutput -join "`n"))
        }
    } else {
        Log-Skip "Forced expiry verification helper is missing"
    }
}

$issueWithoutAuth = Invoke-HttpJson -Uri "$BaseUrl/auth/fmu/session-ticket/issue" -Method "POST" -Body "{}"
$issueWithoutAuthJson = Parse-JsonOrNull $issueWithoutAuth.Body
if ($issueWithoutAuth.StatusCode -eq 401 -and $issueWithoutAuthJson.code -eq "UNAUTHORIZED") {
    Log-Pass "Session ticket issue endpoint is exposed and rejects missing bearer tokens with 401"
} else {
    Log-Fail "Unexpected issue response without auth: status=$($issueWithoutAuth.StatusCode) body=$($issueWithoutAuth.Body)"
}

$redeemWithoutTicket = Invoke-HttpJson -Uri "$BaseUrl/auth/fmu/session-ticket/redeem" -Method "POST" -Body "{}"
$redeemWithoutTicketJson = Parse-JsonOrNull $redeemWithoutTicket.Body
if ($redeemWithoutTicket.StatusCode -eq 400 -and $redeemWithoutTicketJson.code -eq "SESSION_TICKET_INVALID") {
    Log-Pass "Session ticket redeem endpoint is exposed and validates missing session tickets"
} else {
    Log-Fail "Unexpected redeem response without sessionTicket: status=$($redeemWithoutTicket.StatusCode) body=$($redeemWithoutTicket.Body)"
}

if ([string]::IsNullOrWhiteSpace($BearerToken)) {
    Log-Skip "Token-dependent checks skipped. Pass -BearerToken with a valid FMU booking JWT to verify issue, redeem and proxy download."
} else {
    $authHeaders = @{ Authorization = "Bearer $BearerToken" }
    $issueBody = @{
        labId = $LabId
        reservationKey = $ReservationKey
    } | ConvertTo-Json -Compress

    $issueWithAuth = Invoke-HttpJson -Uri "$BaseUrl/auth/fmu/session-ticket/issue" -Method "POST" -Headers $authHeaders -Body $issueBody
    $issueWithAuthJson = Parse-JsonOrNull $issueWithAuth.Body
    if ($issueWithAuth.StatusCode -eq 200 -and $issueWithAuthJson.sessionTicket) {
        $SessionTicket = [string]$issueWithAuthJson.sessionTicket
        Log-Pass "Session ticket issued successfully for labId=$LabId reservationKey=$ReservationKey"
    } else {
        Log-Fail "Session ticket issue failed: status=$($issueWithAuth.StatusCode) body=$($issueWithAuth.Body)"
    }

    if ($SessionTicket) {
        $redeemBody = @{
            sessionTicket = $SessionTicket
            labId = $LabId
            reservationKey = $ReservationKey
        } | ConvertTo-Json -Compress

        $redeemWithTicket = Invoke-HttpJson -Uri "$BaseUrl/auth/fmu/session-ticket/redeem" -Method "POST" -Body $redeemBody
        $redeemWithTicketJson = Parse-JsonOrNull $redeemWithTicket.Body
        $redeemClaims = $redeemWithTicketJson.claims

        if (
            $redeemWithTicket.StatusCode -eq 200 -and
            $redeemClaims -and
            [string]$redeemClaims.labId -eq $LabId -and
            [string]$redeemClaims.reservationKey -eq $ReservationKey
        ) {
            Log-Pass "Session ticket redeem returns claims for the expected labId and reservationKey"
        } else {
            Log-Fail "Session ticket redeem failed: status=$($redeemWithTicket.StatusCode) body=$($redeemWithTicket.Body)"
        }
    }

    if ($SkipProxyDownload) {
        Log-Skip "Proxy FMU download skipped by request"
    } else {
        if (Test-Path $ProxyOutputPath) {
            Remove-Item $ProxyOutputPath -Force
        }

        $proxyUri = "$BaseUrl/fmu/api/v1/fmu/proxy/${LabId}?reservationKey=$ReservationKey"
        $proxyResponse = Invoke-HttpJson -Uri $proxyUri -Headers $authHeaders -OutFile $ProxyOutputPath
        if ($proxyResponse.StatusCode -eq 200 -and (Test-Path $ProxyOutputPath)) {
            Log-Pass "Proxy FMU downloaded successfully to $ProxyOutputPath"
            try {
                $archive = [System.IO.Compression.ZipFile]::OpenRead($ProxyOutputPath)
                $entryNames = $archive.Entries | ForEach-Object { $_.FullName }
                $archive.Dispose()

                if ($entryNames -contains "modelDescription.xml") {
                    Log-Pass "Downloaded proxy FMU contains modelDescription.xml"
                } else {
                    Log-Fail "Downloaded proxy FMU is missing modelDescription.xml"
                }

                if ($entryNames -contains "resources/config.json") {
                    Log-Pass "Downloaded proxy FMU contains resources/config.json"
                } else {
                    Log-Fail "Downloaded proxy FMU is missing resources/config.json"
                }

                if (($entryNames | Where-Object { $_ -like "binaries/*/*" }).Count -gt 0) {
                    Log-Pass "Downloaded proxy FMU contains runtime binaries"
                } else {
                    Log-Fail "Downloaded proxy FMU does not contain runtime binaries"
                }

                $authorizedAccessKey = [string]$redeemClaims.accessKey
                if ([string]::IsNullOrWhiteSpace($authorizedAccessKey)) {
                    Log-Skip "Describe parity check skipped because redeem claims do not include accessKey"
                } else {
                    $describeUri = "$BaseUrl/fmu/api/v1/simulations/describe?fmuFileName=$([Uri]::EscapeDataString($authorizedAccessKey))"
                    $describeResponse = Invoke-HttpJson -Uri $describeUri -Headers $authHeaders
                    $describeJson = Parse-JsonOrNull $describeResponse.Body
                    if ($describeResponse.StatusCode -ne 200 -or $null -eq $describeJson) {
                        Log-Fail "Describe parity check failed to load /api/v1/simulations/describe: status=$($describeResponse.StatusCode) body=$($describeResponse.Body)"
                    } else {
                        $proxySnapshot = Get-ProxyModelDescriptionSnapshot -ProxyPath $ProxyOutputPath
                        $describeVariables = @{}
                        foreach ($variable in $describeJson.modelVariables) {
                            $dimensions = @()
                            foreach ($dimension in @($variable.dimensions)) {
                                $parts = @()
                                foreach ($attrName in @("start", "valueReference", "variableName")) {
                                    $dimensionValue = $dimension.$attrName
                                    if ($null -ne $dimensionValue -and [string]$dimensionValue -ne "") {
                                        $parts += "$attrName=$dimensionValue"
                                    }
                                }
                                $dimensions += ($parts -join ";")
                            }
                            $describeVariables[[string]$variable.name] = [ordered]@{
                                name = [string]$variable.name
                                type = Normalize-VariableType ([string]$variable.type) ([string]$describeJson.fmiVersion)
                                causality = [string]$variable.causality
                                variability = [string]$variable.variability
                                initial = if ($null -ne $variable.initial) { [string]$variable.initial } else { $null }
                                start = Normalize-DescribeStartValue $variable.start
                                dimensions = $dimensions
                            }
                        }

                        $parityErrors = New-Object System.Collections.Generic.List[string]
                        if ([string]$describeJson.fmiVersion -ne $proxySnapshot.FmiVersion) {
                            $parityErrors.Add("fmiVersion mismatch: describe=$($describeJson.fmiVersion) proxy=$($proxySnapshot.FmiVersion)")
                        }
                        $describeNames = @($describeVariables.Keys | Sort-Object)
                        $proxyNames = @($proxySnapshot.Variables.Keys | Sort-Object)
                        if (($describeNames -join ",") -ne ($proxyNames -join ",")) {
                            $parityErrors.Add("variable set mismatch")
                        } else {
                            foreach ($name in $describeNames) {
                                $describeVariable = $describeVariables[$name]
                                $proxyVariable = $proxySnapshot.Variables[$name]
                                foreach ($field in @("type", "causality", "variability", "initial", "start")) {
                                    $describeValue = Get-HashtableValue $describeVariable $field
                                    $proxyValue = Get-HashtableValue $proxyVariable $field
                                    if ($describeValue -ne $proxyValue) {
                                        $parityErrors.Add("variable '$name' mismatch on ${field}: describe='$($describeVariable[$field])' proxy='$($proxyVariable[$field])'")
                                    }
                                }
                                if ((($describeVariable["dimensions"] | Sort-Object) -join ",") -ne (($proxyVariable["dimensions"] | Sort-Object) -join ",")) {
                                    $parityErrors.Add("variable '$name' mismatch on dimensions")
                                }
                            }
                        }

                        if ($parityErrors.Count -eq 0) {
                            Log-Pass "Describe payload matches the generated proxy modelDescription.xml"
                        } else {
                            Log-Fail ("Describe/modelDescription parity failed`n" + ($parityErrors -join "`n"))
                        }
                    }
                }
            } catch {
                Log-Fail "Downloaded proxy FMU could not be inspected as a ZIP archive: $($_.Exception.Message)"
            }
        } else {
            Log-Fail "Proxy FMU download failed: status=$($proxyResponse.StatusCode) error=$($proxyResponse.Error)"
        }
    }
}

Write-Host ""
Write-Host "=================================================="
Write-Host "FMU Live Verification Summary"
Write-Host "=================================================="
Write-Host "  Passed:  $Passed" -ForegroundColor Green
Write-Host "  Failed:  $Failed" -ForegroundColor Red
Write-Host "  Skipped: $Skipped" -ForegroundColor Yellow
Write-Host "=================================================="

if ($Failed -gt 0) {
    exit 1
}

Write-Host ""
Write-Host "Live verification completed successfully." -ForegroundColor Green
