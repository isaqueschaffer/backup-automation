"""Tela para baixar as fotos cadastradas numa facial Intelbras: informa IP, usuario e senha, escolhe a pasta e baixa
cada foto com o nome da pessoa (usa baixar_fotos_facial.py). Gerado como executavel por build_baixar_fotos.ps1."""
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import requests

from baixar_fotos_facial import baixar


class Tela(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Baixar fotos da facial Intelbras")
        self.resizable(False, False)
        self._parar = threading.Event()
        self._fila = []
        quadro = ttk.Frame(self, padding=14)
        quadro.grid()
        self.ip = tk.StringVar()
        self.usuario = tk.StringVar(value="admin")
        self.senha = tk.StringVar()
        self.pasta = tk.StringVar(value=str(Path.home() / "Pictures" / "Fotos da facial"))
        for linha, (rotulo, var, mostrar) in enumerate((("IP da facial", self.ip, ""), ("Usuário", self.usuario, ""),
                                                        ("Senha", self.senha, "*"))):
            ttk.Label(quadro, text=rotulo).grid(row=linha, column=0, sticky="w", pady=3)
            ttk.Entry(quadro, textvariable=var, width=34, show=mostrar).grid(row=linha, column=1, columnspan=2, pady=3)
        ttk.Label(quadro, text="Pasta de destino").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(quadro, textvariable=self.pasta, width=27).grid(row=3, column=1, pady=3)
        ttk.Button(quadro, text="Escolher...", command=self._escolher).grid(row=3, column=2, padx=(6, 0))
        self.botao = ttk.Button(quadro, text="Baixar fotos", command=self._iniciar)
        self.botao.grid(row=4, column=0, columnspan=3, pady=(10, 4), sticky="ew")
        self.barra = ttk.Progressbar(quadro, length=330)
        self.barra.grid(row=5, column=0, columnspan=3, pady=4)
        self.estado = ttk.Label(quadro, text="", wraplength=330, justify="left")
        self.estado.grid(row=6, column=0, columnspan=3, sticky="w")

    def _escolher(self):
        pasta = filedialog.askdirectory(title="Pasta para salvar as fotos")
        if pasta:
            self.pasta.set(pasta)

    def _iniciar(self):
        if not self.ip.get().strip() or not self.usuario.get().strip() or not self.senha.get() or not self.pasta.get().strip():
            messagebox.showwarning("Faltam dados", "Preencha IP, usuário, senha e a pasta de destino.")
            return
        self.botao.config(state="disabled")
        self.barra.config(value=0)
        self.estado.config(text="Conectando...")
        threading.Thread(target=self._trabalhar, daemon=True).start()

    def _trabalhar(self):
        def progresso(feitas, total, nome):
            self.after(0, self._atualizar, feitas, total, nome)

        try:
            r = baixar(self.ip.get().strip(), self.usuario.get().strip(), self.senha.get(), Path(self.pasta.get().strip()), progresso)
            texto = f"{r['salvas']} foto(s) salva(s) de {r['pessoas']} pessoa(s)."
            if r["sem_foto"]:
                texto += "\nSem foto cadastrada: " + ", ".join(r["sem_foto"])
            self.after(0, self._fim, texto)
        except requests.exceptions.HTTPError as e:
            erro = "Usuário ou senha incorretos." if e.response is not None and e.response.status_code == 401 else f"A facial recusou o pedido ({e})."
            self.after(0, self._fim, erro)
        except Exception as e:
            self.after(0, self._fim, f"Não foi possível baixar: {e}")

    def _atualizar(self, feitas, total, nome):
        self.barra.config(maximum=max(total, 1), value=feitas)
        self.estado.config(text=f"{feitas}/{total} {nome}")

    def _fim(self, texto):
        self.botao.config(state="normal")
        self.estado.config(text=texto)


if __name__ == "__main__":
    Tela().mainloop()
