# Gera dist_ferramentas\BaixarFotosFacial.exe (tela para baixar as fotos de uma facial Intelbras).
$ErrorActionPreference = "Continue"  # o PyInstaller escreve o progresso em stderr
Set-Location $PSScriptRoot
$py = "python"
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name BaixarFotosFacial `
    --distpath dist_ferramentas --workpath build_ferramentas --specpath build_ferramentas `
    --paths . baixar_fotos_facial_gui.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou (codigo $LASTEXITCODE)" }
Write-Host "Pronto: $PSScriptRoot\dist_ferramentas\BaixarFotosFacial.exe"
