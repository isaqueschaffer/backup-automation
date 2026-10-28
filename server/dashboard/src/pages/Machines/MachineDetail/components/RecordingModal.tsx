import { CameraRecStatus } from "../../../../api/types";
import Modal from "../../../../components/Modal";
import StatusBadge from "../../../../components/StatusBadge";
import { fmtDate } from "../../../../utils/date";
import MiniCalendar from "./MiniCalendar";

export default function RecordingModal({ nvrName, cameras, lastBackupAt, onClose }: {
  nvrName: string;
  cameras: CameraRecStatus[];
  lastBackupAt: string | null;
  onClose: () => void;
}) {
  return (
    <Modal wide={true} title={`Gravação — ${nvrName} (${fmtDate(lastBackupAt)})`} onClose={onClose}>
      {cameras.length === 0 ? (
        <div className="empty-state">Sem dados de gravação disponíveis.</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Câmera</th>
                <th>Rede</th>
                <th>Gravação</th>
                <th>Dias Gravados</th>
                <th>Mapa (15 dias)</th>
              </tr>
            </thead>
            <tbody>
              {cameras.map((cam, i) => {
                let rede = cam.status_comunicacao;
                if (!rede) rede = cam.online ? "ONLINE" : (cam.online === false ? "OFFLINE" : "DESCONHECIDO");
                let gravacao = cam.status_gravacao;
                if (!gravacao) {
                  const gravouHoje = cam.mapa ? cam.mapa.endsWith("█") : (cam.total_dias ?? 0) > 0;
                  gravacao = gravouHoje ? "COM_GRAVACAO" : "SEM_GRAVACAO";
                }
                let diasTexto: string;
                if (typeof cam.dias_gravados === "number") {
                  diasTexto = `Dias gravados: ${cam.dias_gravados >= 730 ? "730+" : cam.dias_gravados}`;
                } else if (cam.dias_gravados === null) {
                  diasTexto = "Dias gravados: —";
                } else {
                  diasTexto = `${cam.total_dias || 0}/15`;
                }
                return (
                  <tr key={i}>
                    <td>{cam.nome || `Canal ${cam.canal}`}</td>
                    <td><StatusBadge status={rede} /></td>
                    <td><StatusBadge status={gravacao} /></td>
                    <td>{diasTexto}</td>
                    <td><MiniCalendar mapStr={cam.mapa || ""} referenceDate={lastBackupAt} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}
