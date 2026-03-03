# =================================================================
# FMU Integration Test Suite for DecentraLabs Gateway (PowerShell)
# Tests FMU Runner routing, authentication, concurrency, and timeout
# =================================================================
param(
    [int]$Port = 18443
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ComposeFile = Join-Path $ScriptDir "docker-compose.fmu-integration.yml"
$CertsDir = Join-Path $ScriptDir "certs"
$Passed = 0
$Failed = 0
$BaseUrl = "https://127.0.0.1:$Port"
$AuthHeaders = @{ Authorization = "Bearer integration-test-jwt" }

function Log-Pass([string]$msg) { Write-Host "  PASS: $msg" -ForegroundColor Green; $script:Passed++ }
function Log-Fail([string]$msg) { Write-Host "  FAIL: $msg" -ForegroundColor Red; $script:Failed++ }

function Invoke-Curl {
    param([string[]]$Args)
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "curl"
    $psi.Arguments = $Args -join " "
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $p = [System.Diagnostics.Process]::Start($psi)
    $stdout = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit(30000)
    return $stdout
}

function Wait-Service([string]$url, [int]$maxAttempts = 30) {
    for ($i = 0; $i -lt $maxAttempts; $i++) {
        try {
            $null = Invoke-WebRequest -Uri $url -TimeoutSec 3 -ErrorAction SilentlyContinue
            return $true
        } catch { }
        Start-Sleep -Seconds 2
    }
    return $false
}

# Cleanup on exit
$cleanup = {
    Write-Host "`nCleaning up..." -ForegroundColor Yellow
    try {
        docker compose -f $ComposeFile down -v | Out-Null
    } catch {
        # Best-effort cleanup
    }
}

try {
    Write-Host "=================================================="
    Write-Host "DecentraLabs Gateway - FMU Integration Tests"
    Write-Host "=================================================="

    # Generate certs if needed
    $privKeyPath = Join-Path $CertsDir "privkey.pem"
    $fullChainPath = Join-Path $CertsDir "fullchain.pem"
    $publicKeyPath = Join-Path $CertsDir "public_key.pem"
    if (
        -not (Test-Path $privKeyPath) -or
        -not (Test-Path $fullChainPath) -or
        -not (Test-Path $publicKeyPath)
    ) {
        if ((Test-Path $privKeyPath) -and (Test-Path $fullChainPath) -and -not (Test-Path $publicKeyPath)) {
            $opensslCmd = Get-Command openssl -ErrorAction SilentlyContinue
            if ($opensslCmd) {
                Write-Host "Generating public key from existing integration private key..." -ForegroundColor Yellow
                & $opensslCmd.Source rsa -in $privKeyPath -pubout -out $publicKeyPath | Out-Null
            } else {
                $fallbackPublic = Join-Path (Join-Path (Split-Path $ScriptDir -Parent) "smoke\\certs") "public_key.pem"
                if (Test-Path $fallbackPublic) {
                    Write-Host "openssl not found; using fallback public key from smoke certs." -ForegroundColor Yellow
                    Copy-Item -Path $fallbackPublic -Destination $publicKeyPath -Force
                } else {
                    throw "Missing public_key.pem and openssl is not available to derive it."
                }
            }
        } else {
            Write-Host "Generating test certificates..." -ForegroundColor Yellow
            $bashCmd = Get-Command bash -ErrorAction SilentlyContinue
            if (-not $bashCmd) {
                throw "bash is required to generate integration certs from scratch (tests/integration/certs/generate-certs.sh)"
            }
            Push-Location $CertsDir
            & $bashCmd.Source "generate-certs.sh"
            Pop-Location
        }
    }

    # Start services
    Write-Host "`nStarting services..." -ForegroundColor Yellow
    docker compose -f $ComposeFile up --build -d
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }

    Write-Host "Waiting for services to be ready..."
    if (-not (Wait-Service "$BaseUrl/fmu/health" 90)) {
        Write-Host "Services failed to start" -ForegroundColor Red
        docker compose -f $ComposeFile logs
        exit 1
    }
    Start-Sleep -Seconds 3
    Write-Host "Services ready`n" -ForegroundColor Green

    # Reset FMU Runner state
    try { $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/_test/reset" -ErrorAction SilentlyContinue } catch {}

    # === Test 1: FMU Runner health ===
    Write-Host "Test 1: FMU Runner health through gateway"
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/fmu/health"
        if ($resp.Content -match '"UP"') { Log-Pass "FMU Runner health accessible through /fmu/health" }
        else { Log-Fail "FMU health unexpected: $($resp.Content)" }
    } catch { Log-Fail "FMU health not accessible: $_" }

    # === Test 2: Describe endpoint ===
    Write-Host "Test 2: Simulation describe endpoint"
    try {
        $resp = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/describe?fmuFileName=test.fmu" -Headers $AuthHeaders
        $body = $resp.Content
        if ($body -match '"fmiVersion"') { Log-Pass "Describe returns FMU metadata" }
        else { Log-Fail "Describe missing fmiVersion: $body" }
        if ($body -match '"CoSimulation"') { Log-Pass "Describe reports correct simulation type" }
        else { Log-Fail "Describe missing simulation type: $body" }
        if ($body -match '"modelVariables"') { Log-Pass "Describe includes model variables" }
        else { Log-Fail "Describe missing model variables: $body" }
    } catch { Log-Fail "Describe endpoint failed: $_" }

    # === Test 3: Run endpoint ===
    Write-Host "Test 3: Simulation run endpoint"
    try {
        $runBody = '{"labId":"lab-1","parameters":{"mass":1.5},"options":{"startTime":0,"stopTime":10,"stepSize":0.01}}'
        $resp = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/run" -Method POST -Body $runBody `
            -ContentType "application/json" -Headers $AuthHeaders
        $body = $resp.Content
        if ($body -match '"completed"') { Log-Pass "Run endpoint executes simulation" }
        else { Log-Fail "Run missing 'completed': $body" }
        if ($body -match '"position"') { Log-Pass "Run results contain output variables" }
        else { Log-Fail "Run missing output variables: $body" }
    } catch { Log-Fail "Run endpoint failed: $_" }

    # === Test 4: Describe validation ===
    Write-Host "Test 4: Describe validation - missing fmuFileName"
    try {
        $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/describe" -Headers $AuthHeaders -ErrorAction Stop
        Log-Fail "Describe should reject without fmuFileName"
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -eq 422) { Log-Pass "Describe rejects without fmuFileName (422)" }
        else { Log-Fail "Describe expected 422, got: $($_.Exception.Response.StatusCode.value__)" }
    }

    # === Test 5: Run validation - invalid JSON ===
    Write-Host "Test 5: Run validation - invalid JSON"
    try {
        $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/run" -Method POST -Body "not-json" `
            -ContentType "application/json" -Headers $AuthHeaders -ErrorAction Stop
        Log-Fail "Run should reject invalid JSON"
    } catch {
        $sc = $_.Exception.Response.StatusCode.value__
        if ($sc -eq 400 -or $sc -eq 422) { Log-Pass "Run rejects invalid JSON ($sc)" }
        else { Log-Fail "Run expected 400/422, got: $sc" }
    }

    # === Test 6: Concurrency limit ===
    Write-Host "Test 6: Concurrency limit enforcement"
    try { $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/_test/reset" -ErrorAction SilentlyContinue } catch {}

    $concBody = '{"labId":"conc-test","parameters":{},"options":{"startTime":0,"stopTime":1,"stepSize":0.1}}'
    $authToken = "Bearer integration-test-jwt"
    $jobs = @()
    1..3 | ForEach-Object {
        $jobs += Start-Job -ScriptBlock {
            param($url, $body, $token)
            try {
                $headers = @{ Authorization = $token }
                $r = Invoke-WebRequest -Uri $url -Method POST -Body $body -ContentType "application/json" -Headers $headers -ErrorAction Stop
                return $r.StatusCode
            } catch {
                return $_.Exception.Response.StatusCode.value__
            }
        } -ArgumentList "$BaseUrl/fmu/api/v1/simulations/run", $concBody, $authToken
    }
    $results = $jobs | Wait-Job | Receive-Job
    $jobs | Remove-Job -Force

    $count200 = ($results | Where-Object { $_ -eq 200 }).Count
    $count429 = ($results | Where-Object { $_ -eq 429 }).Count
    if ($count429 -ge 1 -and $count200 -ge 2) {
        Log-Pass "Concurrency: $count200 succeeded, $count429 rejected (429)"
    } else {
        Log-Fail "Concurrency not enforced: results=$($results -join ', ') (expected >=2x200, >=1x429)"
    }

    # === Test 7: Timeout simulation ===
    Write-Host "Test 7: Simulation timeout"
    try {
        $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/run?simulateTimeout=2" -Method POST `
            -Body '{"labId":"timeout-test","parameters":{},"options":{}}' -ContentType "application/json" `
            -Headers $AuthHeaders -TimeoutSec 15 -ErrorAction Stop
        Log-Fail "Timeout test should return 504"
    } catch {
        $sc = $_.Exception.Response.StatusCode.value__
        if ($sc -eq 504) { Log-Pass "Simulation timeout returns 504" }
        else { Log-Fail "Timeout expected 504, got: $sc" }
    }

    # === Test 8: Header propagation ===
    Write-Host "Test 8: Header propagation"
    try { $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/_test/reset" -ErrorAction SilentlyContinue } catch {}
    try {
        $null = Invoke-WebRequest -Uri "$BaseUrl/fmu/api/v1/simulations/run" -Method POST `
            -Body '{"labId":"header-test","parameters":{},"options":{}}' -ContentType "application/json" `
            -Headers $AuthHeaders -ErrorAction SilentlyContinue
    } catch {}

    try {
        $logResp = Invoke-WebRequest -Uri "$BaseUrl/fmu/_test/request-log"
        $logBody = $logResp.Content
        if ($logBody -match "x-real-ip|x-forwarded-for") { Log-Pass "OpenResty propagates X-Real-IP / X-Forwarded-For" }
        else { Log-Fail "Headers not propagated: $logBody" }

        # === Test 9: URI rewrite ===
        Write-Host "Test 9: URI rewrite (/fmu/ prefix stripped)"
        if ($logBody -match '"/api/v1/simulations/run"') { Log-Pass "URI correctly rewritten from /fmu/api/... to /api/..." }
        else { Log-Fail "URI not rewritten correctly: $logBody" }
    } catch {
        Log-Fail "Request log not accessible: $_"
        Write-Host "Test 9: URI rewrite"
        Log-Fail "Cannot check URI rewrite (request log unavailable)"
    }

} finally {
    & $cleanup
}

# Summary
Write-Host ""
Write-Host "=================================================="
Write-Host "FMU Integration Test Results"
Write-Host "=================================================="
Write-Host "  Passed: $Passed" -ForegroundColor Green
Write-Host "  Failed: $Failed" -ForegroundColor Red
Write-Host "=================================================="

if ($Failed -gt 0) { exit 1 }

Write-Host "`nAll FMU integration tests passed!" -ForegroundColor Green
