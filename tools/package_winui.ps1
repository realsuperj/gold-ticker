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

Write-Host "==> Publish WinUI (self-contained win-x64 via VS MSBuild)"
$Proj = Join-Path $Root "winui\GoldTicker.WinUI\GoldTicker.WinUI.csproj"
$Publish = Join-Path $Root "dist\winui-publish"
Remove-Item -Recurse -Force $Publish -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Publish | Out-Null

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = if (Test-Path $vswhere) {
  & $vswhere -latest -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe" | Select-Object -First 1
} else { $null }

if ($msbuild) {
  Write-Host "Using MSBuild: $msbuild"
  & $msbuild $Proj /t:Restore /p:Configuration=Release /p:Platform=x64 /p:RuntimeIdentifier=win-x64
  if ($LASTEXITCODE -ne 0) { throw "MSBuild Restore failed ($LASTEXITCODE)" }
  & $msbuild $Proj /t:Publish `
    /p:Configuration=Release `
    /p:Platform=x64 `
    /p:RuntimeIdentifier=win-x64 `
    /p:SelfContained=true `
    /p:WindowsPackageType=None `
    /p:WindowsAppSDKSelfContained=true `
    /p:PublishSingleFile=false `
    /p:PublishDir="$Publish\"
  if ($LASTEXITCODE -ne 0) { throw "MSBuild Publish failed ($LASTEXITCODE)" }
} else {
  Push-Location (Split-Path $Proj)
  try {
    dotnet restore -r win-x64
    dotnet publish -c Release -r win-x64 --self-contained true -o $Publish `
      -p:Platform=x64 `
      -p:WindowsPackageType=None `
      -p:WindowsAppSDKSelfContained=true `
      -p:PublishSingleFile=false
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed ($LASTEXITCODE)" }
  } finally {
    Pop-Location
  }
}
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
