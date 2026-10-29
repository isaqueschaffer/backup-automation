import api from "../../../api/client";
import { CameraLidaPlanilha, NvrCamera, PlanilhaPendente } from "../../../api/types";
import {
  colunasDeSenha,
  DigifortNameOption,
  extrairExemplosNomeEDescricao,
  linhaDoCabecalho,
  linhasParaTexto,
  planilhaTemNomeEDescricao,
  readRowsFromFile,
  rowsToCameras,
} from "./hooks/useCameraImport";

// Mesma lógica da Galeria (NVRCamerasGalleryModal), para o formulário do Digifort: lê o CSV/XLSX e marca
// cada câmera como nova ou já existente (mesmo nome ou IP) na Galeria do equipamento.
function marcarSituacao(rows: unknown[][], opcao: DigifortNameOption, existentes: NvrCamera[]): CameraLidaPlanilha[] {
  return rowsToCameras(rows, opcao).map(c => {
    const nome = (c.name || "").trim().toLowerCase();
    const ip = (c.ip || "").trim();
    const jaExiste = existentes.some(e =>
      (nome !== "" && (e.nome || "").trim().toLowerCase() === nome) || (ip !== "" && (e.ip || "").trim() === ip));
    return { nome: c.name, ip: c.ip, modelo: c.modelo, senha: c.password, situacao: jaExiste ? "atualiza" : "nova" };
  });
}

/** Lê o arquivo; devolve null se nenhuma câmera foi encontrada. */
export async function lerPlanilhaVms(file: File, existentes: NvrCamera[]): Promise<PlanilhaPendente | null> {
  const rows = await readRowsFromFile(file);
  const cams = marcarSituacao(rows, "descricao", existentes);
  if (cams.length === 0) return null;
  const linhas = linhasParaTexto(rows);
  const linhaCabecalho = linhaDoCabecalho(linhas);
  const { nome, descricao } = extrairExemplosNomeEDescricao(rows);
  return {
    nomeArquivo: file.name,
    linhas,
    linhasBrutas: rows,
    linhaCabecalho,
    colunasSenha: colunasDeSenha(linhas, linhaCabecalho),
    temOpcaoNomeDescricao: planilhaTemNomeEDescricao(rows),
    opcaoNome: "descricao",
    exemploNome: nome,
    exemploDescricao: descricao,
    cams,
  };
}

/** Troca o campo usado como nome da câmera (Nome ou Descrição) e recalcula a lista. */
export function aplicarOpcaoNome(p: PlanilhaPendente, opcao: DigifortNameOption, existentes: NvrCamera[]): PlanilhaPendente {
  return { ...p, opcaoNome: opcao, cams: marcarSituacao(p.linhasBrutas, opcao, existentes) };
}

/** Envia a planilha à Galeria do equipamento: importa as câmeras e guarda a planilha (mesmos endpoints da Galeria). */
export async function enviarPlanilhaVms(machineId: string, nvrId: string, p: PlanilhaPendente): Promise<void> {
  await api.post(`/machines/${machineId}/equipamentos/${nvrId}/cameras/import`, {
    cameras: p.cams.map(c => ({ nome: c.nome, ip: c.ip, username: "admin", password: c.senha, modelo: c.modelo })),
  });
  await api.put(`/machines/${machineId}/equipamentos/${nvrId}/planilha`, {
    nome_arquivo: p.nomeArquivo,
    linha_cabecalho: p.linhaCabecalho,
    linhas: p.linhas,
  });
}

export function mensagemDeErro(e: unknown, padrao: string): string {
  // 422 do FastAPI vem como lista [{msg: "Value error, ..."}]
  const detail = (e as { response?: { data?: { detail?: string | { msg?: string }[] } } })?.response?.data?.detail;
  const msg = Array.isArray(detail) ? detail[0]?.msg?.replace(/^Value error, /, "") : detail;
  return msg || (e instanceof Error && !("response" in e) ? e.message : padrao);
}
