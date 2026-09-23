import { useRef, useState } from "react";
import { ArrowDownToLine, ArrowRight, Check, CheckCircle2, File, FileText, FolderOpen, LoaderCircle, Plus, ShieldCheck, Upload, X } from "lucide-react";
import type { DocumentRecord, Project, Side } from "../types";
import { Modal } from "./ui";
import { counted } from "../lib";

const allowed = /\.(pdf|docx|xlsx|txt)$/i;
export function UploadZone({ side, files, otherCount, onFiles, onError }: { side: Side; files: File[]; otherCount: number; onFiles: (f: File[]) => void; onError: (s: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const depth = useRef(0);
  const add = (incoming: File[]) => {
    const next = [...files]; const errors: string[] = [];
    for (const file of incoming) {
      if (!allowed.test(file.name)) { errors.push(file.name + ": поддерживаются PDF, DOCX, XLSX и TXT."); continue; }
      if (file.size > 10 * 1024 * 1024) { errors.push(file.name + ": размер превышает 10 МБ."); continue; }
      if (!file.size) { errors.push(file.name + ": файл пуст."); continue; }
      if (next.some(f => f.name === file.name && f.size === file.size && f.lastModified === file.lastModified)) continue;
      if (next.length + otherCount >= 12) { errors.push("Можно загрузить до 12 файлов суммарно в оба комплекта."); break; }
      next.push(file);
    }
    onFiles(next); onError(errors.join(" "));
  };
  return <section className={"upload-zone " + (dragging ? "is-dragging" : "")}>
    <header><span className={"version-icon " + side}><FileText size={19} /></span><div><h3>{side === "before" ? "До реорганизации" : "После реорганизации"}</h3><p>{side === "before" ? "Действующая структура и положения" : "Новая структура и документы"}</p></div><span className="version-number">{side === "before" ? "01" : "02"}</span></header>
    <div className="drop-area" onDragEnter={e => { e.preventDefault(); depth.current++; setDragging(true); }} onDragOver={e => e.preventDefault()} onDragLeave={e => { e.preventDefault(); depth.current--; if (depth.current <= 0) setDragging(false); }} onDrop={e => { e.preventDefault(); depth.current = 0; setDragging(false); add(Array.from(e.dataTransfer.files)); }}>
      <div className="upload-icon"><Upload size={25} strokeWidth={1.6} /></div><strong>Перетащите документы сюда</strong><p>или <button className="inline-button" onClick={() => input.current?.click()}>выберите файлы</button> на компьютере</p>
      <div className="format-tags"><span>PDF</span><span>DOCX</span><span>XLSX</span><span>TXT</span></div>
      <input ref={input} type="file" className="sr-only" tabIndex={-1} multiple accept=".pdf,.docx,.xlsx,.txt" aria-label={side === "before" ? "Документы до реорганизации" : "Документы после реорганизации"} onChange={e => { add(Array.from(e.target.files || [])); e.target.value = ""; }} />
    </div>
    {!!files.length && <div className="upload-file-list">{files.map((f, i) => <div className="upload-file" key={f.name + i}><FileText size={18} /><div><strong>{f.name}</strong><small>{f.size < 1048576 ? Math.ceil(f.size / 1024) + " КБ" : (f.size / 1048576).toFixed(1) + " МБ"}</small></div><Check size={15} className="file-ready" /><button className="icon-button" aria-label={"Удалить " + f.name} onClick={() => onFiles(files.filter((_, n) => n !== i))}><X size={15} /></button></div>)}</div>}
  </section>;
}

export function UploadWorkspace({ before, after, setBefore, setAfter, onSubmit, onError, busy }: {
  before: File[]; after: File[]; setBefore: (f: File[]) => void; setAfter: (f: File[]) => void; onSubmit: () => void; onError: (s: string) => void; busy: boolean;
}) {
  return <div className="upload-workspace panel">
    <div className="section-header"><div><span className="overline">НОВЫЙ АНАЛИЗ</span><h2>Начните с документов</h2></div><div className="workflow-steps"><span className="current"><b>1</b>Документы</span><i /><span><b>2</b>Сравнение</span><i /><span><b>3</b>Заключение</span></div></div>
    <div className="upload-pair"><UploadZone side="before" files={before} otherCount={after.length} onFiles={setBefore} onError={onError} /><div className="upload-pair-arrow"><ArrowRight size={17} /></div><UploadZone side="after" files={after} otherCount={before.length} onFiles={setAfter} onError={onError} /></div>
    <footer className="upload-footer"><div><ShieldCheck size={17} /><span>До 10 МБ на файл · 12 файлов в двух комплектах<small>PDF должен содержать текст. Для сканов понадобится распознавание.</small></span></div><button className="button button-primary" disabled={!before.length || !after.length || busy} onClick={onSubmit}>{busy ? <LoaderCircle className="spin" size={17} /> : <ArrowDownToLine size={17} />}{busy ? "Загружаем документы…" : "Загрузить и продолжить"}</button></footer>
  </div>;
}

export function DocumentLibrary({ project, onNew }: { project: Project; onNew: () => void }) {
  const [opened, setOpened] = useState<DocumentRecord | null>(null);
  const [query, setQuery] = useState("");
  return <>
    <div className="section-header standalone"><div><h2>Исходные документы</h2><p>Откройте документ, чтобы проверить распознанные пункты.</p></div><button className="button button-secondary" onClick={onNew}><Plus size={16} />Другой комплект</button></div>
    <div className="document-columns">{(["before", "after"] as const).map(side => <section className="panel document-column" key={side}><header><span className={"version-icon " + side}><FolderOpen size={20} /></span><div><h3>{side === "before" ? "До реорганизации" : "После реорганизации"}</h3><p>{counted(project.documents.filter(d => d.side === side).length, "документ", "документа", "документов")}</p></div></header>{project.documents.filter(d => d.side === side).map((d, index) => <button className="library-document" key={index} onClick={() => { setOpened(d); setQuery(""); }}><span className="file-extension"><File size={23} /><small>{d.name.split(".").pop()?.toUpperCase()}</small></span><span><strong>{d.name}</strong><small>{counted(d.clauses.length, "распознанный фрагмент", "распознанных фрагмента", "распознанных фрагментов")}</small></span><ArrowRight size={17} /></button>)}<div className="document-column-note"><CheckCircle2 size={14} />Исходные пункты доступны для проверки</div></section>)}</div>
    {opened && <Modal title={opened.name} onClose={() => setOpened(null)} wide><div className="document-modal-toolbar"><span>{opened.side === "before" ? "До реорганизации" : "После реорганизации"}</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Найти текст в документе…" aria-label="Поиск в документе" /></div><div className="clause-list">{opened.clauses.filter(c => c.text.toLowerCase().includes(query.toLowerCase())).map(c => <article key={c.id}><span>{c.locator}</span><p>{c.text}</p></article>)}{!opened.clauses.some(c => c.text.toLowerCase().includes(query.toLowerCase())) && <p className="muted">Совпадений не найдено. Попробуйте другой запрос.</p>}</div></Modal>}
  </>;
}
