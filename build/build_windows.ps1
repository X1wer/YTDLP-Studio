# YTDLP Studio – Windows 11 x64 portable build
#
# Használat (PowerShell, a projekt gyökeréből vagy bárhonnan):
#   powershell -ExecutionPolicy Bypass -File build\build_windows.ps1
# Kapcsolók:
#   -SkipTests      az automatikus tesztek kihagyása
#   -OfflineTools   a bin\ mappában lévő eszközök használata letöltés nélkül
#
# Eredmény: dist\YTDLPStudio\ (portable mappa) és dist\YTDLPStudio-<verzió>-Windows-x64-portable.zip
param([switch]$SkipTests, [switch]$OfflineTools)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$ProgressPreference = 'SilentlyContinue'   # az Invoke-WebRequest így sokkal gyorsabb

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Bin = Join-Path $Root 'bin'
$Cache = Join-Path $Root '.build-cache'
$Downloads = Join-Path $Cache 'downloads'
$Dist = Join-Path $Root 'dist'
$AppDir = Join-Path $Dist 'YTDLPStudio'
New-Item -ItemType Directory -Force $Bin, $Downloads, $Dist | Out-Null

$Version = (Select-String -Path 'src\ytstudio\__init__.py' -Pattern '__version__ = "([0-9.]+)"').Matches[0].Groups[1].Value
Write-Host "YTDLP Studio $Version - portable build" -ForegroundColor Cyan

# --------------------------------------------------------------------------
# Python 3.11–3.13 x64 keresése ('py' launcher vagy 'python')
# --------------------------------------------------------------------------
function Find-BuildPython {
  $candidates = @(
    @{ Command = 'py'; Prefix = @('-3.12') }, @{ Command = 'py'; Prefix = @('-3.13') },
    @{ Command = 'py'; Prefix = @('-3.11') }, @{ Command = 'python'; Prefix = @() },
    @{ Command = 'python3'; Prefix = @() }, @{ Command = 'py'; Prefix = @() })
  $check = "import sys, struct; v=sys.version_info; ok=(3,11)<=v[:2]<=(3,13) and struct.calcsize('P')==8; print('PYTHON_OK:'+sys.version.split()[0]) if ok else sys.exit(2)"
  foreach ($c in $candidates) {
    if (-not (Get-Command $c.Command -ErrorAction SilentlyContinue)) { continue }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
      $out = & $c.Command @($c.Prefix + @('-c', $check)) 2>$null
      if ($LASTEXITCODE -eq 0 -and "$out" -match 'PYTHON_OK:([0-9.]+)') {
        return @{ Command = $c.Command; Prefix = @($c.Prefix); Version = $Matches[1] }
      }
    } catch { } finally { $ErrorActionPreference = $previous }
  }
  throw 'Nem talalhato 64 bites Python 3.11-3.13. Telepitsd: https://www.python.org/downloads/windows/'
}

# --------------------------------------------------------------------------
# Hivatalos GitHub-kiadások letöltése SHA-256 ellenőrzéssel, gyorsítótárral
# --------------------------------------------------------------------------
function Get-Release([string]$Repo, [string]$Tag = 'latest') {
  $url = if ($Tag -eq 'latest') { "https://api.github.com/repos/$Repo/releases/latest" } else { "https://api.github.com/repos/$Repo/releases/tags/$Tag" }
  return Invoke-RestMethod -Uri $url -Headers @{ 'User-Agent' = "YTDLPStudio-Build/$Version"; 'Accept' = 'application/vnd.github+json' }
}

function Get-VerifiedAsset([object]$Release, [string]$Name, [string]$Target, [switch]$RequireSha) {
  $asset = @($Release.assets | Where-Object { $_.name -eq $Name }) | Select-Object -First 1
  if ($null -eq $asset) { throw "A kiadasbol hianyzik: $Name" }
  $expected = $null
  if ($asset.PSObject.Properties['digest'] -and "$($asset.digest)" -match '^sha256:([a-fA-F0-9]{64})$') { $expected = $Matches[1].ToUpper() }
  $sums = @($Release.assets | Where-Object { $_.name -eq 'SHA2-256SUMS' }) | Select-Object -First 1
  if ($null -ne $sums) {
    $sumFile = Join-Path $Downloads "$($Release.tag_name)-SHA2-256SUMS"
    Invoke-WebRequest -UseBasicParsing -Uri $sums.browser_download_url -OutFile $sumFile
    foreach ($line in Get-Content $sumFile) {
      if ($line -match '^([A-Fa-f0-9]{64})\s+\*?(.+)$' -and $Matches[2].Trim() -eq $Name) {
        $listed = $Matches[1].ToUpper()
        if ($expected -and $expected -ne $listed) { throw "Eltero hivatalos SHA-256 ertekek: $Name" }
        $expected = $listed
      }
    }
  }
  if ($RequireSha -and -not $expected) { throw "Nincs hivatalos SHA-256 ehhez: $Name" }
  if ($expected -and (Test-Path -LiteralPath $Target -PathType Leaf)) {
    if ((Get-FileHash -LiteralPath $Target -Algorithm SHA256).Hash -eq $expected) {
      Write-Host "  gyorsitotarbol (SHA-256 OK): $Name" -ForegroundColor Green
      return
    }
  }
  Write-Host "  letoltes: $Name" -ForegroundColor Cyan
  $temp = "$Target.download"
  if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $asset.browser_download_url -OutFile $temp
    if ($expected) {
      if ((Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -ne $expected) { throw "SHA-256 elteres: $Name" }
      Write-Host "  SHA-256 OK: $Name" -ForegroundColor Green
    } else {
      Write-Warning "${Name}: a kiadas nem ad SHA-256 erteket; HTTPS-en letoltve."
    }
    Move-Item -LiteralPath $temp -Destination $Target -Force
  } finally {
    if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
  }
}

