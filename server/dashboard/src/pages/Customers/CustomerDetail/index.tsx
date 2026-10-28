import { useCallback, useEffect, useRef, useState, FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  attachMachine, cancelCustomerQueue, deleteCustomer, detachMachine, downloadCustomerZip,
  fetchCustomer, fetchCustomerRuns, reorderCustomerQueue, triggerCustomerBackup, updateCustomer,
} from "../../../api/client";
import { fetchContas, moverClienteDeConta } from "../../../api/contas";
import { Conta, Customer, CustomerRun, Machine } from "../../../api/types";
import Modal from "../../../components/Modal";
import { useToast } from "../../../components/Toast";
import { fmtSchedule } from "../../../utils/date";
import { apiErrorMessage } from "../../../utils/errors";
import CustomerFormModal, { CustomerForm, parseEmailList } from "../components/CustomerFormModal";
import CustomerHeader, { CustomerAction } from "./components/CustomerHeader";
import QueueSection, { moveItem } from "./components/QueueSection";
import AddMachineModal from "./components/AddMachineModal";
import CustomerSummary from "./components/CustomerSummary";
import CustomerRuns from "./components/CustomerRuns";
import { useAuth, useRotulos } from "../../../contexts/AuthContext";

const POLL_MS = 5000;

// Detalhe do Cliente: resumo, máquinas e fila de backup (arrastar e soltar) e rodadas de backup
export default function CustomerDetail() {
  const { singular, plural, singularMin } = useRotulos();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const { contaSelecionadaId } = useAuth();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [runs, setRuns] = useState<CustomerRun[] | null>(null);
  const [busy, setBusy] = useState<CustomerAction | null>(null);
  const [queueSaving, setQueueSaving] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [attachingId, setAttachingId] = useState<string | null>(null);

  // Mover cliente de conta (super admin)
  const [showMover, setShowMover] = useState(false);
  const [contasParaMover, setContasParaMover] = useState<Conta[]>([]);
  const [contaDestinoId, setContaDestinoId] = useState("");
  const [movendo, setMovendo] = useState(false);
  const [loadingContas, setLoadingContas] = useState(false);

  // Id exibido (respostas de outro id ou após desmontar são descartadas),
  // sequência para descartar respostas de polling mais antigas que uma alteração local,
  // e trava do polling enquanto uma reordenação otimista está em andamento.
  const activeIdRef = useRef<string | undefined>(undefined);
  const seqRef = useRef(0);
  const reorderPendingRef = useRef(false);
  // Sequência própria das rodadas: descarta respostas que chegarem fora de ordem
  const runsSeqRef = useRef(0);

  const applyCustomer = useCallback((c: Customer) => {
    seqRef.current++;
    if (activeIdRef.current === c.id) setCustomer(c);
  }, []);

  // Rodadas recarregadas no mesmo ciclo do polling do cliente (sem intervalo próprio)
  const loadRuns = useCallback(async () => {
    if (!id) return;
    const reqId = id;
    const seq = ++runsSeqRef.current;
    try {
      const r = await fetchCustomerRuns(reqId);
      if (activeIdRef.current === reqId && seq === runsSeqRef.current) setRuns(r);
    } catch {
      // falha em silêncio; na 1ª carga sai do estado "carregando"
      if (activeIdRef.current === reqId && seq === runsSeqRef.current) setRuns(prev => prev ?? []);
    }
  }, [id]);

  const refresh = useCallback(async (initial = false) => {
    if (!id) return;
    const reqId = id;
    const seq = ++seqRef.current;
    loadRuns();
    try {
      const c = await fetchCustomer(reqId);
      if (activeIdRef.current !== reqId || seq !== seqRef.current || reorderPendingRef.current) return;
      setCustomer(c);
      setNotFound(false);
    } catch (e) {
      if (activeIdRef.current !== reqId || !initial) return; // polling falha em silêncio
      const status = (e as { response?: { status?: number } })?.response?.status;
      if (status === 404) setNotFound(true);
      else toast(`Erro ao carregar o ${singularMin}.`, "error");
    } finally {
      if (initial && activeIdRef.current === reqId) setLoading(false);
    }
  }, [id, toast, loadRuns]);

  useEffect(() => {
    activeIdRef.current = id;
    setLoading(true); setCustomer(null); setNotFound(false); setRuns(null);
    refresh(true);
    const t = setInterval(() => refresh(), POLL_MS);
    return () => { clearInterval(t); activeIdRef.current = undefined; };
  }, [id, refresh]);

  // Carrega contas disponíveis quando modal de mover for aberto
  useEffect(() => {
    if (!showMover || !customer) return;
    let active = true;
    setLoadingContas(true);
    const clienteContaId =
      (customer as unknown as { conta_id?: string | null })?.conta_id ?? contaSelecionadaId;

    fetchContas()
      .then((lista) => {
        if (!active) return;
        const disponiveis = clienteContaId
          ? lista.filter((ct) => ct.id !== clienteContaId)
          : lista;
        setContasParaMover(disponiveis);
        if (disponiveis.length > 0) {
          setContaDestinoId(disponiveis[0].id);
        } else {
          setContaDestinoId("");
        }
      })
      .catch((err) => {
        if (!active) return;
        toast(apiErrorMessage(err, "Erro ao carregar lista de contas."), "error");
      })
      .finally(() => {
        if (active) setLoadingContas(false);
      });

    return () => {
      active = false;
    };
  }, [showMover, customer, contaSelecionadaId, toast]);

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (notFound || !customer) {
    return (
      <div className="empty-state">
        <div>{notFound ? `${singular} não encontrado.` : `Não foi possível carregar o ${singularMin}.`}</div>
        <button className="btn btn-secondary mt-2" onClick={() => navigate("/clientes")}>Voltar para {plural}</button>
      </div>
    );
  }

  const c = customer;
  const schedule = fmtSchedule(c.backup_hour, c.backup_minute);

  const handleAction = async (action: CustomerAction) => {
    if (action === "edit") { setShowEdit(true); return; }
    if (action === "delete") {
      const msg = c.machines_total > 0
        ? `Excluir o ${singularMin} "${c.name}"?\nAs ${c.machines_total} máquina(s) dele continuam cadastradas, mas ficarão sem ${singularMin}.`
        : `Excluir o ${singularMin} "${c.name}"?`;
      if (!confirm(msg)) return;
      try {
        await deleteCustomer(c.id);
        toast(`${singular} excluído.`, "success");
        navigate("/clientes");
      } catch (e) { toast(apiErrorMessage(e, `Erro ao excluir ${singularMin}.`), "error"); }
      return;
    }
    if (action === "backup" && !confirm(`Iniciar o backup em fila das ${c.machines_total} máquina(s) de "${c.name}"?\nElas farão o backup uma por vez, na ordem da fila.`)) return;
    setBusy(action);
    try {
      if (action === "backup") {
        await triggerCustomerBackup(c.id);
        toast("Fila de backup iniciada.", "success");
      } else if (action === "stop") {
        await cancelCustomerQueue(c.id);
        toast("Fila parada.", "success");
      } else if (action === "zip") {
        await downloadCustomerZip(c.id, c.name);
        toast("Download iniciado.", "success");
      }
      await refresh();
    } catch (e) {
      const fallback = action === "zip" ? "Erro ao baixar o ZIP." : action === "stop" ? "Erro ao parar a fila." : "Erro ao iniciar a fila.";
      toast(apiErrorMessage(e, fallback), "error");
    } finally { setBusy(null); }
  };

  const handleEditSave = async (form: CustomerForm) => {
    if (!form.name.trim()) { toast("Nome obrigatório.", "error"); return; }
    const scheduleChanged = form.backup_hour !== c.backup_hour || form.backup_minute !== c.backup_minute;
    setEditSaving(true);
    try {
      const updatePayload: Parameters<typeof updateCustomer>[1] = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        backup_hour: form.backup_hour,
        backup_minute: form.backup_minute,
        email_to: parseEmailList(form.email_to),
      };
      if (form.password_mode === "default") {
        updatePayload.zip_password = "";
      } else if (form.zip_password && form.zip_password.trim()) {
        updatePayload.zip_password = form.zip_password.trim();
      }
      const updated = await updateCustomer(c.id, updatePayload);
      applyCustomer(updated);
      setShowEdit(false);
      toast(scheduleChanged
        ? `${singular} atualizado. O novo horário foi aplicado a todas as máquinas (agentes reiniciados).`
        : `${singular} atualizado.`, "success");
    } catch (e) { toast(apiErrorMessage(e, `Erro ao salvar o ${singularMin}.`), "error"); }
    finally { setEditSaving(false); }
  };

  // Atualização otimista: mostra a nova ordem na hora; em erro volta à anterior
  const handleReorder = async (from: number, insertAt: number) => {
    const previous = c;
    const machines = moveItem(previous.machines, from, insertAt);
    reorderPendingRef.current = true;
    seqRef.current++;
    setCustomer({ ...previous, machines });
    setQueueSaving(true);
    try {
      const updated = await reorderCustomerQueue(previous.id, machines.map(m => m.id));
      applyCustomer(updated);
      toast("Ordem da fila salva.", "success");
    } catch (e) {
      setCustomer(previous);
      toast(apiErrorMessage(e, "Não foi possível salvar a nova ordem. A ordem anterior foi restaurada."), "error");
    } finally {
      reorderPendingRef.current = false;
      setQueueSaving(false);
    }
  };

  const handleDetach = async (m: Machine) => {
    if (!confirm(`Remover a máquina "${m.name}" do ${singularMin} "${c.name}"?\nEla continua cadastrada em Máquinas, fica sem ${singularMin} e mantém o horário atual.`)) return;
    setQueueSaving(true);
    try {
      applyCustomer(await detachMachine(c.id, m.id));
      toast(`Máquina "${m.name}" removida do ${singularMin}.`, "success");
    } catch (e) { toast(apiErrorMessage(e, `Erro ao remover a máquina do ${singularMin}.`), "error"); }
    finally { setQueueSaving(false); }
  };

  const handleAttach = async (m: Machine) => {
    setAttachingId(m.id);
    try {
      applyCustomer(await attachMachine(c.id, m.id));
      setShowAdd(false);
      toast(`Máquina "${m.name}" adicionada ao ${singularMin}.`, "success");
    } catch (e) { toast(apiErrorMessage(e, "Erro ao adicionar a máquina."), "error"); }
    finally { setAttachingId(null); }
  };

  const handleMoverConta = async (e: FormEvent) => {
    e.preventDefault();
    if (!contaDestinoId) {
      toast("Selecione a conta de destino.", "error");
      return;
    }
    const contaEscolhida = contasParaMover.find((ct) => ct.id === contaDestinoId);
    const nomeConta = contaEscolhida ? contaEscolhida.nome : "nova conta";
    setMovendo(true);
    try {
      const r = await moverClienteDeConta(c.id, contaDestinoId);
      toast(
        `Movido para ${nomeConta}. ${r.maquinas_movidas} máquina(s) junto.`,
        "success"
      );
      setShowMover(false);
      navigate("/clientes");
    } catch (err) {
      toast(apiErrorMessage(err, "Erro ao mover cliente de conta."), "error");
    } finally {
      setMovendo(false);
    }
  };

  return (
    <>
      <CustomerHeader
        customer={c}
        busy={busy}
        onBack={() => navigate("/clientes")}
        onAction={handleAction}
        onDashboard={() => navigate(`/clientes/${c.id}/dashboard`)}
        onMoverConta={() => setShowMover(true)}
      />

      <CustomerSummary runs={runs} machines={c.machines} />

      <QueueSection
        customer={c}
        runs={runs}
        saving={queueSaving}
        onReorder={handleReorder}
        onDetach={handleDetach}
        onAdd={() => setShowAdd(true)}
      />

      <CustomerRuns customerId={c.id} customerName={c.name} runs={runs} onChanged={loadRuns} />

      {showEdit && (
        <CustomerFormModal
          title={`Editar ${singular}`}
          isEdit
          initial={{
            name: c.name, description: c.description || "", backup_hour: c.backup_hour, backup_minute: c.backup_minute,
            email_to: (c.email_to || []).join(", "),
            password_mode: c.has_zip_password ? "custom" : "default",
            zip_password: "",
            has_zip_password: c.has_zip_password,
          }}
          saving={editSaving}
          onSave={handleEditSave}
          onClose={() => setShowEdit(false)}
        />
      )}

      {showAdd && (
        <AddMachineModal
          customerName={c.name}
          scheduleLabel={schedule}
          attachingId={attachingId}
          onAttach={handleAttach}
          onClose={() => setShowAdd(false)}
        />
      )}

      {showMover && (
        <Modal
          title="Mover para outra conta"
          onClose={() => {
            if (!movendo) setShowMover(false);
          }}
          width={480}
        >
          <form onSubmit={handleMoverConta}>
            <p
              style={{
                margin: "0 0 16px 0",
                color: "var(--text-secondary)",
                fontSize: 14,
                lineHeight: 1.5,
              }}
            >
              As máquinas deste {singularMin} vão junto. Ele passa a aparecer só na conta escolhida.
            </p>

            <div className="form-group">
              <label className="form-label">Conta de destino *</label>
              {loadingContas ? (
                <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 0" }}>
                  <span className="spinner spinner-sm" />
                  <span className="text-muted" style={{ fontSize: 13 }}>
                    Carregando contas...
                  </span>
                </div>
              ) : contasParaMover.length === 0 ? (
                <div className="text-muted" style={{ fontSize: 13 }}>
                  Nenhuma outra conta disponível para destino.
                </div>
              ) : (
                <select
                  className="form-input"
                  value={contaDestinoId}
                  onChange={(e) => setContaDestinoId(e.target.value)}
                  disabled={movendo}
                  required
                >
                  {contasParaMover.map((ct) => (
                    <option key={ct.id} value={ct.id}>
                      {ct.nome}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
                marginTop: 20,
              }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowMover(false)}
                disabled={movendo}
              >
                Cancelar
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={movendo || loadingContas || contasParaMover.length === 0 || !contaDestinoId}
              >
                {movendo ? (
                  <>
                    <span className="spinner spinner-sm" /> Movendo...
                  </>
                ) : (
                  "Mover"
                )}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
