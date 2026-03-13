param(
    [string]$OpenModelicaBin = "C:\Program Files\OpenModelica1.26.3-64bit\bin",
    [string]$BaseUrl = "https://localhost:8443",
    [string]$LabId = "lab-1",
    [string]$AccessKey = "Feedthrough.fmu",
    [string]$Workspace = ""
)

$ErrorActionPreference = "Stop"

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw $Message
    }
}

function New-ReservationKey {
    param([string]$Prefix)
    return "{0}-{1}" -f $Prefix, (Get-Random -Minimum 1000 -Maximum 9999)
}

function New-BookingToken {
    param(
        [string]$AccessKey,
        [string]$LabId,
        [string]$ReservationKey,
        [string]$RepoRoot
    )

    $scriptPath = Join-Path $RepoRoot "tests\integration\new-fmu-dev-booking-token.py"
    $token = python $scriptPath --access-key $AccessKey --lab-id $LabId --reservation-key $ReservationKey
    if ($LASTEXITCODE -ne 0) {
        throw "Could not generate a booking JWT for reservationKey=$ReservationKey."
    }

    return ($token | Select-Object -Last 1).Trim()
}

function Download-ProxyFmu {
    param(
        [string]$BaseUrl,
        [string]$LabId,
        [string]$ReservationKey,
        [string]$Token,
        [string]$Destination
    )

    $url = "${BaseUrl}/fmu/api/v1/fmu/proxy/${LabId}?reservationKey=${ReservationKey}"
    & curl.exe -sk -H "Authorization: Bearer $Token" $url -o $Destination
    if ($LASTEXITCODE -ne 0) {
        throw "Could not download proxy.fmu from $url."
    }

    Assert-PathExists -Path $Destination -Message "Expected downloaded proxy.fmu at $Destination."
    if ((Get-Item -LiteralPath $Destination).Length -lt 1024) {
        $body = Get-Content -LiteralPath $Destination -Raw
        throw "Downloaded proxy.fmu from $url is too small and likely an error payload: $body"
    }
}

