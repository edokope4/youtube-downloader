# YouTube Downloader

Interfaz gráfica para descargar un video de YouTube. La versión actual es la del archivo `VERSION`.

## Qué se puede hacer

- Pegar el enlace de un video (`youtube.com` o `youtu.be`).
- Cargar las calidades disponibles y elegir una.
- Descargar solo el audio, en MP3.
- Elegir la carpeta de destino. Si no se cambia, usa `Descargas`.
- Ver el avance y cancelar la descarga.
- Abrir la carpeta del archivo guardado.

## Requisitos

- Windows de 64 bits.
- Python 3.11 o superior, para ejecutarlo desde el código.
- FFmpeg, para unir imagen y audio y para guardar el MP3.

`build.bat` descarga una build LGPL de FFmpeg y la incluye en el ejecutable. Si se corre desde el código, FFmpeg tiene que estar en el `PATH` o en `vendor\ffmpeg` (esa carpeta la crea el script de compilación).

## Ejecutar desde el código

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

También se puede usar:

```powershell
python main.py --version
python main.py --check
```

`--version` muestra la versión del proyecto. `--check` muestra la versión y si FFmpeg está disponible.

## Generar el ejecutable

```powershell
.\build.bat
```

El resultado queda en `dist\YouTubeDownloader-<version>.exe`. La primera apertura puede tardar unos segundos porque el archivo se desempaqueta al iniciarse.

## Versión del proyecto

La fuente de la versión es el archivo `VERSION`, con el formato `MAJOR.MINOR.PATCH`. Ese número se muestra en la ventana y se incrusta en el ejecutable.

```powershell
.\version.ps1          # muestra la versión actual
.\version.ps1 patch    # 1.0.0 -> 1.0.1
.\version.ps1 minor    # 1.0.1 -> 1.1.0
.\version.ps1 major    # 1.1.0 -> 2.0.0
```

Después de cambiar la versión, hay que volver a ejecutar `build.bat` para que el `.exe` lleve el número nuevo.

Usa el programa solo con videos que tengas derecho a descargar.
