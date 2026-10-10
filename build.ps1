# Compila YouTube Downloader y genera dist\YouTubeDownloader-<version>.exe
# Uso: clic derecho > Ejecutar con PowerShell, o desde la carpeta del proyecto:
#   .\build.bat
#   .\build.ps1

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = $PSScriptRoot
Set-Location $Root

function Get-ProjectVersion {
    $versionFile = Join-Path $Root "VERSION"
    if (-not (Test-Path $versionFile)) {
        throw "No se encontró el archivo VERSION."
    }
    $version = (Get-Content -Raw -Path $versionFile).Trim()
    if ($version -notmatch '^\d+\.\d+\.\d+$') {
        throw "VERSION debe tener el formato MAJOR.MINOR.PATCH. Valor actual: $version"
    }
    return $version
}

function Ensure-Venv {
    $python = Join-Path $Root ".venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        Write-Host "Creando entorno virtual..."
        & python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) {
            throw "Se necesita Python 3.11 o superior."
        }
        & python -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo crear el entorno virtual."
        }
    }
    return $python
}

function Ensure-Ffmpeg {
    $dest = Join-Path $Root "vendor\ffmpeg"
    $ffmpeg = Join-Path $dest "ffmpeg.exe"
    $ffprobe = Join-Path $dest "ffprobe.exe"
    if ((Test-Path $ffmpeg) -and (Test-Path $ffprobe)) {
        Write-Host "FFmpeg ya está en vendor\ffmpeg"
        return
    }

    Write-Host "Descargando FFmpeg (build LGPL para Windows de 64 bits)..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("ffmpeg-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    try {
        $zip = Join-Path $tempRoot "ffmpeg.zip"
        $url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
        $extract = Join-Path $tempRoot "extract"
        Expand-Archive -Path $zip -DestinationPath $extract
        $found = Get-ChildItem -Path $extract -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
        if (-not $found) {
            throw "El paquete de FFmpeg no contiene ffmpeg.exe."
        }
        $probe = Join-Path $found.DirectoryName "ffprobe.exe"
        if (-not (Test-Path $probe)) {
            throw "El paquete de FFmpeg no contiene ffprobe.exe."
        }
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        Copy-Item $found.FullName (Join-Path $dest "ffmpeg.exe") -Force
        Copy-Item $probe (Join-Path $dest "ffprobe.exe") -Force
    }
    finally {
        if (Test-Path $tempRoot) {
            Remove-Item -Recurse -Force $tempRoot
        }
    }
}

$version = Get-ProjectVersion
Write-Host "Compilando YouTube Downloader $version"
$venvPython = Ensure-Venv

Write-Host "Instalando dependencias..."
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip no pudo actualizarse." }
& $venvPython -m pip install -r (Join-Path $Root "requirements.txt") "pyinstaller>=6.3"
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias." }

Ensure-Ffmpeg

$buildDir = Join-Path $Root ".build"
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$versionInfo = Join-Path $buildDir "version_info.txt"
& $venvPython (Join-Path $Root "packaging\write_version_info.py") (Join-Path $Root "VERSION") $versionInfo
if ($LASTEXITCODE -ne 0) { throw "No se pudo generar el recurso de version." }

$exeName = "YouTubeDownloader-$version"
Write-Host "Generando $exeName.exe ..."
& $venvPython -m PyInstaller @(
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onefile",
    "--name", $exeName,
    "--version-file", $versionInfo,
    "--distpath", (Join-Path $Root "dist"),
    "--workpath", (Join-Path $Root "build"),
    "--specpath", $buildDir,
    "--paths", $Root,
    "--add-data", ((Join-Path $Root "VERSION") + ";."),
    "--add-data", ((Join-Path $Root "vendor\ffmpeg") + ";vendor/ffmpeg"),
    "--collect-all", "yt_dlp",
    "--collect-submodules", "youtube_downloader",
    "main.py"
)
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló." }

$exePath = Join-Path $Root "dist\$exeName.exe"
if (-not (Test-Path $exePath)) {
    throw "No se genero el ejecutable esperado: $exePath"
}

Write-Host ""
Write-Host "Listo: $exePath"
Write-Host "FFmpeg queda dentro del .exe. Si copias el programa a otra carpeta, copia solo ese archivo."