$versions = [ordered]@{ 'YTDLP Studio' = $Version }
if ($OfflineTools) {
  foreach ($tool in 'yt-dlp', 'ffmpeg', 'ffprobe', 'deno') {
    if (-not (Test-Path (Join-Path $Bin "$tool.exe"))) { throw "Hianyzik: bin\$tool.exe (futtasd -OfflineTools nelkul)" }
  }
  $versions['Eszkozok'] = 'a meglevo bin\ mappabol (offline build)'
} else {
  Write-Host 'Fuggosegek a hivatalos kiadasokbol:' -ForegroundColor Cyan
  $ytdlp = Get-Release 'yt-dlp/yt-dlp'
  Get-VerifiedAsset $ytdlp 'yt-dlp.exe' (Join-Path $Bin 'yt-dlp.exe') -RequireSha
  $versions['yt-dlp'] = "$($ytdlp.tag_name) (github.com/yt-dlp/yt-dlp)"

  $deno = Get-Release 'denoland/deno'
  $denoZip = Join-Path $Downloads 'deno-x86_64-pc-windows-msvc.zip'
  Get-VerifiedAsset $deno 'deno-x86_64-pc-windows-msvc.zip' $denoZip -RequireSha
  $denoOut = Join-Path $Cache 'deno-extract'
  if (Test-Path $denoOut) { Remove-Item $denoOut -Recurse -Force }
  Expand-Archive -LiteralPath $denoZip -DestinationPath $denoOut -Force
  Copy-Item (Join-Path $denoOut 'deno.exe') (Join-Path $Bin 'deno.exe') -Force
  $versions['Deno'] = "$($deno.tag_name) (github.com/denoland/deno)"

  $ff = Get-Release 'BtbN/FFmpeg-Builds' 'latest'
  $ffName = 'ffmpeg-master-latest-win64-gpl.zip'
  $ffZip = Join-Path $Downloads $ffName
  Get-VerifiedAsset $ff $ffName $ffZip -RequireSha
  $ffOut = Join-Path $Cache 'ffmpeg-extract'
  if (Test-Path $ffOut) { Remove-Item $ffOut -Recurse -Force }
  Expand-Archive -LiteralPath $ffZip -DestinationPath $ffOut -Force
  foreach ($tool in 'ffmpeg.exe', 'ffprobe.exe') {
    $found = Get-ChildItem $ffOut -Recurse -Filter $tool -File | Select-Object -First 1
    if (-not $found) { throw "Az FFmpeg ZIP-bol hianyzik: $tool" }
    Copy-Item $found.FullName (Join-Path $Bin $tool) -Force
  }
  $ffLicense = Get-ChildItem $ffOut -Recurse -File -Filter 'LICENSE*' | Select-Object -First 1
  if ($ffLicense) { Copy-Item $ffLicense.FullName (Join-Path $Cache 'ffmpeg-distribution-LICENSE.txt') -Force }
  $ffAsset = @($ff.assets | Where-Object { $_.name -eq $ffName })[0]
  $versions['FFmpeg'] = "BtbN/FFmpeg-Builds $($ff.tag_name), feltoltve $($ffAsset.updated_at) (win64-gpl)"
}

