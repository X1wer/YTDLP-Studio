# Build a real, self-contained Windows 11 x64 portable distribution.
# Run in PowerShell on Windows 11 with a supported 64-bit Python 3.11-3.13 installed:
#   powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Set-Location $PSScriptRoot
$bin = Join-Path $PSScriptRoot 'bin'
$distDir = Join-Path $PSScriptRoot 'dist'
$stage = Join-Path $distDir 'YTDLPStudio-portable'
New-Item -ItemType Directory -Force $bin,$distDir | Out-Null

function Get-Release([string]$url) {
  return Invoke-RestMethod -Uri $url -Headers @{'User-Agent'='YTDLPStudio-Build/0.1'; 'Accept'='application/vnd.github+json'}
}
function Get-Asset([object]$release, [string]$name, [string]$target, [switch]$RequiredSha) {
  $asset = @($release.assets | Where-Object { $_.name -eq $name }) | Select-Object -First 1
  if ($null -eq $asset) { throw "Missing release file: $name" }
  $expected = $null
  if ($asset.PSObject.Properties['digest'] -and $asset.digest -match '^sha256:([a-f0-9]{64})$') { $expected = $Matches[1] }
  if (-not $expected -and $RequiredSha) {
    $sums = @($release.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }) | Select-Object -First 1
    if ($null -eq $sums) { throw "No official SHA-256 hash available: $name" }
    $sumPath = Join-Path $distDir 'SHA2-256SUMS.txt'
    Invoke-WebRequest -UseBasicParsing -Uri $sums.browser_download_url -OutFile $sumPath
    foreach ($line in (Get-Content $sumPath)) {
      if ($line -match '^([A-Fa-f0-9]{64})\s+\*?(.+)$' -and $Matches[2].Trim() -eq $name) {
        $expected = $Matches[1]; break
      }
    }
  }
  if ($RequiredSha -and -not $expected) { throw "Cannot verify SHA-256 for $name" }

  # Re-use the binary already downloaded on a previous run ONLY if its
  # checksum matches the current official GitHub release.
  $verified = $false
  if ($expected -and (Test-Path -LiteralPath $target -PathType Leaf)) {
    $actual = (Get-FileHash -Path $target -Algorithm SHA256).Hash
    $verified = ($actual -eq $expected)
    if ($verified) { Write-Host "Cached SHA-256 OK: $name" -ForegroundColor Green }
  }
  if (-not $verified) {
    Write-Host "Downloading: $name" -ForegroundColor Cyan
    $tempTarget = "$target.download"
    if (Test-Path $tempTarget) { Remove-Item $tempTarget -Force }
    try {
      Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $tempTarget
      if ($expected) {
        $actual = (Get-FileHash -Path $tempTarget -Algorithm SHA256).Hash
        if ($actual -ne $expected) { throw "SHA-256 mismatch: $name" }
        Write-Host "SHA-256 OK: $name" -ForegroundColor Green
      } else {
        Write-Warning "${name}: No official SHA-256 provided by the release; downloaded via HTTPS."
      }
      Move-Item -LiteralPath $tempTarget -Destination $target -Force
    } finally {
      if (Test-Path $tempTarget) { Remove-Item $tempTarget -Force }
    }
  }
}

# Accept an installed 64-bit Python 3.11-3.13, whether it is launched by
# 'python' or through the Windows 'py' launcher. Prefer Python 3.12.
function Find-BuildPython {
  $candidates = @(
    @{ Command = 'py'; Prefix = @('-3.12') },
    @{ Command = 'py'; Prefix = @('-3.13') },
    @{ Command = 'py'; Prefix = @('-3.11') },
    @{ Command = 'python'; Prefix = @() },
    @{ Command = 'python3'; Prefix = @() },
    @{ Command = 'py'; Prefix = @() }
  )
  $checkCode = "import sys, struct; v=sys.version_info; ok=(3,11)<=v[:2]<=(3,13) and struct.calcsize('P')==8; print('PYTHON_OK:'+sys.version.split()[0]) if ok else sys.exit(2)"
  foreach ($candidate in $candidates) {
    $cmd = $candidate.Command
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
    $argsToCheck = @($candidate.Prefix) + @('-c', $checkCode)
    # Some 'py -3.12' calls may fail if that specific version is unavailable.
    # Ignore these probing failures and try the next candidate.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $result = & $cmd @argsToCheck 2>$null
      $exitCode = $LASTEXITCODE
      if ($exitCode -eq 0 -and "$result" -match 'PYTHON_OK:([0-9]+\.[0-9]+\.[0-9]+)') {
        return @{ Command = $cmd; Prefix = @($candidate.Prefix); Version = $Matches[1] }
      }
    } catch {
      # Try other Python commands rather than aborting the entire build.
    } finally {
      $ErrorActionPreference = $previous
    }
  }
  throw "No compatible 64-bit Python found. Install Python 3.12 x64 from https://www.python.org/downloads/windows/ (or check: py -0p and python --version)."
}

