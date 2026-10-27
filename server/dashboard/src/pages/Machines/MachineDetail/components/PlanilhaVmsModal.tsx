import { useState } from "react";
import Modal from "../../../../components/Modal";
import { DigifortNameOption } from "../hooks/useCameraImport";

export interface CameraLidaPrevia {
  nome: string;
  ip: string;
  modelo: string;
  senha: string;
  situacao: "nova" | "atualiza";
}

export interface PlanilhaVmsModalProps {
  titulo: string;
  linhas: string[][];
  linhaCabecalho: number;
  colunasSenha: number[];
  mostrarSenhas: boolean;
  onMostrarSenhas: (v: boolean) => void;
  info?: string;
  camerasLidas?: CameraLidaPrevia[];
  temOpcaoNomeDescricao?: boolean;
  opcaoNome?: DigifortNameOption;
  onMudarOpcaoNome?: (opcao: DigifortNameOption) => void;
  exemploNome?: string;
  exemploDescricao?: string;
  onConfirmar?: () => void;
  confirmarLabel?: string;
  confirmando?: boolean;
  onRemover?: () => void;
  carregando?: boolean;
  onClose: () => void;
}

export default function PlanilhaVmsModal({
  titulo,
  linhas,
  linhaCabecalho,
  colunasSenha,
  mostrarSenhas,
  onMostrarSenhas,
  info,
  camerasLidas,
  temOpcaoNomeDescricao,
  opcaoNome,
  onMudarOpcaoNome,
  exemploNome,
  exemploDescricao,
  onConfirmar,
  confirmarLabel,
  confirmando,
  onRemover,
  carregando,
  onClose,
}: PlanilhaVmsModalProps) {
  const [abaAtiva, setAbaAtiva] = useState<"cameras" | "planilha">(
    camerasLidas && camerasLidas.length > 0 ? "cameras" : "planilha"
  );

  const colCount = linhas.reduce((max, r) => Math.max(max, r.length), 0);

  return (
    <Modal title={titulo} onClose={onClose} width="1100px">
      <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {/* Faixa de topo */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
            borderBottom: "1px solid var(--border)",
            paddingBottom: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            {camerasLidas && camerasLidas.length > 0 && (
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  type="button"
                  className={`btn ${abaAtiva === "cameras" ? "btn-primary" : "btn-secondary"}`}
                  style={{ padding: "5px 12px", fontSize: 12 }}
                  onClick={() => setAbaAtiva("cameras")}
                >
                  Câmeras lidas ({camerasLidas.length})
                </button>
                <button
                  type="button"
                  className={`btn ${abaAtiva === "planilha" ? "btn-primary" : "btn-secondary"}`}
                  style={{ padding: "5px 12px", fontSize: 12 }}
                  onClick={() => setAbaAtiva("planilha")}
                >
                  Planilha ({linhas.length} linhas)
                </button>
              </div>
            )}
            {temOpcaoNomeDescricao && onMudarOpcaoNome && (
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  background: "var(--surface-2)",
                  padding: "4px 10px",
                  borderRadius: 6,
                  border: "1px solid var(--border)",
                  fontSize: 12,
                }}
              >
                <span style={{ fontWeight: 600, color: "var(--text)" }}>Registrar como nome:</span>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    cursor: "pointer",
                    userSelect: "none",
                    fontWeight: opcaoNome === "descricao" ? 600 : 400,
                    color: opcaoNome === "descricao" ? "var(--primary)" : "var(--text)",
                  }}
                >
                  <input
                    type="radio"
                    name="opcaoNomePreviaVms"
                    value="descricao"
                    checked={opcaoNome === "descricao"}
                    onChange={() => onMudarOpcaoNome("descricao")}
                  />
                  <span>Descrição {exemploDescricao ? `(ex.: ${exemploDescricao})` : ""}</span>
                </label>
                <label
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    cursor: "pointer",
                    userSelect: "none",
                    fontWeight: opcaoNome === "nome" ? 600 : 400,
                    color: opcaoNome === "nome" ? "var(--primary)" : "var(--text)",
                  }}
                >
                  <input
                    type="radio"
                    name="opcaoNomePreviaVms"
                    value="nome"
                    checked={opcaoNome === "nome"}
                    onChange={() => onMudarOpcaoNome("nome")}
                  />
                  <span>Nome {exemploNome ? `(ex.: ${exemploNome})` : ""}</span>
                </label>
              </div>
            )}
            {info && (
              <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
                {info}
              </span>
            )}
          </div>

          <label
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              fontSize: 13,
              cursor: "pointer",
              userSelect: "none",
              color: "var(--text-secondary)",
            }}
          >
            <input
              type="checkbox"
              checked={mostrarSenhas}
              disabled={carregando}
              onChange={e => onMostrarSenhas(e.target.checked)}
              style={{ cursor: "pointer" }}
            />
            Mostrar senhas
          </label>
        </div>

        {/* Conteúdo */}
        {carregando ? (
          <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            Carregando planilha...
          </div>
        ) : abaAtiva === "cameras" && camerasLidas && camerasLidas.length > 0 ? (
          <div
            style={{
              maxHeight: "60vh",
              overflow: "auto",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--surface-2)", position: "sticky", top: 0, zIndex: 1 }}>
                  <th style={{ padding: "8px 12px", textAlign: "center", borderBottom: "1px solid var(--border)", width: 44, color: "var(--text-muted)", fontSize: 11 }}>#</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", borderBottom: "1px solid var(--border)" }}>Nome</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", borderBottom: "1px solid var(--border)" }}>IP</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", borderBottom: "1px solid var(--border)" }}>Modelo</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", borderBottom: "1px solid var(--border)" }}>Senha</th>
                  <th style={{ padding: "8px 12px", textAlign: "left", borderBottom: "1px solid var(--border)", width: 90 }}>Situação</th>
                </tr>
              </thead>
              <tbody>
                {camerasLidas.map((cam, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "8px 12px", textAlign: "center", color: "var(--text-muted)", fontSize: 11 }}>{idx + 1}</td>
                    <td style={{ padding: "8px 12px", fontWeight: 500 }} title={cam.nome}>{cam.nome}</td>
                    <td style={{ padding: "8px 12px", fontFamily: "monospace" }}>{cam.ip}</td>
                    <td style={{ padding: "8px 12px" }}>{cam.modelo}</td>
                    <td style={{ padding: "8px 12px", fontFamily: "monospace" }}>
                      {mostrarSenhas ? (cam.senha || "—") : (cam.senha ? "••••••" : "—")}
                    </td>
                    <td style={{ padding: "8px 12px" }}>
                      <span className={`badge ${cam.situacao === "nova" ? "ok" : "warn"}`}>
                        {cam.situacao === "nova" ? "Nova" : "Atualiza"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : linhas.length === 0 ? (
          <div style={{ padding: 48, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
            Planilha vazia.
          </div>
        ) : (
          <div
            style={{
              maxHeight: "60vh",
              overflow: "auto",
              border: "1px solid var(--border)",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <table style={{ width: "max-content", minWidth: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <tbody>
                {linhas.map((row, rIdx) => {
                  const isHeader = rIdx === linhaCabecalho;
                  const isBeforeHeader = rIdx < linhaCabecalho;

                  return (
                    <tr
                      key={rIdx}
                      style={{
                        ...(isHeader
                          ? { fontWeight: 700, background: "var(--surface-2)" }
                          : isBeforeHeader
                          ? { opacity: 0.6 }
                          : {}),
                        borderBottom: "1px solid var(--border)",
                      }}
                    >
                      <td
                        style={{
                          padding: "6px 10px",
                          textAlign: "center",
                          color: "var(--text-muted)",
                          fontSize: 11,
                          userSelect: "none",
                          width: 44,
                          minWidth: 44,
                          borderRight: "1px solid var(--border)",
                          borderBottom: "1px solid var(--border)",
                          ...(isHeader
                            ? {
                                position: "sticky",
                                top: 0,
                                zIndex: 3,
                                background: "var(--surface-2)",
                              }
                            : {}),
                        }}
                      >
                        {rIdx + 1}
                      </td>

                      {Array.from({ length: colCount }).map((_, cIdx) => {
                        const rawVal = row[cIdx] ?? "";
                        const isSenhaCol = colunasSenha.includes(cIdx);
                        const isBelowHeader = rIdx > linhaCabecalho;

                        let displayVal = rawVal;
                        let isMasked = false;
                        if (isBelowHeader && isSenhaCol) {
                          if (!mostrarSenhas && rawVal !== "") {
                            displayVal = "••••••";
                            isMasked = true;
                          }
                        }

                        return (
                          <td
                            key={cIdx}
                            title={rawVal}
                            style={{
                              padding: "6px 10px",
                              maxWidth: 240,
                              whiteSpace: "nowrap",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              borderRight: "1px solid var(--border)",
                              borderBottom: "1px solid var(--border)",
                              ...(isHeader
                                ? {
                                    position: "sticky",
                                    top: 0,
                                    zIndex: 2,
                                    background: "var(--surface-2)",
                                  }
                                : {}),
                              ...(isBelowHeader && isSenhaCol && (mostrarSenhas || isMasked)
                                ? { fontFamily: "monospace" }
                                : {}),
                            }}
                          >
                            {displayVal}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Rodapé */}
        <div
          style={{
            display: "flex",
            justifyContent: onConfirmar ? "flex-end" : "space-between",
            alignItems: "center",
            gap: 10,
            marginTop: 8,
            borderTop: "1px solid var(--border)",
            paddingTop: 14,
          }}
        >
          {onConfirmar ? (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={confirmando}
              >
                Cancelar
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={onConfirmar}
                disabled={confirmando || carregando}
              >
                {confirmando ? "Importando..." : (confirmarLabel || "Importar")}
              </button>
            </>
          ) : (
            <>
              {onRemover ? (
                <button
                  type="button"
                  className="btn btn-danger"
                  onClick={onRemover}
                  disabled={carregando}
                >
                  Remover planilha
                </button>
              ) : (
                <div />
              )}
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
                disabled={carregando}
              >
                Fechar
              </button>
            </>
          )}
        </div>
      </div>
    </Modal>
  );
}
