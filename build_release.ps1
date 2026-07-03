param(
    [string]$Version = "",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $Version) {
    $Version = (Get-Content -LiteralPath (Join-Path $Root "VERSION") -TotalCount 1).Trim()
}

$AppName = "HB_Automation"
$ReleaseRoot = Join-Path $Root "release"
$PackageDir = Join-Path $ReleaseRoot "${AppName}_v$Version"
$AppDir = Join-Path $PackageDir "app"
$InstallerSrc = Join-Path $Root "installer"

if ($Clean) {
    Remove-Item -LiteralPath (Join-Path $Root "build") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Root "dist") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $ReleaseRoot -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name $AppName `
    main.py

Remove-Item -LiteralPath $PackageDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

Copy-Item -LiteralPath (Join-Path $Root "dist\$AppName") -Destination $AppDir -Recurse -Force
Copy-Item -LiteralPath (Join-Path $InstallerSrc "install.cmd") -Destination (Join-Path $PackageDir "install.cmd") -Force
Copy-Item -LiteralPath (Join-Path $InstallerSrc "launch.cmd") -Destination (Join-Path $PackageDir "launch.cmd") -Force
Copy-Item -LiteralPath (Join-Path $InstallerSrc "uninstall.cmd") -Destination (Join-Path $PackageDir "uninstall.cmd") -Force
Copy-Item -LiteralPath (Join-Path $InstallerSrc "README_INSTALL.txt") -Destination (Join-Path $PackageDir "README_INSTALL.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "VERSION") -Destination (Join-Path $PackageDir "VERSION") -Force
Copy-Item -LiteralPath (Join-Path $Root "CHANGELOG.md") -Destination (Join-Path $PackageDir "CHANGELOG.md") -Force

$ZipPath = Join-Path $ReleaseRoot "${AppName}_v$Version.zip"
Remove-Item -LiteralPath $ZipPath -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $PackageDir -DestinationPath $ZipPath -Force

if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "Failed to create release zip: $ZipPath"
}

Write-Host ""
Write-Host "Release package created:"
Write-Host "  $ZipPath"
Write-Host ""
Write-Host "Give this zip file to team members. They only need to extract it and run install.cmd."
