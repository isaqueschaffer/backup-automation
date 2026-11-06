import { Renovacao } from "../../api/types";
import { fmtDate, fmtDay } from "../../utils/date";

interface HistoricoValidadeProps {
  renovacoes?: Renovacao[];
}

export default function HistoricoValidade({ renovacoes = [] }: HistoricoValidadeProps) {
  return (
    <div className="card" style={{ marginTop: 24 }}>
      <h3
        style={{
          fontSize: 16,
          fontWeight: 600,
          color: "var(--text-primary)",
          margin: "0 0 16px 0",
        }}
      >
        Histórico de validade
      </h3>

      {!renovacoes || renovacoes.length === 0 ? (
        <div className="empty-state" style={{ padding: "24px 16px" }}>
          <div>Sem registros de histórico de validade.</div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th>Plano</th>
                <th>Dias</th>
                <th>De → Para</th>
                <th>Feito por</th>
              </tr>
            </thead>
            <tbody>
              {renovacoes.map((r) => (
                <tr key={r.id}>
                  <td>{fmtDate(r.criado_em)}</td>
                  <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {r.plano_nome}
                  </td>
                  <td>+{r.dias}</td>
                  <td>
                    {fmtDay(r.expira_em_anterior)} → {fmtDay(r.expira_em_nova)}
                  </td>
                  <td>{r.feito_por ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
