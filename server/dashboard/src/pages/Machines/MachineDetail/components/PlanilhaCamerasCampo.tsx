import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Upload } from "lucide-react";
import api from "../../../../api/client";
import { EqForm, NvrCamera, PlanilhaPendente, PlanilhaVms } from "../../../../api/types";
import { aplicarOpcaoNome, lerPlanilhaVms, mensagemDeErro } from "../planilhaVms";
import PlanilhaVmsModal from "./PlanilhaVmsModal";

const dataBr = (iso?: string) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "");

// Campo "Planilha das câmeras" do formulário do Digifort: lê o CSV/XLSX (mesmo formato e prévia da Galeria) e
// guarda o resultado no formulário; as câmeras só são enviadas à Galeria quando o equipamento é salvo.
export default function PlanilhaCamerasCampo({ machineId, nvrId, eqForm, setEqForm, onPreviaAberta, onErro }: {
  machineId: string;
  nvrId: string | null;
  eqForm: EqForm;
  setEqForm: React.Dispatch<React.SetStateAction<EqForm>>;
  onPreviaAberta: (aberta: boolean) => void;
  onErro: (mensagem: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [existentes, setExistentes] = useState<NvrCamera[]>([]);
  const [previa, setPrevia] = useState<PlanilhaPendente | null>(null);
  const [mostrarSenhas, setMostrarSenhas] = useState(false);
  const [lendo, setLendo] = useState(false);

  // Equipamento já cadastrado: o que a Galeria dele já tem (planilha guardada e câmeras)
  useEffect(() => {
    if (!nvrId) return;
    let cancelado = false;
    (async () => {
      const [cams, plan] = await Promise.allSettled([
        api.get<NvrCamera[]>(`/machines/${machineId}/equipamentos/${nvrId}/cameras`),
        api.get<PlanilhaVms>(`/machines/${machineId}/equipamentos/${nvrId}/planilha`),
      ]);
      if (cancelado) return;
      const lista = cams.status === "fulfilled" ? cams.value.data : [];
      const guardada = plan.status === "fulfilled" ? plan.value.data : null;
      setExistentes(lista);
      setEqForm(f => ({
        ...f,
        planilhaSalva: guardada || lista.length > 0
          ? { nome_arquivo: guardada?.nome_arquivo, total_linhas: guardada?.total_linhas, importado_em: guardada?.importado_em, total_cameras: lista.length }
          : null,
      }));
    })();
    return () => { cancelado = true; };
  }, [machineId, nvrId, setEqForm]);

  useEffect(() => { onPreviaAberta(previa !== null); }, [previa, onPreviaAberta]);

  const escolherArquivo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const arquivo = e.target.files?.[0];
    e.target.value = "";
    if (!arquivo) return;
    setLendo(true);
    try {
      const lida = await lerPlanilhaVms(arquivo, existentes);
      if (!lida) { onErro("Nenhuma câmera encontrada no arquivo."); return; }
      setMostrarSenhas(false);
      setPrevia(lida);
    } catch (err) {
      onErro(mensagemDeErro(err, "Erro ao ler arquivo."));
    } finally {
      setLendo(false);
    }
  };

  const nova = eqForm.planilhaNova;
  const salva = eqForm.planilhaSalva;
  const textoEstado = nova
    ? `${nova.nomeArquivo} · ${nova.cams.length} câmera(s) · será importada ao salvar`
    : salva
      ? `${salva.nome_arquivo ? salva.nome_arquivo + " · " : ""}${salva.total_cameras} câmera(s) na Galeria${salva.importado_em ? ` · importada em ${dataBr(salva.importado_em)}` : ""}`
      : "Nenhuma planilha carregada";

  return (
    <div className="form-group">
      <label className="form-label">Planilha das câmeras *</label>
      <input ref={inputRef} type="file" accept=".csv,.xls,.xlsx" style={{ display: "none" }} onChange={escolherArquivo} />
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="btn btn-secondary" disabled={lendo} onClick={() => inputRef.current?.click()}>
          <Upload size={14} /> {lendo ? "Lendo..." : (nova || salva ? "Trocar planilha" : "Carregar planilha")}
        </button>
        {nova && (
          <button type="button" className="btn btn-secondary" onClick={() => { setMostrarSenhas(false); setPrevia(nova); }}>
            Ver prévia
          </button>
        )}
        <span style={{ fontSize: 12, color: nova || salva ? "var(--text-muted)" : "var(--warn)" }}>{textoEstado}</span>
      </div>
      <span style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4, display: "block" }}>
        CSV ou XLSX exportado do Digifort, no mesmo formato da Galeria. Os nomes das câmeras da planilha são associados às
        pastas de gravação: cada câmera usa a subpasta de mesmo nome.
      </span>

      {previa && createPortal(
        <PlanilhaVmsModal
          titulo={`Prévia da planilha: ${previa.nomeArquivo}`}
          linhas={previa.linhas}
          linhaCabecalho={previa.linhaCabecalho}
          colunasSenha={previa.colunasSenha}
          mostrarSenhas={mostrarSenhas}
          onMostrarSenhas={setMostrarSenhas}
          info={`${previa.cams.length} câmera(s) identificada(s)`}
          camerasLidas={previa.cams}
          confirmarLabel="Usar esta planilha"
          onConfirmar={() => { setEqForm(f => ({ ...f, planilhaNova: previa })); setPrevia(null); }}
          onClose={() => setPrevia(null)}
          temOpcaoNomeDescricao={previa.temOpcaoNomeDescricao}
          opcaoNome={previa.opcaoNome}
          onMudarOpcaoNome={opcao => setPrevia(p => (p ? aplicarOpcaoNome(p, opcao, existentes) : p))}
          exemploNome={previa.exemploNome}
          exemploDescricao={previa.exemploDescricao}
        />,
        document.body,
      )}
    </div>
  );
}
