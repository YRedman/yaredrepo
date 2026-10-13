# Instalación del proyecto en Windows (equivalente a "npm install").
#
# Uso, desde la carpeta del proyecto:
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
#
# Qué hace:
#   1. Busca Python 3.10 o superior (prefiere 3.13 o 3.12).
#   2. Crea el entorno virtual .venv (si no existe).
#   3. Instala las dependencias de requirements.txt.
#   4. Busca Tesseract (OCR); si falta, intenta instalarlo con winget.
#   5. Descarga el idioma español de Tesseract (spa.traineddata) si falta.
#   6. Ejecuta el diagnóstico del proyecto.
#
# Opciones:
#   -SinOCR     no instala Tesseract ni el idioma español (los PDF escaneados quedarán sin texto)
#   -Pruebas    instala también las dependencias de las pruebas (requirements-dev.txt)

param(
    [switch]$SinOCR,
    [switch]$Pruebas
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Aviso($texto) { Write-Host "AVISO: $texto" -ForegroundColor Yellow }

# 1. Python ------------------------------------------------------------------
Paso "Buscando Python"
$python = $null        # comando y argumentos, p. ej. @("py", "-3.13")
foreach ($candidato in @("py -3.13", "py -3.12", "py -3.11", "py -3.10", "python", "python3")) {
    $partes = $candidato.Split(" ")
    $exe = $partes[0]
    $extra = @($partes | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    try {
        $salida = & $exe @extra -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        $codigo = $LASTEXITCODE    # leerlo antes de cualquier tuberia: Select-Object -First lo deja vacio
    } catch { continue }
    $version = @($salida)[0]
    if ($codigo -ne 0 -or -not $version) { continue }
    $mayor, $menor = $version.Trim().Split(".")
    if ([int]$mayor -eq 3 -and [int]$menor -ge 10) {
        $python = @($exe) + $extra
        Write-Host "Python $version ($candidato)"
        if ([int]$menor -ge 14) {
            Aviso "Python $version es muy nuevo: si alguna librería no instala, use Python 3.12 o 3.13."
        }
        break
    }
}
if (-not $python) {
    Write-Host ("No encontré Python 3.10 o superior. Instálelo desde https://www.python.org/downloads/ " +
                "(marque 'Add python.exe to PATH') y vuelva a ejecutar este script.") -ForegroundColor Red
    exit 1
}

# 2. Entorno virtual -----------------------------------------------------------
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Paso "Creando el entorno virtual .venv"
    $extra = @($python | Select-Object -Skip 1)
    & $python[0] @extra -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo crear el entorno virtual." -ForegroundColor Red; exit 1 }
} else {
    Paso "Usando el entorno virtual existente .venv"
}

# 3. Dependencias de Python -----------------------------------------------------
Paso "Instalando dependencias de Python (requirements.txt)"
& $venvPython -m pip install --upgrade pip --quiet
$requisitos = "requirements.txt"
if ($Pruebas) { $requisitos = "requirements-dev.txt" }
& $venvPython -m pip install -r $requisitos
if ($LASTEXITCODE -ne 0) { Write-Host "Falló la instalación de dependencias (ver el mensaje de pip)." -ForegroundColor Red; exit 1 }

# 4 y 5. Tesseract (OCR) e idioma español ---------------------------------------------
function Buscar-Tesseract {
    $rutas = @()
    if ($env:TESSERACT_CMD) { $rutas += $env:TESSERACT_CMD }
    $enPath = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($enPath) { $rutas += $enPath.Source }
    $rutas += (Join-Path $env:LOCALAPPDATA "Programs\Tesseract-OCR\tesseract.exe")
    if ($env:ProgramFiles) { $rutas += (Join-Path $env:ProgramFiles "Tesseract-OCR\tesseract.exe") }
    if (${env:ProgramFiles(x86)}) { $rutas += (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR\tesseract.exe") }
    foreach ($r in $rutas) { if ($r -and (Test-Path $r)) { return $r } }
    return $null
}

if (-not $SinOCR) {
    Paso "Buscando Tesseract (OCR para PDF escaneados)"
    $tesseract = Buscar-Tesseract
    if (-not $tesseract) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "Tesseract no está instalado; instalándolo con winget..."
            try {
                winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements
            } catch { Aviso "winget no pudo instalar Tesseract: $_" }
            $tesseract = Buscar-Tesseract
        }
        if (-not $tesseract) {
            Aviso ("Instale Tesseract a mano: https://github.com/UB-Mannheim/tesseract/wiki (en 'Choose Components' " +
                   "marque Additional language data -> Spanish) y vuelva a ejecutar este script.")
        }
    }
    if ($tesseract) {
        Write-Host "Tesseract: $tesseract"
        $tessdata = Join-Path (Split-Path $tesseract) "tessdata"
        $spa = Join-Path $tessdata "spa.traineddata"
        $idiomas = @(& $tesseract --list-langs 2>$null) | ForEach-Object { "$_".Trim() }
        if ($idiomas -notcontains "spa") {
            Paso "Descargando el idioma español de Tesseract (spa.traineddata)"
            try {
                Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/spa.traineddata" -OutFile $spa
                Write-Host "Idioma español instalado en $tessdata"
            } catch {
                Aviso ("No se pudo descargar o guardar spa.traineddata ($_). Descárguelo de " +
                       "https://github.com/tesseract-ocr/tessdata/blob/main/spa.traineddata y cópielo en $tessdata " +
                       "(si la carpeta está en Program Files, hace falta permiso de administrador).")
            }
        } else {
            Write-Host "Idioma español: ya instalado"
        }
    }
}

# 6. Diagnóstico ----------------------------------------------------------------
Paso "Diagnóstico"
& $venvPython scripts\convertir.py diagnostico
$ok = ($LASTEXITCODE -eq 0)

Write-Host ""
if ($ok) {
    Write-Host "Instalación completa." -ForegroundColor Green
} else {
    Aviso "La instalación terminó con piezas faltantes (ver el diagnóstico arriba)."
}
Write-Host @"

Siguientes pasos:
  1. Active el entorno en cada terminal nueva:   .\.venv\Scripts\Activate.ps1
  2. Ponga los documentos en entrada\Descriptivos\ (y entrada\Procedimientos\ si los hay).
  3. Construya el corpus:
       python scripts\convertir.py construir --entrada entrada --contexto contexto --salida salida_corpus
"@
