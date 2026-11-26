import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Bot, Copy, KeyRound, Trash2 } from "lucide-react";
import api from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useToast } from "../components/Toast";
import { useConfirm } from "../components/ConfirmDialog";
import { apiErrorMessage } from "../utils/errors";
import { fmtDate } from "../utils/date";

interface AcessoMcp {
  id: string;
  tipo: "PESSOAL" | "OAUTH";
  nome: string;
  criado_em: string;
  ultimo_uso: string | null;
  expira_em: string | null;
}

type Cliente = "claude" | "chatgpt" | "gemini" | "antigravity";

const ABAS: { id: Cliente; rotulo: string }[] = [
  { id: "claude", rotulo: "Claude" },
  { id: "chatgpt", rotulo: "ChatGPT" },
  { id: "gemini", rotulo: "App do Gemini" },
  { id: "antigravity", rotulo: "Antigravity / Gemini CLI" },
];

const blocoCodigo: React.CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
  fontSize: 12.5,
  background: "var(--surface-2)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius-sm)",
  padding: "10px 12px",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  margin: "8px 0",
};

async function copiar(texto: string, toast: (m: string, t?: "success" | "error" | "info") => void) {
  try {
    await navigator.clipboard.writeText(texto);
    toast("Copiado.", "success");
  } catch {
    toast("Não foi possível copiar automaticamente. Use Ctrl+C.", "info");
  }
}

