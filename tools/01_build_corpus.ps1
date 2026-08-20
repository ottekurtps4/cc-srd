$ErrorActionPreference = "Stop"

$Root = "C:\Users\p1\Desktop\embeddings"
$Script = Join-Path $Root "01_build_corpus.py"

Write-Host ""
Write-Host "BOOK BUCKET - CORPUS BUILDER"
Write-Host "Root: $Root"
Write-Host ""

if (-not (Test-Path $Script)) {
    Write-Host "ERROR: Python script not found:"
    Write-Host $Script
    Read-Host "Press Enter to close"
    exit 1
}

$Python = $null

if (Get-Command py -ErrorAction SilentlyContinue) {
    $Python = "py"
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $Python = "python"
}
else {
    Write-Host "ERROR: Python was not found in PATH."
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host "Checking PyMuPDF..."

if ($Python -eq "py") {
    & py -c "import pymupdf; print('PyMuPDF OK')" 2>$null

    if ($LASTEXITCODE -ne 0) {
        & py -c "import fitz; print('PyMuPDF/fitz OK')" 2>$null
    }
}
else {
    & python -c "import pymupdf; print('PyMuPDF OK')" 2>$null

    if ($LASTEXITCODE -ne 0) {
        & python -c "import fitz; print('PyMuPDF/fitz OK')" 2>$null
    }
}

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: PyMuPDF is not available to this Python installation."
    Write-Host "Install PyMuPDF into this same Python environment first."
    Read-Host "Press Enter to close"
    exit 1
}

Write-Host ""
Write-Host "Starting corpus build..."
Write-Host ""

if ($Python -eq "py") {
    & py $Script
}
else {
    & python $Script
}

$ExitCode = $LASTEXITCODE

Write-Host ""

if ($ExitCode -eq 0) {
    Write-Host "Corpus pass finished."
}
else {
    Write-Host "Corpus pass returned exit code $ExitCode."
}

Write-Host ""
Read-Host "Press Enter to close"

exit $ExitCode
