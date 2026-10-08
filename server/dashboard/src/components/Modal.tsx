import { X } from "lucide-react";
import { useEffect } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
  width?: string | number;
}

export default function Modal({ title, onClose, children, wide, width }: Props) {
  useEffect(() => {
    const fn = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", fn);
    return () => document.removeEventListener("keydown", fn);
  }, [onClose]);

  // Combine styles
  let finalMaxWidth: string | number | undefined = undefined;
  if (width) {
    finalMaxWidth = width;
  } else if (wide) {
    finalMaxWidth = 900;
  }

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={finalMaxWidth ? { maxWidth: finalMaxWidth, width: "100%" } : {}}>
        <div className="modal-header">
          <h2 className="modal-title">{title}</h2>
          <button className="btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
