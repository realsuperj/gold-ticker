# Build native standalone single-file GoldTicker.exe (.NET Framework 4.8 WPF — zero companion files)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force -Path (Join-Path $Root "build") | Out-Null
$Out = Join-Path $Root "dist\windows"
Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Out | Out-Null

Write-Host "==> Generate multi-size GoldTicker.ico"
python -c "from PIL import Image; im=Image.open('docs/icon-1024.png').convert('RGBA'); im.save('build/GoldTicker.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"

$Proj = Join-Path $Root "windows-wpf\GoldTicker.Wpf.csproj"
$BinDir = Join-Path $Root "build\wpf-out"
Remove-Item -Recurse -Force $BinDir -ErrorAction SilentlyContinue

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$msbuild = if (Test-Path $vswhere) {
  & $vswhere -latest -requires Microsoft.Component.MSBuild -find "MSBuild\**\Bin\MSBuild.exe" | Select-Object -First 1
} else { $null }

Write-Host "==> Compile standalone GoldTicker.exe (net48 WPF)"
if ($msbuild) {
  & $msbuild $Proj /restore /t:Rebuild /p:Configuration=Release /p:OutputPath="$BinDir\" /v:minimal
  if ($LASTEXITCODE -ne 0) { throw "MSBuild failed ($LASTEXITCODE)" }
} else {
  dotnet build $Proj -c Release -o $BinDir
  if ($LASTEXITCODE -ne 0) { throw "dotnet build failed ($LASTEXITCODE)" }
}

$BuiltExe = Join-Path $BinDir "GoldTicker.exe"
if (-not (Test-Path $BuiltExe)) { throw "GoldTicker.exe not produced in $BinDir" }

$TargetExe = Join-Path $Out "GoldTicker.exe"
Copy-Item -Force $BuiltExe $TargetExe

# Verify true single-file portability in a completely empty temp directory!
$IsoDir = Join-Path ([IO.Path]::GetTempPath()) ("goldticker-iso-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $IsoDir | Out-Null
try {
  $IsoExe = Join-Path $IsoDir "GoldTicker.exe"
  Copy-Item -Force $TargetExe $IsoExe
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $IsoExe
  $psi.Arguments = "--smoke-test"
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError = $true
  $psi.UseShellExecute = $false
  $p = [Diagnostics.Process]::Start($psi)
  $stdout = $p.StandardOutput.ReadToEnd()
  $stderr = $p.StandardError.ReadToEnd()
  if (-not $p.WaitForExit(20000)) { $p.Kill(); throw "Standalone smoke test timed out" }
  if ($p.ExitCode -ne 0) { throw "Standalone smoke failed ($($p.ExitCode)): $stderr" }
  Write-Host "Standalone smoke passed: $stdout"
} finally {
  Remove-Item -Recurse -Force $IsoDir -ErrorAction SilentlyContinue
}

$Zip = Join-Path $Out "GoldTicker-Windows-x64.zip"
Compress-Archive -Path $TargetExe -DestinationPath $Zip -Force

foreach ($f in @($TargetExe, $Zip)) {
  $leaf = Split-Path -Leaf $f
  $hash = (Get-FileHash $f -Algorithm SHA256).Hash.ToLower()
  "$hash  $leaf" | Set-Content ($f + ".sha256") -Encoding ascii
}

Get-ChildItem $Out | Format-Table Name, Length
