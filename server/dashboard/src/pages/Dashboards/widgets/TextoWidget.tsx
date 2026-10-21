import { DadosTexto, WidgetInstancia } from "../types";

interface Props {
  dados: DadosTexto;
  widget: WidgetInstancia;
}

export default function TextoWidget({ dados }: Props) {
  return (
    <div
      style={{
        height: "100%",
        overflow: "auto",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        fontSize: 13,
        color: "var(--text-secondary)",
        lineHeight: 1.5,
      }}
    >
      {dados.texto || ""}
    </div>
  );
}
