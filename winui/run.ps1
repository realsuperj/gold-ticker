# Build & launch GoldTicker WinUI shell (Python core via IPC).
# Requires: .NET 8 SDK, Python 3.9+, pip install -r requirements.txt
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $Root) { $Root = (Resolve-Path "$PSScriptRoot\..").Path }
$Proj = Join-Path $PSScriptRoot "GoldTicker.WinUI\GoldTicker.WinUI.csproj"

$env:GOLDTICKER_ROOT = $Root
if (-not $env:GOLDTICKER_PYTHON) {
  $py = Get-Command python -ErrorAction SilentlyContinue
  if ($py) { $env:GOLDTICKER_PYTHON = $py.Source }
}

Write-Host "Repo: $Root"
Write-Host "Building WinUI..."
dotnet build $Proj -c Release -p:Platform=x64
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Launching..."
dotnet run --project $Proj -c Release -p:Platform=x64 --no-build