# --------------------------------------------------------------------------
# Python-környezet, tesztek, PyInstaller
# --------------------------------------------------------------------------
$py = Find-BuildPython
Write-Host "Python $($py.Version) ($($py.Command) $($py.Prefix -join ' '))" -ForegroundColor Green
$venv = Join-Path $Root '.build-venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
  & $py.Command @($py.Prefix + @('-m', 'venv', $venv))
  if ($LASTEXITCODE -ne 0) { throw 'A virtualis kornyezet letrehozasa nem sikerult.' }
}
& $venvPython -m pip install --disable-pip-version-check -q -r 'build\requirements-build.txt'
if ($LASTEXITCODE -ne 0) { throw 'A Python-csomagok telepitese nem sikerult.' }
if (-not (Test-Path 'assets\icon.ico')) { & $venvPython 'build\make_icon.py' }

if (-not $SkipTests) {
  Write-Host 'Automatikus tesztek...' -ForegroundColor Cyan
  Push-Location 'tests'
  try {
    & $venvPython -m unittest discover -s .
    if ($LASTEXITCODE -ne 0) { throw 'A tesztek hibat jeleztek; a build leallt.' }
  } finally { Pop-Location }
}

$parts = ($Version.Split('.') + @('0', '0', '0', '0'))[0..3] -join ', '
$dotted = ($Version.Split('.') + @('0', '0', '0', '0'))[0..3] -join '.'
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($parts), prodvers=($parts), mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040E04B0', [
      StringStruct('CompanyName', 'YTDLP Studio contributors'),
      StringStruct('FileDescription', 'YTDLP Studio - video- es hangletolto'),
      StringStruct('FileVersion', '$dotted'),
      StringStruct('InternalName', 'YTDLPStudio'),
      StringStruct('LegalCopyright', 'MIT License'),
      StringStruct('OriginalFilename', 'YTDLPStudio.exe'),
      StringStruct('ProductName', 'YTDLP Studio'),
      StringStruct('ProductVersion', '$Version')])]),
    VarFileInfo([VarStruct('Translation', [0x040E, 1200])])
  ]
)
"@ | Set-Content -Path (Join-Path $Cache 'version_info.txt') -Encoding UTF8

Write-Host 'PyInstaller (onedir)...' -ForegroundColor Cyan
if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
& $venvPython -m PyInstaller --noconfirm --clean --log-level WARN --distpath $Dist --workpath (Join-Path $Cache 'pyinstaller') 'build\YTDLPStudio.spec'
if ($LASTEXITCODE -ne 0) { throw 'A PyInstaller-forditas nem sikerult.' }
if (-not (Test-Path (Join-Path $AppDir 'YTDLPStudio.exe'))) { throw 'Nem keszult el a YTDLPStudio.exe' }

# --------------------------------------------------------------------------
# Portable mappa összeállítása
# --------------------------------------------------------------------------
New-Item -ItemType Directory -Force (Join-Path $AppDir 'bin'), (Join-Path $AppDir 'licenses') | Out-Null
foreach ($tool in 'yt-dlp', 'ffmpeg', 'ffprobe', 'deno') { Copy-Item (Join-Path $Bin "$tool.exe") (Join-Path $AppDir 'bin') -Force }
Get-ChildItem 'docs\licenses' -File | Where-Object { $_.Name -ne 'pillow-MIT-CMU.txt' } | Copy-Item -Destination (Join-Path $AppDir 'licenses') -Force
$ffLicenseCached = Join-Path $Cache 'ffmpeg-distribution-LICENSE.txt'
if (Test-Path $ffLicenseCached) { Copy-Item $ffLicenseCached (Join-Path $AppDir 'licenses') -Force }
Copy-Item 'README.md', 'CHANGELOG.md' $AppDir -Force
foreach ($tool in 'yt-dlp', 'ffmpeg', 'deno') {
  $exe = Join-Path $Bin "$tool.exe"
  $flag = if ($tool -eq 'ffmpeg') { '-version' } else { '--version' }
  $line = (& $exe $flag 2>$null | Select-Object -First 1)
  $versions["$tool (futtatva)"] = "$line"
}
$versions['Build ideje'] = (Get-Date -Format 'yyyy-MM-dd HH:mm')
($versions.GetEnumerator() | ForEach-Object { "$($_.Key): $($_.Value)" }) | Set-Content (Join-Path $AppDir 'VERSIONS.txt') -Encoding UTF8

$zip = Join-Path $Dist "YTDLPStudio-$Version-Windows-x64-portable.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host 'ZIP keszitese...' -ForegroundColor Cyan
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($AppDir, $zip, [System.IO.Compression.CompressionLevel]::Optimal, $true)
$hash = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $zip -Leaf)" | Set-Content "$zip.sha256" -Encoding ASCII

$size = '{0:N0} MB' -f ((Get-Item $zip).Length / 1MB)
Write-Host ''
Write-Host "KESZ: $AppDir" -ForegroundColor Green
Write-Host "ZIP:  $zip ($size)" -ForegroundColor Green
Write-Host "SHA-256: $hash"
