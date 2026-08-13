param(
    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root "backend\.venv\Scripts\python.exe"
$Npm = "npm.cmd"
$PyInstallerVersion = "6.10.0"
$Spec = Join-Path $Root "packaging\se-mentor.spec"
$DistRoot = Join-Path $Root "packaging\dist"
$WorkRoot = Join-Path $Root "packaging\build"
$FrontendBuildRoot = Join-Path ([System.IO.Path]::GetTempPath()) "se-mentor-frontend-build"
$FrontendDist = Join-Path $Root "frontend\dist"
$Distribution = Join-Path $DistRoot "SE-Mentor"
$Exe = Join-Path $Distribution "se-mentor.exe"

$IsWindowsHost = [System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [System.Runtime.InteropServices.OSPlatform]::Windows
)
if (-not $IsWindowsHost) {
    throw "scripts/build_windows.ps1 must run on Windows."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python virtual environment not found: $Python"
}
if (-not (Test-Path -LiteralPath $Spec)) {
    throw "PyInstaller spec not found: $Spec"
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location $Root
try {
    if (-not $SkipDependencyInstall) {
        Invoke-Checked $Python @("-m", "pip", "install", "pyinstaller==$PyInstallerVersion")
    }

    if (Test-Path -LiteralPath $DistRoot) {
        Remove-Item -LiteralPath $DistRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $WorkRoot) {
        Remove-Item -LiteralPath $WorkRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $FrontendBuildRoot) {
        Remove-Item -LiteralPath $FrontendBuildRoot -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path $FrontendBuildRoot | Out-Null
    Copy-Item -LiteralPath (Join-Path $Root "frontend\package.json") -Destination $FrontendBuildRoot
    Copy-Item -LiteralPath (Join-Path $Root "frontend\package-lock.json") -Destination $FrontendBuildRoot
    Copy-Item -LiteralPath (Join-Path $Root "frontend\index.html") -Destination $FrontendBuildRoot
    Copy-Item -LiteralPath (Join-Path $Root "frontend\tsconfig.json") -Destination $FrontendBuildRoot
    Copy-Item -LiteralPath (Join-Path $Root "frontend\src") -Destination $FrontendBuildRoot -Recurse
    Set-Content -LiteralPath (Join-Path $FrontendBuildRoot "vite.config.mjs") -Encoding utf8 -Value @'
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
'@

    Push-Location $FrontendBuildRoot
    try {
        Invoke-Checked $Npm @("ci")
        Invoke-Checked $Npm @("run", "build")
    }
    finally {
        Pop-Location
    }

    if (Test-Path -LiteralPath $FrontendDist) {
        Remove-Item -LiteralPath $FrontendDist -Recurse -Force
    }
    Copy-Item -LiteralPath (Join-Path $FrontendBuildRoot "dist") -Destination $FrontendDist -Recurse

    if (-not (Test-Path -LiteralPath (Join-Path $FrontendDist "index.html"))) {
        throw "frontend production build output is missing index.html"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Root "backend\migrations\env.py"))) {
        throw "migration resources are missing"
    }

    Invoke-Checked $Python @(
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        $DistRoot,
        "--workpath",
        $WorkRoot,
        $Spec
    )

    if (-not (Test-Path -LiteralPath $Exe)) {
        throw "launcher executable was not generated: $Exe"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Distribution "_internal\frontend\index.html"))) {
        throw "frontend assets were not packaged"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Distribution "_internal\migrations\env.py"))) {
        throw "migration assets were not packaged"
    }

    Invoke-Checked "powershell.exe" @(
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        (Join-Path $Root "scripts\smoke_windows.ps1"),
        "-DistPath",
        $Distribution
    )

    Write-Host "SE-Mentor Windows onedir package:"
    Write-Host $Distribution
    Write-Host "Launcher:"
    Write-Host $Exe
}
finally {
    if (Test-Path -LiteralPath $FrontendBuildRoot) {
        Remove-Item -LiteralPath $FrontendBuildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
