<#
.SYNOPSIS
  Builds BinaryClockTest.fmu (FMI 3.0 Co-Simulation with Binary + Clock).
.DESCRIPTION
  1. Compiles src/BinaryClockTest.c into a DLL via MSVC (x64).
  2. Packages modelDescription.xml + the DLL into BinaryClockTest.fmu (ZIP).
  3. Optionally copies the FMU to the fmu-data directory.
.NOTES
  Requires: Visual Studio 2019 Build Tools (or later).
  Run from the BinaryClockTest project directory.
#>

param(
    [switch]$NoCopy
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
$SrcFile    = Join-Path $ProjectDir 'src\BinaryClockTest.c'
$BuildDir   = Join-Path $ProjectDir 'build'
$FmuDataDir = Resolve-Path (Join-Path $ProjectDir '..\..')

# --- Locate MSVC -----------------------------------------------------------
$VcVars = $null
$VsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $VsWhere) {
    $VsPath = & $VsWhere -latest -property installationPath
    if ($VsPath) { $VcVars = Join-Path $VsPath 'VC\Auxiliary\Build\vcvars64.bat' }
}
# Fallback: known Build Tools 2019 path
if (-not $VcVars -or -not (Test-Path $VcVars)) {
    $VcVars = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\2019\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
}
if (-not (Test-Path $VcVars)) {
    throw "vcvars64.bat not found. Install Visual Studio Build Tools."
}

# --- Prepare build dir ------------------------------------------------------
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

$DllPath = Join-Path $BuildDir 'BinaryClockTest.dll'

# --- Compile ----------------------------------------------------------------
Write-Host ''
Write-Host '=== Compiling BinaryClockTest.c (x64 Release) ===' -ForegroundColor Cyan

$BatchFile = Join-Path $BuildDir '_compile.bat'
$BatchContent = "@echo off`r`ncall `"$VcVars`" >nul 2>&1`r`nif errorlevel 1 exit /b 1`r`ncl /LD /O2 /W4 /WX /nologo /DWIN32 `"$SrcFile`" /Fe:`"$DllPath`" /Fo:`"$BuildDir\BinaryClockTest.obj`""
[System.IO.File]::WriteAllText($BatchFile, $BatchContent, [System.Text.Encoding]::ASCII)

cmd /c $BatchFile
if ($LASTEXITCODE -ne 0) { throw 'Compilation failed.' }
if (-not (Test-Path $DllPath)) { throw "DLL not produced at $DllPath" }
Write-Host "   DLL: $DllPath" -ForegroundColor Green

# --- Package FMU ------------------------------------------------------------
Write-Host ''
Write-Host '=== Packaging BinaryClockTest.fmu ===' -ForegroundColor Cyan

$FmuPath = Join-Path $BuildDir 'BinaryClockTest.fmu'
$StagingDir = Join-Path $BuildDir '_staging'
if (Test-Path $StagingDir) { Remove-Item $StagingDir -Recurse -Force }

$BinDir = Join-Path $StagingDir 'binaries\x86_64-windows'
New-Item -ItemType Directory -Path $BinDir | Out-Null

Copy-Item $DllPath (Join-Path $BinDir 'BinaryClockTest.dll')
Copy-Item (Join-Path $ProjectDir 'modelDescription.xml') (Join-Path $StagingDir 'modelDescription.xml')

if (Test-Path $FmuPath) { Remove-Item $FmuPath -Force }
$ZipPath = $FmuPath -replace '\.fmu$', '.zip'
Compress-Archive -Path "$StagingDir\*" -DestinationPath $ZipPath -CompressionLevel Optimal
Move-Item $ZipPath $FmuPath -Force
Write-Host "   FMU: $FmuPath" -ForegroundColor Green

# --- Optionally copy to fmu-data -------------------------------------------
if (-not $NoCopy) {
    $DestFmu = Join-Path $FmuDataDir 'BinaryClockTest.fmu'
    Copy-Item $FmuPath $DestFmu -Force
    Write-Host "   Copied to: $DestFmu" -ForegroundColor Green
}

Write-Host ''
Write-Host '=== Done ===' -ForegroundColor Cyan
