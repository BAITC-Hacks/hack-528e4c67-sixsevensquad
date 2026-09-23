import { useEffect, useId, useRef, type ReactNode } from "react";
import { ArrowUpRight, Check, FileSearch, X } from "lucide-react";
import type { Evidence } from "../types";
import { labels } from "../lib";

export function Logo({ compact = false }: { compact?: boolean }) {
  return <div className="brand"><span className="brand-symbol" role="img" aria-label="Логотип ОргКонтур" />{!compact && <span className="brand-word">ОргКонтур<span>АНАЛИЗ ОРГСТРУКТУРЫ</span></span>}</div>;
}
export function Badge({ kind, children }: { kind?: string; children?: ReactNode }) {
  return <span className={"badge badge-" + (kind || "neutral")}><span className="badge-dot" />{children || labels[kind || ""] || kind}</span>;
}
export function Empty({ title, text, children }: { title: string; text: string; children?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><FileSearch size={28} strokeWidth={1.5} /></div><h3>{title}</h3><p>{text}</p>{children}</div>;
}
export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} aria-labelledby={titleId} className={"modal" + (wide ? " modal-wide" : "")} onCancel={onClose} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
    <div className="modal-shell"><header className="modal-head"><h2 id={titleId}>{title}</h2><button className="icon-button" onClick={onClose} aria-label="Закрыть окно"><X size={20} /></button></header>{children}</div>
  </dialog>;
}
export function SourceCard({ item, onOpen }: { item: Evidence; onOpen: (e: Evidence) => void }) {
  return <div className="source-card">
    <div className="source-label">{item.side === "before" ? "До реорганизации" : "После реорганизации"}<span>{item.locator}</span></div>
    <blockquote>«{item.quote}»</blockquote>
    <button className="source-link" onClick={() => onOpen(item)}><FileSearch size={15} /><span>{item.document}</span><ArrowUpRight size={15} /></button>
  </div>;
}
export function EvidenceModal({ evidence, onClose }: { evidence: Evidence; onClose: () => void }) {
  const index = evidence.text.indexOf(evidence.quote);
  return <Modal title="Фрагмент документа" onClose={onClose}>
    <div className="document-preview-head"><FileSearch size={24} /><div><h3>{evidence.document}</h3><p>{evidence.side === "before" ? "До реорганизации" : "После реорганизации"} · {evidence.locator}</p></div></div>
    <div className="document-paper">{index >= 0 ? <>{evidence.text.slice(0, index)}<mark>{evidence.quote}</mark>{evidence.text.slice(index + evidence.quote.length)}</> : evidence.text}</div>
    <p className="fine-print"><Check size={15} /> Показан извлечённый текст исходного пункта документа.</p>
  </Modal>;
}
