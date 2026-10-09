Write-Host "Criando ambiente virtual e instalando dependencias..."
python -m venv venv

.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m pip install pyinstaller pywin32

Write-Host "Compilando serviço em background (service.exe)..."
# O serviço Windows no PyInstaller precisa ser Console (não windowed) para o pywin32 funcionar
.\venv\Scripts\pyinstaller.exe --noconfirm --onefile `
    --hidden-import win32timezone `
    --hidden-import win32serviceutil `
    --hidden-import win32service `
    --hidden-import servicemanager `
    --hidden-import agent `
    --hidden-import src.application.updater `
    --collect-all imageio_ffmpeg `
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
