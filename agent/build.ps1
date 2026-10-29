Write-Host "Criando ambiente virtual e instalando dependencias..."
# Python fixo (o build atual usa o 3.14.8), não o que estiver no PATH
py -3.14 -m venv venv

.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install pyinstaller==6.22.3 pywin32==312

Write-Host "Compilando serviço em background (service.exe)..."
# O serviço Windows no PyInstaller precisa ser Console (não windowed) para o pywin32 funcionar
.\venv\Scripts\pyinstaller.exe --noconfirm --onefile `
    --hidden-import win32timezone `
    --hidden-import win32serviceutil `
    --hidden-import win32service `
    --hidden-import servicemanager `
    --hidden-import agent `
    --hidden-import src.application.updater `
    --hidden-import src.application.backup_job `
    --hidden-import src.application.webhook_digifort `
    --hidden-import src.application.webhook_defense `
    --hidden-import src.olt.huawei_active `
    --hidden-import psutil `
    --hidden-import GPUtil `
    --collect-all imageio_ffmpeg `
    --collect-all pysnmp `
    --collect-all pyasn1 `
    --name TrilanAgentService `
    service.py

Write-Host "Compilando aplicativo da bandeja (tray.exe)..."
.\venv\Scripts\pyinstaller.exe --noconfirm --onefile --windowed `
    --collect-all pystray `
    --collect-all PIL `
    --hidden-import pystray `
    --hidden-import pystray._win32 `
    --name TrilanAgentTray `
    tray.py

Write-Host "Limpando arquivos temporários..."
Remove-Item -Recurse -Force build
Remove-Item TrilanAgentService.spec
Remove-Item TrilanAgentTray.spec

Write-Host "======================================"
Write-Host "Build concluído! Executáveis na pasta 'dist'"
Write-Host "======================================"
