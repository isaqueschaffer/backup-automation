import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  attachMachine, cancelCustomerQueue, deleteCustomer, detachMachine, downloadCustomerZip,
  fetchBackups, fetchCustomer, fetchCustomerRuns, reorderCustomerQueue, triggerCustomerBackup, updateCustomer,
} from "../../../api/client";
import { Backup, Customer, CustomerRun, Machine } from "../../../api/types";
import { useToast } from "../../../components/Toast";
import { fmtSchedule } from "../../../utils/date";
import { apiErrorMessage } from "../../../utils/errors";
import CustomerFormModal, { CustomerForm, parseEmailList } from "../components/CustomerFormModal";
import CustomerHeader, { CustomerAction } from "./components/CustomerHeader";
import QueueSection, { moveItem } from "./components/QueueSection";
import AddMachineModal from "./components/AddMachineModal";
import CustomerBackups from "./components/CustomerBackups";
import CustomerRuns from "./components/CustomerRuns";

const POLL_MS = 5000;

// Detalhe do Cliente: dados, fila de backup (ordem por arrastar e soltar), rodadas de backup e backups por máquina
export default function CustomerDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const [customer, setCustomer] = useState<Customer | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [backups, setBackups] = useState<Backup[] | null>(null);
  const [runs, setRuns] = useState<CustomerRun[] | null>(null);
  const [busy, setBusy] = useState<CustomerAction | null>(null);
  const [queueSaving, setQueueSaving] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [editSaving, setEditSaving] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [attachingId, setAttachingId] = useState<string | null>(null);

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
      else toast("Erro ao carregar o cliente.", "error");
    } finally {
      if (initial && activeIdRef.current === reqId) setLoading(false);
    }
  }, [id, toast, loadRuns]);

  useEffect(() => {
    activeIdRef.current = id;
    setLoading(true); setCustomer(null); setNotFound(false); setBackups(null); setRuns(null);
    refresh(true);
    const t = setInterval(() => refresh(), POLL_MS);
    return () => { clearInterval(t); activeIdRef.current = undefined; };
  }, [id, refresh]);

  // Backups recentes: recarrega quando muda o último backup ou o conjunto de máquinas
  const backupKey = customer ? `${customer.last_backup_at}|${customer.machines.map(m => m.id).join(",")}` : "";
  useEffect(() => {
    if (!id || !backupKey) return;
    let cancelled = false;
    fetchBackups({ customer_id: id, size: 10 })
      .then(r => { if (!cancelled) setBackups(r.items); })
      .catch(() => { if (!cancelled) setBackups(prev => prev ?? []); });
    return () => { cancelled = true; };
  }, [id, backupKey]);

  if (loading) return <div className="loading-state"><div className="spinner" /></div>;
  if (notFound || !customer) {
    return (
      <div className="empty-state">
        <div>{notFound ? "Cliente não encontrado." : "Não foi possível carregar o cliente."}</div>
        <button className="btn btn-secondary mt-2" onClick={() => navigate("/clientes")}>Voltar para Clientes</button>
      </div>
    );
  }

  const c = customer;
  const schedule = fmtSchedule(c.backup_hour, c.backup_minute);

  const handleAction = async (action: CustomerAction) => {
    if (action === "edit") { setShowEdit(true); return; }
    if (action === "delete") {
      const msg = c.machines_total > 0
        ? `Excluir o cliente "${c.name}"?\nAs ${c.machines_total} máquina(s) dele continuam cadastradas, mas ficarão sem cliente.`
        : `Excluir o cliente "${c.name}"?`;
      if (!confirm(msg)) return;
      try {
        await deleteCustomer(c.id);
        toast("Cliente excluído.", "success");
        navigate("/clientes");
      } catch (e) { toast(apiErrorMessage(e, "Erro ao excluir cliente."), "error"); }
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
      const updated = await updateCustomer(c.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        backup_hour: form.backup_hour,
        backup_minute: form.backup_minute,
        email_to: parseEmailList(form.email_to),
      });
      applyCustomer(updated);
      setShowEdit(false);
      toast(scheduleChanged
        ? "Cliente atualizado. O novo horário foi aplicado a todas as máquinas (agentes reiniciados)."
        : "Cliente atualizado.", "success");
    } catch (e) { toast(apiErrorMessage(e, "Erro ao salvar o cliente."), "error"); }
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
    if (!confirm(`Remover a máquina "${m.name}" do cliente "${c.name}"?\nEla continua cadastrada em Máquinas, fica sem cliente e mantém o horário atual.`)) return;
    setQueueSaving(true);
    try {
      applyCustomer(await detachMachine(c.id, m.id));
      toast(`Máquina "${m.name}" removida do cliente.`, "success");
    } catch (e) { toast(apiErrorMessage(e, "Erro ao remover a máquina do cliente."), "error"); }
    finally { setQueueSaving(false); }
  };

  const handleAttach = async (m: Machine) => {
    setAttachingId(m.id);
    try {
      applyCustomer(await attachMachine(c.id, m.id));
      setShowAdd(false);
      toast(`Máquina "${m.name}" adicionada ao cliente.`, "success");
    } catch (e) { toast(apiErrorMessage(e, "Erro ao adicionar a máquina."), "error"); }
    finally { setAttachingId(null); }
  };

  return (
    <>
      <CustomerHeader customer={c} busy={busy} onBack={() => navigate("/clientes")} onAction={handleAction} />

      <QueueSection
        customer={c}
        saving={queueSaving}
        onReorder={handleReorder}
        onDetach={handleDetach}
        onAdd={() => setShowAdd(true)}
      />

      <CustomerRuns customerId={c.id} customerName={c.name} runs={runs} onChanged={loadRuns} />

      <CustomerBackups backups={backups} />

      {showEdit && (
        <CustomerFormModal
          title="Editar cliente"
          isEdit
          initial={{
            name: c.name, description: c.description || "", backup_hour: c.backup_hour, backup_minute: c.backup_minute,
            email_to: (c.email_to || []).join(", "),
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
    </>
  );
}
