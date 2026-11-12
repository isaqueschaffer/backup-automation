import { useState } from "react";
import { Image } from "lucide-react";

// Painel de imagem da câmera: usado pela referência e pela noite para garantir a mesma visualização.
// "contain" mostra o quadro inteiro (sem cortar o enquadramento) e a resolução ajuda a comparar a origem.
export default function CameraImagePanel({ dotColor, label, base64, alt, emptyText, onZoom }: {
  dotColor: string, label: string, base64?: string | null, alt: string, emptyText: string, onZoom: (src: string) => void
}) {
  const [dims, setDims] = useState<string | null>(null);
  const src = base64 ? `data:image/jpeg;base64,${base64}` : null;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor }}></div>
        {label}
        {src && dims && <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 500, letterSpacing: 0 }}>{dims}</span>}
      </div>
      <div style={{ background: "#000", borderRadius: 12, border: "1px solid var(--border)", overflow: "hidden", aspectRatio: "16/9", display: "flex", alignItems: "center", justifyContent: "center" }}>
        {src ? (
          <img
            src={src}
            alt={alt}
            style={{ width: "100%", height: "100%", objectFit: "contain", cursor: "zoom-in", transition: "transform 0.3s" }}
            onLoad={(e) => setDims(`${e.currentTarget.naturalWidth}×${e.currentTarget.naturalHeight}`)}
            onMouseOver={(e) => (e.currentTarget.style.transform = "scale(1.03)")}
            onMouseOut={(e) => (e.currentTarget.style.transform = "scale(1)")}
            onClick={() => onZoom(src)}
          />
        ) : (
          <div style={{ color: "var(--text-muted)", display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
            <Image size={32} opacity={0.3} />
            <span>{emptyText}</span>
          </div>
        )}
      </div>
    </div>
  );
}
