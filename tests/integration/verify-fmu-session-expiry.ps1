param(
    [int]$Port = 8443,
    [string]$LabId = "lab-1",
    [string]$AccessKey = "BouncingBall.fmu",
    [int]$ExpiresInSeconds = 5,
    [int]$TimeoutSeconds = 40,
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$TokenHelper = Join-Path $ScriptDir "new-fmu-dev-booking-token.py"
if (-not (Test-Path $TokenHelper)) {
    throw "Token helper not found: $TokenHelper"
}

Add-Type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public sealed class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint srvPoint, X509Certificate certificate, WebRequest request, int certificateProblem) {
        return true;
    }
}
"@
[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

$token = & $PythonExe $TokenHelper `
    --lab-id $LabId `
    --access-key $AccessKey `
    --expires-in-seconds $ExpiresInSeconds `
    --nbf-skew-seconds 0

if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($token)) {
    throw "Could not generate a short-lived FMU booking JWT for expiry verification."
}
$token = $token.Trim()

$ws = [System.Net.WebSockets.ClientWebSocket]::new()

$uri = [Uri]("wss://127.0.0.1:$Port/fmu/api/v1/fmu/sessions?token=$([Uri]::EscapeDataString($token))")
$cts = [System.Threading.CancellationTokenSource]::new([TimeSpan]::FromSeconds($TimeoutSeconds))

function Send-Json([System.Net.WebSockets.ClientWebSocket]$Socket, [hashtable]$Payload, [System.Threading.CancellationToken]$CancellationToken) {
    $json = $Payload | ConvertTo-Json -Compress -Depth 8
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $segment = [System.ArraySegment[byte]]::new($bytes)
    $null = $Socket.SendAsync($segment, [System.Net.WebSockets.WebSocketMessageType]::Text, $true, $CancellationToken).GetAwaiter().GetResult()
}

function Receive-Json([System.Net.WebSockets.ClientWebSocket]$Socket, [System.Threading.CancellationToken]$CancellationToken) {
    $buffer = New-Object byte[] 4096
    $builder = [System.Text.StringBuilder]::new()
    do {
        $segment = [System.ArraySegment[byte]]::new($buffer)
        $result = $Socket.ReceiveAsync($segment, $CancellationToken).GetAwaiter().GetResult()
        if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
            return [pscustomobject]@{
                type = "socket.closed"
                closeStatus = [int]$result.CloseStatus
                closeStatusDescription = $result.CloseStatusDescription
            }
        }
        [void]$builder.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
    } while (-not $result.EndOfMessage)

    $payload = $builder.ToString()
    return $payload | ConvertFrom-Json
}

try {
    $null = $ws.ConnectAsync($uri, $cts.Token).GetAwaiter().GetResult()
    Send-Json $ws @{
        type = "session.create"
        requestId = "req-expiry"
        labId = $LabId
    } $cts.Token

    $created = Receive-Json $ws $cts.Token
    if ($created.type -ne "session.created") {
        throw "Expected session.created, received: $($created | ConvertTo-Json -Compress -Depth 8)"
    }

    while ($true) {
        $payload = Receive-Json $ws $cts.Token
        if ($payload.type -eq "session.closed" -and $payload.reason -eq "expired") {
            Write-Host "session.closed received with reason=expired" -ForegroundColor Green
            exit 0
        }
        if ($payload.type -eq "error") {
            throw "Unexpected error payload: $($payload | ConvertTo-Json -Compress -Depth 8)"
        }
        if ($payload.type -eq "socket.closed") {
            throw "WebSocket closed before receiving session.closed reason=expired"
        }
    }
} finally {
    if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open -or
        $ws.State -eq [System.Net.WebSockets.WebSocketState]::CloseReceived) {
        $closeToken = [System.Threading.CancellationToken]::None
        $null = $ws.CloseAsync([System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure, "done", $closeToken).GetAwaiter().GetResult()
    }
    $ws.Dispose()
    $cts.Dispose()
}
