# agent/ferramentas/

Ferramentas avulsas de apoio, separadas do agente em 26/11/2026. **Não entram** no serviço, no instalador nem na
imagem do Mikrotik: a raiz de `agent/` ficou só com os pontos de entrada do produto (`service.py`, `tray.py`,
`agent.py`, `service_linux.py`, `launcher_linux.py`) e os scripts de build e publicação.

| Arquivo | Para que serve | Como usar |
|---|---|---|
| `baixar_fotos_facial.py` | Baixa as fotos cadastradas numa leitora facial Intelbras, cada uma com o nome da pessoa | Usado pela tela abaixo |
| `baixar_fotos_facial_gui.py` | Tela (tkinter) para o técnico escolher a facial e a pasta | `python ferramentas/baixar_fotos_facial_gui.py` |
| `build_baixar_fotos.ps1` | Gera `ferramentas/dist_ferramentas/BaixarFotosFacial.exe` (PyInstaller) | `./ferramentas/build_baixar_fotos.ps1` |
| `testar_olt_loop.py` | Coleta o estado das OLTs a cada 60 s e envia ao servidor, sem instalar o agente | Na pasta `agent/`: `python ferramentas/testar_olt_loop.py` (lê o `agent/agent.conf`) |
