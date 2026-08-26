param(
    [int]$Port = 8000,
    [switch]$Install,
    [switch]$Migrate,
    [switch]$NoBrowser,
    [string]$Python
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

function Test-Python {
    param([string]$Path)

    if (-not $Path) {
        return $false
    }

    try {
        $output = & $Path -c "import sys; print(sys.executable)" 2>$null
        return $LASTEXITCODE -eq 0 -and $output
    }
    catch {
        return $false
    }
}

function Resolve-Python {
    $candidates = @()

    if ($Python) {
        $candidates += $Python
    }

    $candidates += @(
        (Join-Path $PSScriptRoot ".venv-local\Scripts\python.exe"),
        (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
        (Join-Path (Split-Path $PSScriptRoot -Parent) ".venv\Scripts\python.exe"),
        "python",
        "py"
    )

    foreach ($candidate in $candidates) {
        if (Test-Python $candidate) {
            return $candidate
        }
    }

    return $null
}

function Test-PythonModule {
    param(
        [string]$Path,
        [string]$Module
    )

    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Path -c "import $Module" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $oldPreference
    }
}

$pythonPath = Resolve-Python
$localVenvPython = Join-Path $PSScriptRoot ".venv-local\Scripts\python.exe"
$shouldInstall = [bool]$Install

if (-not $pythonPath) {
    Write-Host "No working Python was found."
    Write-Host "Install Python 3.11+, then run this script again:"
    Write-Host "  .\run.ps1 -Install -Migrate"
    exit 1
}

if ($pythonPath -notlike "*.venv-local*") {
    if (-not (Test-Path -LiteralPath $localVenvPython)) {
        Write-Host "Creating local virtual environment: .venv-local"
        & $pythonPath -m venv ".venv-local"
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to create .venv-local"
        }
        $shouldInstall = $true
    }

    if (Test-Python $localVenvPython) {
        $pythonPath = $localVenvPython
    }
}

Write-Host "Using Python: $pythonPath"

if (-not (Test-PythonModule $pythonPath "django")) {
    $shouldInstall = $true
}

if ($shouldInstall) {
    Write-Host "Installing dependencies from requirements.txt"
    & $pythonPath -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw "pip upgrade failed"
    }

    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "dependency install failed"
    }
}

& $pythonPath manage.py check
if ($LASTEXITCODE -ne 0) {
    throw "Django check failed"
}

if ($Migrate) {
    Write-Host "Applying migrations"
    & $pythonPath manage.py migrate
    if ($LASTEXITCODE -ne 0) {
        throw "migrations failed"
    }
}

$url = "http://127.0.0.1:$Port/"
Write-Host "Starting local server: $url"

if (-not $NoBrowser) {
    Start-Process $url -WindowStyle Hidden
}

& $pythonPath manage.py runserver "127.0.0.1:$Port"
