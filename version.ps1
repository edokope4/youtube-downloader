# Lee o incrementa la version del proyecto (archivo VERSION).
# Uso:
#   .\version.ps1
#   .\version.ps1 patch
#   .\version.ps1 minor
#   .\version.ps1 major

param(
    [Parameter(Position = 0)]
    [ValidateSet("get", "patch", "minor", "major")]
    [string]$Action = "get"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$VersionFile = Join-Path $PSScriptRoot "VERSION"
if (-not (Test-Path $VersionFile)) {
    throw "No se encontró el archivo VERSION."
}

$current = (Get-Content -Raw -Path $VersionFile).Trim()
if ($current -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION debe tener el formato MAJOR.MINOR.PATCH. Valor actual: $current"
}

if ($Action -eq "get") {
    Write-Output $current
    exit 0
}

$pieces = $current.Split(".")
$major = [int]$pieces[0]
$minor = [int]$pieces[1]
$patch = [int]$pieces[2]

switch ($Action) {
    "major" {
        $major++
        $minor = 0
        $patch = 0
    }
    "minor" {
        $minor++
        $patch = 0
    }
    "patch" {
        $patch++
    }
}

$next = "$major.$minor.$patch"
$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($VersionFile, "$next`n", $utf8)
Write-Output $next
