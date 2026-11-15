# Build WinUI shell + GoldTicker.Core.exe into dist/windows-winui/
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Out = Join-Path $Root "dist\windows-winui"
$Stage = Join-Path $Out "GoldTicker"
Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $Stage | Out-Null

Write-Host "==> Build GoldTicker.Core.exe (IPC worker)"
New-Item -ItemType Directory -Force -Path (Join-Path $Root "build") | Out-Null
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
python -m pip install --disable-pip-version-check -q -r requirements.txt "pyinstaller>=6.11,<7"
python -c "from PIL import Image; Image.open('docs/icon-1024.png').convert('RGBA').save('build/GoldTicker.ico')"
python -m PyInstaller --noconfirm --clean --distpath dist/windows-core --workpath build/pyinstaller-core GoldTicker.Core.spec
if (-not (Test-Path "dist\windows-core\GoldTicker.Core.exe")) { throw "GoldTicker.Core.exe missing" }
Copy-Item "dist\windows-core\GoldTicker.Core.exe" (Join-Path $Stage "GoldTicker.Core.exe")

Write-Host "==> Publish WinUI (self-contained win-x64)"
$Proj = Join-Path $Root "winui\GoldTicker.WinUI\GoldTicker.WinUI.csproj"
$Publish = Join-Path $Root "dist\winui-publish"
Remove-Item -Recurse -Force $Publish -ErrorAction SilentlyContinue
# Do not pass Platform=x64 together with -r win-x64 (RID publish conflict on CI).
dotnet restore $Proj
dotnet publish $Proj -c Release -r win-x64 --self-contained true -o $Publish `
  -p:WindowsPackageType=None `
  -p:WindowsAppSDKSelfContained=true `
  -p:PublishSingleFile=false `
  -p:IncludeNativeLibrariesForSelfExtract=true
if (-not (Test-Path (Join-Path $Publish "GoldTicker.WinUI.exe"))) {
  Get-ChildItem $Publish -ErrorAction SilentlyContinue | Format-Table Name, Length
  throw "GoldTicker.WinUI.exe missing after publish"
}

Copy-Item -Recurse -Force (Join-Path $Publish "*") $Stage
# Prefer a clear entry name for users
$winuiExe = Join-Path $Stage "GoldTicker.WinUI.exe"
$entry = Join-Path $Stage "GoldTicker.exe"
if ((Test-Path $winuiExe) -and -not (Test-Path $entry)) {
  Rename-Item $winuiExe "GoldTicker.exe"
}

$Zip = Join-Path $Out "GoldTicker-WinUI-Windows-x64.zip"
if (Test-Path $Zip) { Remove-Item $Zip }
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $Zip -Force
Get-FileHash $Zip -Algorithm SHA256 | ForEach-Object {
  "$($_.Hash.ToLower())  GoldTicker-WinUI-Windows-x64.zip" | Set-Content ($Zip + ".sha256") -Encoding ascii
}

Write-Host "Built $Zip"
Get-ChildItem $Out | Format-Table Name, Length
