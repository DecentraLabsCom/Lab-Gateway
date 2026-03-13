param(
    [string]$ImageTag = "decentralabs/fmu-proxy-linux64-builder:local",
    [switch]$Promote
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..")
$Dockerfile = Join-Path $ScriptDir "docker/linux64-builder.Dockerfile"
$BuildDir = Join-Path $ScriptDir "build-linux64"
$RuntimeOutput = Join-Path $RepoRoot "fmu-proxy-runtime/binaries/linux64/decentralabs_proxy.so"

Write-Host "== Building Linux builder image ==" -ForegroundColor Cyan
docker build -f $Dockerfile -t $ImageTag $ScriptDir

Write-Host "== Building linux64 runtime inside Docker ==" -ForegroundColor Cyan
if (Test-Path $BuildDir) {
    Remove-Item -Recurse -Force $BuildDir
}
docker run --rm `
  -v "${ScriptDir}:/workspace" `
  $ImageTag `
  bash -lc "cmake -S /workspace -B /workspace/build-linux64 -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build /workspace/build-linux64 -j"

$BuiltLibrary = Join-Path $BuildDir "libdecentralabs_proxy.so"
if (-not (Test-Path $BuiltLibrary)) {
    throw "Expected library not found: $BuiltLibrary"
}

Get-Item $BuiltLibrary | Select-Object FullName,Length,LastWriteTime

if ($Promote) {
    New-Item -ItemType Directory -Force -Path (Split-Path $RuntimeOutput -Parent) | Out-Null
    Copy-Item -Force $BuiltLibrary $RuntimeOutput
    Write-Host "== Promoted linux64 runtime ==" -ForegroundColor Green
    Get-Item $RuntimeOutput | Select-Object FullName,Length,LastWriteTime
}
