import type { ReactNode } from "react";
import { fmtOfflineHa } from "../../../utils/date";
import { AtualidadeStatus, NivelStatus } from "../types";

// Peças comuns dos widgets de status periódico (antenas, OLT, alarmes): cor por nível, cartão do
// equipamento com "atualizado há X" e mensagens de vazio. O nível vem pronto do servidor.

export const COR_NIVEL: Record<NivelStatus, string> = {
  critico: "var(--err)",
  atencao: "var(--warn)",
  ok: "var(--ok)",
  neutro: "var(--text-muted)",
};

export function Ponto({ nivel }: { nivel: NivelStatus }) {
  return (
    <span
      aria-hidden
      style={{
        width: 8,
        height: 8,
        borderRadius: "50%",
        backgroundColor: COR_NIVEL[nivel],
        flexShrink: 0,
        display: "inline-block",
      }}
    />
  );
}

export function Vazio({ texto }: { texto: string }) {
  return (
    <div
      style={{
        height: "100%",
        minHeight: 40,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        color: "var(--text-muted)",
        fontSize: 12,
        textAlign: "center",
      }}
    >
      {texto}
    </div>
  );
}

export function textoAtualidade(eq: AtualidadeStatus): { texto: string; cor: string } {
  if (eq.sem_status) return { texto: "Ainda sem leitura", cor: "var(--warn)" };
  const ha = fmtOfflineHa(eq.segundos_desde_atualizacao);
  if (eq.desatualizado) return { texto: `Sem atualização ${ha}`.trim(), cor: "var(--warn)" };
  return { texto: `Atualizado ${ha}`.trim(), cor: "var(--text-muted)" };
}

export function Linha({
  nivel,
  nome,
  detalhe,
  direita,
}: {
  nivel: NivelStatus;
  nome: string;
  detalhe?: string | null;
  direita?: ReactNode;
}) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, padding: "2px 0" }}>
      <Ponto nivel={nivel} />
      <span style={{ color: "var(--text-primary)", minWidth: 0, flex: 1, overflowWrap: "anywhere" }}>
        {nome}
        {detalhe && <span style={{ color: "var(--text-muted)", fontSize: 11 }}> · {detalhe}</span>}
      </span>
      {direita != null && (
        <span style={{ flexShrink: 0, fontSize: 11, whiteSpace: "nowrap", textAlign: "right" }}>{direita}</span>
      )}
    </div>
  );
}

export function CartaoEquipamento({
  eq,
  resumo,
  aviso,
  children,
}: {
  eq: AtualidadeStatus;
  resumo?: ReactNode;
  aviso?: string | null;
  children?: ReactNode;
}) {
  const atual = textoAtualidade(eq);
  return (
    <div
      style={{
        backgroundColor: "var(--surface-2)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${COR_NIVEL[eq.nivel]}`,
        borderRadius: 6,
        padding: "10px 12px",
        display: "flex",
        flexDirection: "column",
        gap: 6,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>{eq.nome}</span>
          <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 6 }}>· {eq.maquina}</span>
        </div>
        {resumo}
      </div>
      <div style={{ fontSize: 11, color: atual.cor }}>{atual.texto}</div>
      {aviso && <div style={{ fontSize: 11, color: "var(--warn)" }}>{aviso}</div>}
      {children}
    </div>
  );
}

export function ListaEquipamentos({ children }: { children: ReactNode }) {
  return <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>{children}</div>;
}