function Invoke-OMSimulatorLua {
    param(
        [string]$OMSimulatorExe,
        [string]$WorkingDir,
        [string]$LuaPath
    )

    $luaFileName = Split-Path -Leaf $LuaPath
    Push-Location $WorkingDir
    try {
        $output = & $OMSimulatorExe $luaFileName 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    return [pscustomobject]@{
        Output = ($output -join "`n")
        ExitCode = $exitCode
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$testsDir = $scriptDir
$gatewayRoot = Split-Path -Parent (Split-Path -Parent $testsDir)

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Join-Path $testsDir "artifacts\openmodelica-omsimulator"
}

$omSimulatorExe = Join-Path $OpenModelicaBin "OMSimulator.exe"
$localFmuPath = Join-Path $gatewayRoot ("fmu-data\" + $AccessKey)

Assert-PathExists -Path $omSimulatorExe -Message "OMSimulator.exe not found at $omSimulatorExe."
Assert-PathExists -Path $localFmuPath -Message "Local FMU not found at $localFmuPath."

New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
$workspace = (Resolve-Path $Workspace).Path
$workspaceUnix = $workspace -replace "\\", "/"

$compositeReservationKey = New-ReservationKey -Prefix "om-composite"
$stepReservationKey = New-ReservationKey -Prefix "om-step"

$compositeProxyPath = Join-Path $workspace "proxy-feedthrough-composite.fmu"
$stepProxyPath = Join-Path $workspace "proxy-feedthrough-step.fmu"
$compositeLuaPath = Join-Path $workspace "run-composite.lua"
$stepLuaPath = Join-Path $workspace "run-step.lua"
$compositeResultPath = Join-Path $workspace "proxy-composite_res.mat"
$compositeSspPath = Join-Path $workspace "proxy-composite.ssp"
$stepResultPath = Join-Path $workspace "proxyStep_res.mat"
$localCopyPath = Join-Path $workspace $AccessKey

Copy-Item $localFmuPath $localCopyPath -Force

$compositeToken = New-BookingToken -AccessKey $AccessKey -LabId $LabId -ReservationKey $compositeReservationKey -RepoRoot $gatewayRoot
$stepToken = New-BookingToken -AccessKey $AccessKey -LabId $LabId -ReservationKey $stepReservationKey -RepoRoot $gatewayRoot

Download-ProxyFmu -BaseUrl $BaseUrl -LabId $LabId -ReservationKey $compositeReservationKey -Token $compositeToken -Destination $compositeProxyPath
Download-ProxyFmu -BaseUrl $BaseUrl -LabId $LabId -ReservationKey $stepReservationKey -Token $stepToken -Destination $stepProxyPath

$compositeLua = @"
oms_setTempDirectory("./temp/")
oms_newModel("proxyComposite")
oms_addSystem("proxyComposite.root", oms_system_wc)
oms_addSubModel("proxyComposite.root.localFeedthrough", "$AccessKey")
oms_addSubModel("proxyComposite.root.remoteProxy", "proxy-feedthrough-composite.fmu")
oms_addConnection("proxyComposite.root.localFeedthrough.Float64_continuous_output", "proxyComposite.root.remoteProxy.Float64_continuous_input")
oms_setResultFile("proxyComposite", "proxy-composite_res.mat", 1)
oms_setStopTime("proxyComposite", 0.1)
oms_setFixedStepSize("proxyComposite.root", 0.01)
oms_instantiate("proxyComposite")
oms_setReal("proxyComposite.root.localFeedthrough.Float64_continuous_input", 2.5)
oms_initialize("proxyComposite")
local_out, status1 = oms_getReal("proxyComposite.root.localFeedthrough.Float64_continuous_output")
remote_out, status2 = oms_getReal("proxyComposite.root.remoteProxy.Float64_continuous_output")
print("before_sim local=" .. tostring(local_out) .. " remote=" .. tostring(remote_out) .. " status1=" .. tostring(status1) .. " status2=" .. tostring(status2))
oms_simulate("proxyComposite")
local_out2, status3 = oms_getReal("proxyComposite.root.localFeedthrough.Float64_continuous_output")
remote_out2, status4 = oms_getReal("proxyComposite.root.remoteProxy.Float64_continuous_output")
print("after_sim local=" .. tostring(local_out2) .. " remote=" .. tostring(remote_out2) .. " status3=" .. tostring(status3) .. " status4=" .. tostring(status4))
oms_export("proxyComposite", "proxy-composite.ssp")
oms_terminate("proxyComposite")
oms_delete("proxyComposite")
"@

$stepLua = @"
oms_setTempDirectory("./temp-step/")
oms_newModel("proxyStep")
oms_addSystem("proxyStep.root", oms_system_wc)
oms_addSubModel("proxyStep.root.remoteProxy", "proxy-feedthrough-step.fmu")
oms_setStopTime("proxyStep", 0.2)
oms_setFixedStepSize("proxyStep.root", 0.01)
oms_instantiate("proxyStep")
oms_setReal("proxyStep.root.remoteProxy.Float64_continuous_input", 1.25)
oms_initialize("proxyStep")
out1, st1 = oms_getReal("proxyStep.root.remoteProxy.Float64_continuous_output")
print("init output=" .. tostring(out1) .. " status=" .. tostring(st1))
oms_stepUntil("proxyStep", 0.1)
out2, st2 = oms_getReal("proxyStep.root.remoteProxy.Float64_continuous_output")
print("after step 0.1 output=" .. tostring(out2) .. " status=" .. tostring(st2))
oms_setReal("proxyStep.root.remoteProxy.Float64_continuous_input", 4.75)
oms_stepUntil("proxyStep", 0.2)
out3, st3 = oms_getReal("proxyStep.root.remoteProxy.Float64_continuous_output")
print("after step 0.2 output=" .. tostring(out3) .. " status=" .. tostring(st3))
oms_terminate("proxyStep")
oms_delete("proxyStep")
"@

Set-Content -LiteralPath $compositeLuaPath -Value $compositeLua -NoNewline
Set-Content -LiteralPath $stepLuaPath -Value $stepLua -NoNewline

$compositeRun = Invoke-OMSimulatorLua -OMSimulatorExe $omSimulatorExe -WorkingDir $workspace -LuaPath $compositeLuaPath
if ($compositeRun.ExitCode -ne 0) {
    throw "Composite OMSimulator run failed.`n$($compositeRun.Output)"
}

Assert-PathExists -Path $compositeResultPath -Message "Composite OMSimulator run did not produce $compositeResultPath."
Assert-PathExists -Path $compositeSspPath -Message "Composite OMSimulator run did not export $compositeSspPath."

if ($compositeRun.Output -notmatch "before_sim local=2.5 remote=2.5") {
    throw "Composite OMSimulator run did not confirm the local->remote connection before simulate.`n$($compositeRun.Output)"
}

if ($compositeRun.Output -notmatch "after_sim local=2.5 remote=2.5") {
    throw "Composite OMSimulator run did not preserve the connected values after simulate.`n$($compositeRun.Output)"
}

$stepRun = Invoke-OMSimulatorLua -OMSimulatorExe $omSimulatorExe -WorkingDir $workspace -LuaPath $stepLuaPath
if ($stepRun.ExitCode -ne 0) {
    throw "Stepwise OMSimulator run failed.`n$($stepRun.Output)"
}

Assert-PathExists -Path $stepResultPath -Message "Stepwise OMSimulator run did not produce $stepResultPath."

if ($stepRun.Output -notmatch "after step 0.1 output=1.25") {
    throw "Stepwise OMSimulator run did not expose the first stepped output.`n$($stepRun.Output)"
}

if ($stepRun.Output -notmatch "after step 0.2 output=4.75") {
    throw "Stepwise OMSimulator run did not reflect the updated input after stepping.`n$($stepRun.Output)"
}

Write-Host "PASS openmodelica composite simulation"
Write-Host "  workspace: $workspace"
Write-Host "  ssp:       $compositeSspPath"
Write-Host "  result:    $compositeResultPath"
Write-Host "PASS openmodelica stepwise control"
Write-Host "  result:    $stepResultPath"