// "Conectar IA (MCP)" em Minha conta: endereço do MCP, passo a passo por aplicativo, tokens pessoais e conexões.
export default function ConexaoIA() {
  const { me } = useAuth();
  const { toast } = useToast();
  const confirmar = useConfirm();
  const papelOk = me?.usuario.papel === "ADMIN" || me?.usuario.papel === "SUPER_ADMIN";
  const temUsuario = !!me?.usuario.id;

  const [url, setUrl] = useState("");
  const [acessos, setAcessos] = useState<AcessoMcp[]>([]);
  const [aba, setAba] = useState<Cliente>("claude");
  const [nomeToken, setNomeToken] = useState("");
  const [gerando, setGerando] = useState(false);
  const [tokenNovo, setTokenNovo] = useState<string | null>(null);

  const carregar = useCallback(() => {
    api.get("/mcp/info").then((r) => setUrl(r.data.url)).catch(() => {});
    api.get("/mcp/tokens").then((r) => setAcessos(r.data)).catch(() => {});
  }, []);

  useEffect(() => {
    if (papelOk && temUsuario) carregar();
  }, [papelOk, temUsuario, carregar]);

  if (!papelOk) return null;

  if (!temUsuario) {
    return (
      <div className="card" style={{ marginTop: 24, maxWidth: 720 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 8px" }}>Conectar IA (MCP)</h3>
        <p className="text-secondary" style={{ fontSize: 14, margin: 0 }}>
          Para conectar Claude, ChatGPT ou Gemini, entre com um usuário com e-mail (o login só com senha não pode).
        </p>
      </div>
    );
  }

  const gerar = async (e: FormEvent) => {
    e.preventDefault();
    if (!nomeToken.trim()) return;
    setGerando(true);
    try {
      const r = await api.post("/mcp/tokens", { nome: nomeToken.trim() });
      setTokenNovo(r.data.token);
      setNomeToken("");
      carregar();
    } catch (err) {
      toast(apiErrorMessage(err, "Não foi possível gerar o token."), "error");
    } finally {
      setGerando(false);
    }
  };

  const desconectar = async (a: AcessoMcp) => {
    const ok = await confirmar({
      title: a.tipo === "PESSOAL" ? "Revogar token" : "Desconectar aplicativo",
      message: `"${a.nome}" perde o acesso ao sistema na hora. Para voltar, será preciso conectar de novo.`,
      confirmLabel: a.tipo === "PESSOAL" ? "Revogar" : "Desconectar",
      variant: "danger",
    });
    if (!ok) return;
    try {
      await api.delete(`/mcp/tokens/${a.id}`);
      toast("Acesso removido.", "success");
      carregar();
    } catch (err) {
      toast(apiErrorMessage(err, "Não foi possível remover o acesso."), "error");
    }
  };

  const enderecoMcp = url || "https://server.suportetrilan.com.br/mcp";
  const configGemini = JSON.stringify(
    { mcpServers: { "trilan-backups": { httpUrl: enderecoMcp, headers: { Authorization: `Bearer ${tokenNovo ?? "<seu token>"}` } } } },
    null,
    2,
  );
  const configAntigravity = JSON.stringify(
    { mcpServers: { "trilan-backups": { serverUrl: enderecoMcp, headers: { Authorization: `Bearer ${tokenNovo ?? "<seu token>"}` } } } },
    null,
    2,
  );

  return (
    <div className="card" style={{ marginTop: 24, maxWidth: 720 }}>
      <h3 style={{ fontSize: 16, fontWeight: 600, margin: "0 0 6px", display: "flex", alignItems: "center", gap: 8 }}>
        <Bot size={18} /> Conectar IA (MCP)
      </h3>
      <p className="text-secondary" style={{ fontSize: 14, margin: "0 0 14px" }}>
        Claude, ChatGPT e Gemini podem consultar e alterar o sistema por você, com as mesmas permissões que você tem
        aqui. Tudo o que a IA alterar aparece na Auditoria como "{me?.usuario.email} (IA via MCP)". Ações que apagam ou
        afetam todas as máquinas pedem a sua confirmação no aplicativo.
      </p>

      <div className="text-xs text-muted">Endereço do servidor MCP</div>
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <code style={{ ...blocoCodigo, flex: 1, minWidth: 0 }}>{enderecoMcp}</code>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => copiar(enderecoMcp, toast)}>
          <Copy size={14} /> Copiar
        </button>
      </div>

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", margin: "16px 0 8px" }} role="tablist">
        {ABAS.map((a) => (
          <button
            key={a.id}
            type="button"
            role="tab"
            aria-selected={aba === a.id}
            className={`btn btn-sm ${aba === a.id ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setAba(a.id)}
          >
            {a.rotulo}
          </button>
        ))}
      </div>

      <div className="text-secondary" style={{ fontSize: 14, lineHeight: 1.6 }}>
        {aba === "claude" && (
          <ol style={{ paddingLeft: 20, margin: 0 }}>
            <li>No claude.ai (ou no app), abra <strong>Configurações → Conectores</strong> e clique em <strong>Adicionar conector personalizado</strong>.</li>
            <li>Nome: <strong>Trilan Backups</strong>. URL: o endereço acima. Salve e clique em <strong>Conectar</strong>.</li>
            <li>Abre a tela de login do Trilan: entre com seu e-mail e senha. Pronto.</li>
            <li>Na conversa, ative o conector no menu de ferramentas. Em times (Team/Enterprise) o dono da organização adiciona o conector primeiro.</li>
          </ol>
        )}
        {aba === "chatgpt" && (
          <ol style={{ paddingLeft: 20, margin: 0 }}>
            <li>No chatgpt.com, abra <strong>Configurações → Aplicativos e conectores → Avançado</strong> e ative o <strong>Modo desenvolvedor</strong>.</li>
            <li>Em <strong>Aplicativos e conectores</strong>, clique em <strong>Criar</strong>. Nome: <strong>Trilan Backups</strong>. URL: o endereço acima. Autenticação: <strong>OAuth</strong>.</li>
            <li>Abre a tela de login do Trilan: entre com seu e-mail e senha.</li>
            <li>Na conversa, escolha o conector em <strong>+ → Modo desenvolvedor</strong>. As ações que alteram pedem confirmação. A disponibilidade do modo desenvolvedor depende do plano do ChatGPT.</li>
          </ol>
        )}
        {aba === "gemini" && (
          <ol style={{ paddingLeft: 20, margin: 0 }}>
            <li>No gemini.google.com (computador), abra <strong>Configurações → Apps conectados</strong> e clique em <strong>Adicionar app personalizado</strong>.</li>
            <li>Cole o endereço acima, avance e entre com seu e-mail e senha do Trilan.</li>
            <li>Depois de adicionado no computador, funciona também no app do celular.</li>
            <li>O Google ainda limita esse recurso por país e plano; se a opção não aparecer na sua conta, use o Antigravity / Gemini CLI.</li>
          </ol>
        )}
        {aba === "antigravity" && (
          <>
            <p style={{ margin: "0 0 6px" }}>
              Esses aplicativos usam um <strong>token pessoal</strong>. Gere um abaixo e cole a configuração:
            </p>
            <div className="text-xs text-muted" style={{ marginTop: 8 }}>Antigravity (Gerenciar servidores MCP → Ver configuração bruta, mcp_config.json)</div>
            <pre style={blocoCodigo}>{configAntigravity}</pre>
            <div className="text-xs text-muted">Gemini CLI (~/.gemini/settings.json)</div>
            <pre style={blocoCodigo}>{configGemini}</pre>
          </>
        )}
      </div>

      <h4 style={{ fontSize: 14, fontWeight: 600, margin: "20px 0 8px", display: "flex", alignItems: "center", gap: 6 }}>
        <KeyRound size={15} /> Token pessoal
      </h4>
      {tokenNovo ? (
        <div style={{ border: "1px solid var(--warn)", background: "var(--warn-bg)", borderRadius: "var(--radius-sm)", padding: 12 }}>
          <div style={{ fontSize: 13, color: "var(--warn)", fontWeight: 600 }}>
            Copie agora: este token não aparece de novo. Ele dá acesso ao sistema como você; não compartilhe.
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <code style={{ ...blocoCodigo, flex: 1, minWidth: 0 }}>{tokenNovo}</code>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => copiar(tokenNovo, toast)}>
              <Copy size={14} /> Copiar
            </button>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setTokenNovo(null)}>Já copiei</button>
        </div>
      ) : (
        <form onSubmit={gerar} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            className="form-input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder='Nome do uso (ex.: "Antigravity do notebook")'
            value={nomeToken}
            onChange={(e) => setNomeToken(e.target.value)}
            maxLength={100}
            disabled={gerando}
          />
          <button type="submit" className="btn btn-primary" disabled={gerando || !nomeToken.trim()}>
            {gerando ? "Gerando…" : "Gerar token"}
          </button>
        </form>
      )}

      <h4 style={{ fontSize: 14, fontWeight: 600, margin: "20px 0 8px" }}>Conexões ativas</h4>
      {acessos.length === 0 ? (
        <p className="text-muted" style={{ fontSize: 13, margin: 0 }}>Nenhuma IA conectada.</p>
      ) : (
        <div className="table-wrap">
          <table className="tabela-cartoes">
            <thead>
              <tr>
                <th>Nome</th>
                <th>Tipo</th>
                <th>Criado em</th>
                <th>Último uso</th>
                <th aria-label="Ações" />
              </tr>
            </thead>
            <tbody>
              {acessos.map((a) => (
                <tr key={a.id}>
                  <td data-label="Nome">{a.nome}</td>
                  <td data-label="Tipo">{a.tipo === "PESSOAL" ? "Token pessoal" : "Login do aplicativo"}</td>
                  <td data-label="Criado em">{fmtDate(a.criado_em, { short: true })}</td>
                  <td data-label="Último uso">{fmtDate(a.ultimo_uso, { short: true, empty: "Nunca" })}</td>
                  <td>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => desconectar(a)}>
                      <Trash2 size={14} /> {a.tipo === "PESSOAL" ? "Revogar" : "Desconectar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
