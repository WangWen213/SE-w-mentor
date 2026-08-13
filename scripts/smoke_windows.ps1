param(
    [string]$DistPath = "",
    [switch]$LaunchCheck
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
if ([string]::IsNullOrWhiteSpace($DistPath)) {
    $DistPath = Join-Path $Root "packaging\dist\SE-Mentor"
}
$Dist = Resolve-Path $DistPath
$Exe = Join-Path $Dist "se-mentor.exe"
$Internal = Join-Path $Dist "_internal"

if (-not (Test-Path -LiteralPath $Exe)) {
    throw "launcher executable is missing: $Exe"
}
if (-not (Test-Path -LiteralPath (Join-Path $Internal "frontend\index.html"))) {
    throw "frontend assets are missing from distribution"
}
if (-not (Test-Path -LiteralPath (Join-Path $Internal "migrations\env.py"))) {
    throw "migration assets are missing from distribution"
}

$ForbiddenPatterns = @(
    "\.env$",
    "\.pem$",
    "\.key$",
    "\.sqlite$",
    "\.sqlite3$",
    "\.db$",
    "perf-runtime\.log$",
    "(^|\\)backups?(\\|$)",
    "(^|\\)credentials?(\\|$)",
    "(^|\\)secrets?(\\|$)"
)

$Forbidden = @()
Get-ChildItem -LiteralPath $Dist -Recurse -Force | ForEach-Object {
    $Relative = $_.FullName.Substring($Dist.Path.Length).TrimStart("\")
    foreach ($Pattern in $ForbiddenPatterns) {
        if ($Relative -match $Pattern) {
            $Forbidden += $Relative
            break
        }
    }
}
if ($Forbidden.Count -gt 0) {
    throw "forbidden runtime or secret-like artifacts found in distribution: $($Forbidden -join ', ')"
}

$TextFiles = Get-ChildItem -LiteralPath $Dist -Recurse -File -Include *.txt,*.json,*.html,*.js,*.css,*.py,*.ini -Force
foreach ($File in $TextFiles) {
    $Content = Get-Content -LiteralPath $File.FullName -Raw -ErrorAction SilentlyContinue
    if ($Content -match "sk-[A-Za-z0-9_-]{20,}" -or
        $Content -match "-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----" -or
        $Content -match "AKIA[0-9A-Z]{16}") {
        throw "secret-like literal found in distribution text resource: $($File.FullName)"
    }
}

if ($LaunchCheck) {
    $Port = 18050
    $Runtime = Join-Path ([System.IO.Path]::GetTempPath()) "se-mentor-smoke-$([guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
    $Env:SE_MENTOR_NO_BROWSER = "1"
    $Env:SE_MENTOR_PORT = [string]$Port
    $Env:SE_MENTOR_RUNTIME_ROOT = $Runtime
    $Process = Start-Process -FilePath $Exe -PassThru -WindowStyle Hidden
    try {
        $Ready = $false
        for ($Attempt = 0; $Attempt -lt 30; $Attempt++) {
            Start-Sleep -Seconds 1
            try {
                $Response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
                if ($Response.StatusCode -eq 200) {
                    $Ready = $true
                    break
                }
            }
            catch {
            }
        }
        if (-not $Ready) {
            throw "launcher did not become ready during smoke check"
        }
    }
    finally {
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id
        }
        Remove-Item -LiteralPath $Runtime -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item Env:\SE_MENTOR_NO_BROWSER -ErrorAction SilentlyContinue
        Remove-Item Env:\SE_MENTOR_PORT -ErrorAction SilentlyContinue
        Remove-Item Env:\SE_MENTOR_RUNTIME_ROOT -ErrorAction SilentlyContinue
    }
}

Write-Host "Windows package smoke checks passed:"
Write-Host $Dist