$buildPython = Find-BuildPython
Write-Host "Using Python $($buildPython.Version) x64 via $($buildPython.Command) $($buildPython.Prefix -join ' ')" -ForegroundColor Green
function Invoke-BuildPython([string[]]$PythonArgs) {
  $fullArgs = @($buildPython.Prefix) + $PythonArgs
  & $buildPython.Command @fullArgs
  if ($LASTEXITCODE -ne 0) { throw "Python process failed (exit code $LASTEXITCODE): $($PythonArgs -join ' ')" }
}

# yt-dlp standalone includes yt-dlp-ejs. Deno is bundled separately.
$ydlp = Get-Release 'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest'
Get-Asset $ydlp 'yt-dlp.exe' (Join-Path $bin 'yt-dlp.exe') -RequiredSha

$deno = Get-Release 'https://api.github.com/repos/denoland/deno/releases/latest'
$denoZip = Join-Path $distDir 'deno.zip'
Get-Asset $deno 'deno-x86_64-pc-windows-msvc.zip' $denoZip
$denoExtract = Join-Path $distDir 'deno-extract'
New-Item -ItemType Directory -Force $denoExtract | Out-Null
Expand-Archive -Path $denoZip -DestinationPath $denoExtract -Force
Copy-Item (Join-Path $denoExtract 'deno.exe') (Join-Path $bin 'deno.exe') -Force

# Gyan / BtbN are community FFmpeg binary distributors; no official Windows
# executables are published by the FFmpeg upstream. Use GPL-licensed binaries.
$ffRelease = Get-Release 'https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest'
$ffZip = Join-Path $distDir 'ffmpeg.zip'
Get-Asset $ffRelease 'ffmpeg-master-latest-win64-gpl.zip' $ffZip
$ffExtract = Join-Path $distDir 'ffmpeg-extract'
New-Item -ItemType Directory -Force $ffExtract | Out-Null
Expand-Archive -Path $ffZip -DestinationPath $ffExtract -Force
$ffFound = Get-ChildItem $ffExtract -Recurse -Filter 'ffmpeg.exe' -File | Select-Object -First 1
$probeFound = Get-ChildItem $ffExtract -Recurse -Filter 'ffprobe.exe' -File | Select-Object -First 1
if (-not $ffFound -or -not $probeFound) { throw 'Az FFmpeg ZIP nem tartalmazza a szükséges EXE fájlokat' }
Copy-Item $ffFound.FullName (Join-Path $bin 'ffmpeg.exe') -Force
Copy-Item $probeFound.FullName (Join-Path $bin 'ffprobe.exe') -Force

# Build in a project-local virtual environment (no admin rights or global
# Python package modifications). The finished EXE does not require Python.
$venvDir = Join-Path $PSScriptRoot '.build-venv'
$venvPython = Join-Path $venvDir 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
  Write-Host 'Creating isolated build environment...'
  Invoke-BuildPython @('-m', 'venv', $venvDir)
}
& $venvPython -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32 else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Existing .build-venv is incompatible. Delete that directory and retry.' }
Write-Host 'Installing PyInstaller and Pillow into the local build environment...'
& $venvPython -m pip install --disable-pip-version-check -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Failed to install Python build dependencies.' }
& $venvPython -m PyInstaller --noconfirm --clean --onefile --windowed --name YTDLPStudio --icon assets\icon.ico start.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller compilation failed.' }
if (!(Test-Path (Join-Path $distDir 'YTDLPStudio.exe'))) { throw 'A Windows EXE nem készült el' }
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $stage 'bin'), (Join-Path $stage 'licenses') | Out-Null
Copy-Item (Join-Path $distDir 'YTDLPStudio.exe') (Join-Path $stage 'YTDLPStudio.exe') -Force
Copy-Item (Join-Path $bin '*.exe') (Join-Path $stage 'bin') -Force
Copy-Item (Join-Path $PSScriptRoot 'licenses\*') (Join-Path $stage 'licenses') -Recurse -Force
Copy-Item (Join-Path $PSScriptRoot 'README.md') (Join-Path $stage 'README.md') -Force
@("YTDLPStudio 0.1.3", "yt-dlp: $($ydlp.tag_name)", "Deno: $($deno.tag_name)",
  "FFmpeg BtbN: $($ffRelease.tag_name)", "Binaries from official GitHub release pages") |
  Set-Content (Join-Path $stage 'VERSIONS.txt') -Encoding utf8
# Preserve bundled FFmpeg license and documentation if shipped by distributor.
$ffLicenseFiles = @(Get-ChildItem $ffExtract -Recurse -File | Where-Object { $_.Name -match '^(LICENSE|COPYING)(\..*)?$' })
foreach ($file in $ffLicenseFiles) {
  Copy-Item $file.FullName (Join-Path $stage ('licenses\ffmpeg-distribution-' + $file.Name)) -Force
}
$archive = Join-Path $distDir 'YTDLPStudio-Windows-x64-portable.zip'
if (Test-Path $archive) { Remove-Item $archive -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $archive -CompressionLevel Optimal
Write-Host "KÉSZ: $archive" -ForegroundColor Green
Write-Host 'Indítsd el a portable YTDLPStudio.exe-t a kicsomagolt mappából.'
