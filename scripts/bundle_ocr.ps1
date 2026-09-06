$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$source = Join-Path $env:ProgramFiles 'Tesseract-OCR'
if (!(Test-Path (Join-Path $source 'tesseract.exe'))) {
    throw 'Install Tesseract OCR first (default location: Program Files\Tesseract-OCR).'
}
$dest = Join-Path $repo 'vendor\tesseract'
New-Item -ItemType Directory -Force $dest | Out-Null
# Keep engine DLLs and upstream license files together; omit the installer/uninstaller.
Get-ChildItem $source -File | Where-Object {
    $_.Extension -eq '.dll' -or $_.Name -eq 'tesseract.exe' -or $_.Name -match 'LICENSE|COPYING|NOTICE|AUTHORS'
} | Copy-Item -Destination $dest -Force
$data = Join-Path $dest 'tessdata'
New-Item -ItemType Directory -Force $data | Out-Null
# Version-tagged official Tesseract language models.
foreach ($lang in @('eng', 'jpn', 'jpn_vert', 'chi_sim', 'chi_tra', 'osd')) {
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/$lang.traineddata" -OutFile (Join-Path $data "$lang.traineddata")
}
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/LICENSE' -OutFile (Join-Path $data 'LICENSE')
Invoke-WebRequest 'https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.0/LICENSE' -OutFile (Join-Path $dest 'LICENSE-tesseract')
& (Join-Path $dest 'tesseract.exe') --list-langs --tessdata-dir $data
if ($LASTEXITCODE -ne 0) { throw 'Bundled OCR did not start.' }
