import Modal from "../../../../components/Modal";
import { CameraRow, DigifortNameOption } from "../hooks/useCameraImport";

export interface ImportCamerasModalProps {
  fileName: string;
  cameras: CameraRow[];
  totalLinhas: number;
  temOpcaoNomeDescricao: boolean;
  opcaoNome: DigifortNameOption;
  onMudarOpcaoNome: (opcao: DigifortNameOption) => void;
  exemploNome?: string;
  exemploDescricao?: string;
  confirmando?: boolean;
  onConfirmar: () => void;
  onClose: () => void;
}

export default function ImportCamerasModal({
  fileName,
  cameras,
  temOpcaoNomeDescricao,
  opcaoNome,
  onMudarOpcaoNome,
  exemploNome,
  exemploDescricao,
  confirmando,
  onConfirmar,
  onClose,
}: ImportCamerasModalProps) {
  return (
    <Modal title={`Importar Câmeras — ${fileName}`} onClose={onClose} width="780px">
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {temOpcaoNomeDescricao && (
          <div
            style={{
              padding: "14px 16px",
              borderRadius: "8px",
              background: "rgba(59, 130, 246, 0.08)",
              border: "1px solid rgba(59, 130, 246, 0.25)",
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
              Planilha Digifort: escolha qual campo registrar como nome da câmera
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.4 }}>
              Esta planilha possui as colunas <strong>Nome</strong> e <strong>Descrição</strong>. Selecione qual delas deseja utilizar para identificar cada câmera no sistema:
            </div>
            <div style={{ display: "flex", gap: 24, marginTop: 4, flexWrap: "wrap" }}>
              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 13,
                  cursor: "pointer",
                  fontWeight: opcaoNome === "descricao" ? 600 : 400,
                  color: opcaoNome === "descricao" ? "var(--primary)" : "var(--text)",
                }}
              >
                <input
                  type="radio"
                  name="opcaoNomeDigifortRtsp"
                  value="descricao"
                  checked={opcaoNome === "descricao"}
                  onChange={() => onMudarOpcaoNome("descricao")}
                />
                <span>
                  Descrição {exemploDescricao ? `(ex.: ${exemploDescricao})` : ""}
                </span>
              </label>

              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 13,
                  cursor: "pointer",
                  fontWeight: opcaoNome === "nome" ? 600 : 400,
                  color: opcaoNome === "nome" ? "var(--primary)" : "var(--text)",
                }}
              >
                <input
                  type="radio"
                  name="opcaoNomeDigifortRtsp"
                  value="nome"
                  checked={opcaoNome === "nome"}
                  onChange={() => onMudarOpcaoNome("nome")}
                />
                <span>
                  Nome {exemploNome ? `(ex.: ${exemploNome})` : ""}
                </span>
              </label>
            </div>
          </div>
        )}

        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              marginBottom: 8,
              color: "var(--text-muted)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>
              Prévia das Câmeras ({cameras.length} encontrada{cameras.length === 1 ? "" : "s"})
            </span>
            <span style={{ fontSize: 11 }}>
              Exibindo as primeiras {Math.min(6, cameras.length)}
            </span>
          </div>

          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: "6px",
              overflow: "hidden",
              maxHeight: "260px",
              overflowY: "auto",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr
                  style={{
                    background: "var(--surface-2)",
                    borderBottom: "1px solid var(--border)",
                    textAlign: "left",
                    position: "sticky",
                    top: 0,
                    zIndex: 1,
                  }}
                >
                  <th style={{ padding: "8px 12px", width: 40, textAlign: "center", color: "var(--text-muted)" }}>#</th>
                  <th style={{ padding: "8px 12px" }}>Nome a Registrar</th>
                  <th style={{ padding: "8px 12px" }}>Endereço IP</th>
                  <th style={{ padding: "8px 12px" }}>Modelo</th>
                </tr>
              </thead>
              <tbody>
                {cameras.slice(0, 6).map((cam, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "8px 12px", textAlign: "center", color: "var(--text-muted)" }}>{idx + 1}</td>
                    <td style={{ padding: "8px 12px", fontWeight: 500 }} title={cam.name}>{cam.name}</td>
                    <td style={{ padding: "8px 12px", fontFamily: "monospace" }}>{cam.ip}</td>
                    <td style={{ padding: "8px 12px" }}>{cam.modelo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {cameras.length > 6 && (
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, textAlign: "right" }}>
              + {cameras.length - 6} outra{cameras.length - 6 === 1 ? "" : "s"} câmera{cameras.length - 6 === 1 ? "" : "s"} cadastrada{cameras.length - 6 === 1 ? "" : "s"} com este padrão.
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10, marginTop: 8 }}>
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={confirmando}>
            Cancelar
          </button>
          <button type="button" className="btn btn-primary" onClick={onConfirmar} disabled={confirmando || cameras.length === 0}>
            {confirmando ? "Importando..." : `Importar ${cameras.length} Câmera${cameras.length === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    </Modal>
  );
}
