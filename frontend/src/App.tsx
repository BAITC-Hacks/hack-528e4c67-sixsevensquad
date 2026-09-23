import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowRight, Building2, CheckCircle2, Download, FileSearch, FileText, GitCompareArrows, Layers3, Play, RefreshCw, ShieldAlert, UploadCloud, X } from "lucide-react";

type Evidence = { document: string; locator: string; quote: string; clause_id: string; side: string; text: string };
type Clause = Omit<Evidence, "quote" | "clause_id"> & { id: string };
type FunctionRecord = { id: string; owner: string; action: string; object: string; scope: string; side: string; evidence: { clause_id: string; quote: string }[] };
type SearchScope = { documents: string[]; catalog_size: number; owners?: string[]; candidates?: { id: string; owner: string; action: string; object: string; lexical_score: number }[]; note?: string };
type Finding = { id: string; kind: string; label: string; title: string; explanation: string; recommendation: string; before_ids: string[]; after_ids: string[]; evidence: Evidence[]; evidence_check?: { exact_quotes: boolean; required_sides_present: boolean; interpretation: string }; search_scope?: SearchScope };
type UnitChange = { before_names: string[]; after_names: string[]; status: string; explanation: string; evidence: Evidence[] };
type Review = { decision: "pending" | "confirmed" | "rejected"; comment: string };
type Result = { mode: string; report: string; counts: Record<string, number>; coverage: { before_functions: number; after_functions: number; clauses_processed: number }; functions: FunctionRecord[]; findings: Finding[]; unit_changes: UnitChange[]; limitations: string[] };
type Project = { id: string; created: string; status: string; stage: string; error?: string; documents: { name: string; side: string; clauses: Clause[] }[]; result: Result | null; reviews: Record<string, Review> };
type ProjectSummary = { id: string; created: string; status: string; stage: string };
type Health = { database: string; openai_configured: boolean; model: string };

const labels: Record<string, string> = { preserved: "Сохранена", transferred: "Передана", split: "Разделена", changed: "Изменена", uncertain: "Недостаточно данных", not_found: "Потенциальная потеря", new: "Без соответствия до", duplication: "Возможное дублирование", conflict: "Возможный конфликт" };
const unitLabels: Record<string, string> = { preserved: "Сохранено", reorganized: "Преобразовано", created: "Создано", not_found: "Не найдено после" };

async function api<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("json") ? await response.json() : { detail: await response.text() };
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Ошибка запроса");
  return data as T;
}

function EvidenceList({ items }: { items: Evidence[] }) {
  return <div className="source-list">{items.map((item, index) =>
    <details className="evidence" key={item.clause_id + index}>
      <summary><FileSearch size={15} /> {item.side === "before" ? "До" : "После"} · {item.document} · {item.locator}</summary>
      <blockquote>{item.quote}<small>Исходный фрагмент: {item.text}</small></blockquote>
    </details>
  )}</div>;
}

function EvidenceComparison({ items, lost }: { items: Evidence[]; lost: boolean }) {
  return <div className="source-columns">{(["before", "after"] as const).map(side => <section className="source-column" key={side}>
    <h4>{side === "before" ? "До реорганизации" : "После реорганизации"}</h4>
    {items.filter(item => item.side === side).map((item, index) => <div className="source-card" key={item.clause_id + index}>
      <strong>{item.document} · {item.locator}</strong><blockquote>«{item.quote}»</blockquote><small>Точный фрагмент подтверждён в загруженном файле.</small>
    </div>)}
    {!items.some(item => item.side === side) && <p className="source-absence">{side === "after" && lost ? "Подтверждающего пункта «после» нет: это результат поиска, а не доказательство упразднения функции." : "Для этой стороны источник не требуется."}</p>}
  </section>)}</div>;
}

function Drop({ title, files, setFiles }: { title: string; files: File[]; setFiles: (files: File[]) => void }) {
  return <section className="upload-card">
    <div className="upload-heading"><span className="version-dot" /><div><h3>{title}</h3><p>Можно добавить несколько документов</p></div></div>
    <label className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); setFiles([...files, ...Array.from(e.dataTransfer.files)]); }}>
      <input type="file" multiple accept=".txt,.pdf,.docx,.xlsx" onChange={e => setFiles([...files, ...Array.from(e.target.files || [])])} />
      <UploadCloud size={24} /><strong>Перетащите или выберите файлы</strong><span>DOCX · PDF с текстом · XLSX · TXT</span><small>До 10 МБ на файл</small>
    </label>
    <div className="file-list">{files.map((file, index) => <div className="file-row" key={file.name + index}><FileText size={17} /><span><b>{file.name}</b><small>{Math.ceil(file.size / 1024)} КБ</small></span><button onClick={() => setFiles(files.filter((_, i) => i !== index))} aria-label={"Удалить " + file.name}><X size={16} /></button></div>)}</div>
  </section>;
}

export default function App() {
  const analysis = useAnalysis();
  const { page, project, health, busy, connection } = analysis;
  const [before, setBefore] = useState<File[]>([]);
  const [after, setAfter] = useState<File[]>([]);
  const [project, setProject] = useState<Project | null>(null);
  const [history, setHistory] = useState<ProjectSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [tab, setTab] = useState<"map" | "structure" | "functions" | "risks" | "report">("map");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<Finding | null>(null);
  const [decision, setDecision] = useState<Review["decision"]>("pending");
  const [comment, setComment] = useState("");

  const loadHistory = async () => { try { setHistory(await api<ProjectSummary[]>("/api/projects")); } catch { /* API status shown separately */ } };
  useEffect(() => { api<Health>("/api/health").then(setHealth).catch(e => setError(e.message)); loadHistory(); }, []);
  useEffect(() => {
    if (!project || project.status !== "running") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await api<Project>("/api/projects/" + project.id);
        setProject(next);
        if (next.status === "completed") { setTab("map"); loadHistory(); }
        if (next.status === "failed") { setError(next.error || "Ошибка анализа"); loadHistory(); }
      } catch (e) { setError((e as Error).message); }
    }, 1400);
    return () => window.clearInterval(timer);
  }, [project?.id, project?.status]);

  const createFromFiles = async () => {
    if (!before.length || !after.length) return;
    setBusy(true); setError("");
    try {
      const form = new FormData();
      before.forEach(file => form.append("before", file)); after.forEach(file => form.append("after", file));
      const created = await api<{ id: string }>("/api/projects", { method: "POST", body: form });
      setProject(await api<Project>("/api/projects/" + created.id)); setTab("map"); await loadHistory();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const sample = async (kind: "organizer" | "control") => {
    setBusy(true); setError("");
    try {
      const created = await api<{ id: string }>("/api/projects/sample?kind=" + kind, { method: "POST" });
      setProject(await api<Project>("/api/projects/" + created.id)); setTab("map"); await loadHistory();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const start = async () => {
    if (!project) return;
    setBusy(true); setError("");
    try {
      await api("/api/projects/" + project.id + "/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "openai" }) });
      setProject(await api<Project>("/api/projects/" + project.id));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const openProject = async (id: string) => {
    setBusy(true); setError("");
    try { const loaded = await api<Project>("/api/projects/" + id); setProject(loaded); setTab("map"); setSelected(null); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const showFinding = (finding: Finding) => { setSelected(finding); setDecision(project?.reviews[finding.id]?.decision || "pending"); setComment(project?.reviews[finding.id]?.comment || ""); };
  const saveReview = async () => {
    if (!project || !selected) return;
    setBusy(true); setError("");
    try {
      await api("/api/projects/" + project.id + "/findings/" + selected.id + "/review", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, comment }) });
      setProject(await api<Project>("/api/projects/" + project.id));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };

  const result = project?.result;
  const catalog = useMemo(() => new Map((result?.functions || []).map(f => [f.id, f])), [result]);
  const clauseIndex = useMemo(() => new Map((project?.documents || []).flatMap(d => d.clauses).map(c => [c.id, c])), [project?.documents]);
  const findings = useMemo(() => (result?.findings || []).filter(f => {
    const owners = [...f.before_ids, ...f.after_ids].map(id => catalog.get(id)?.owner || "").join(" ");
    return (filter === "all" || f.kind === filter) && (f.title + " " + f.explanation + " " + owners).toLowerCase().includes(search.toLowerCase());
  }), [result, search, filter, catalog]);
  const ownerNames = (ids: string[]) => [...new Set(ids.map(id => catalog.get(id)?.owner).filter(Boolean))].join(", ") || "—";
  const evidenceFor = (f: FunctionRecord): Evidence[] => f.evidence.flatMap(e => {
    const clause = clauseIndex.get(e.clause_id);
    return clause ? [{ ...clause, clause_id: e.clause_id, quote: e.quote }] : [];
  });
  const mapFindings = (result?.findings || []).filter(f => !["duplication", "conflict"].includes(f.kind));

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="#top"><span className="brand-mark"><Layers3 size={20} /></span><span>ОргКонтур<small>Анализ реорганизации</small></span></a><div className="engine-status"><span /> {health?.database === "memory" ? "Локальное хранение" : health?.database === "connected" ? "MongoDB подключена" : "Проверка сервера"} <b>{!health ? "Проверка подключения" : health.openai_configured ? "ИИ-анализ · OpenAI" : "Проверьте подключение OpenAI"}</b></div></header>
    <main id="top">
      <section className="intro"><div><span className="eyebrow"><FileSearch size={14} /> Рабочая область</span><h1>Анализ структуры<br />и функций подразделений</h1><p>Загрузите документы «до» и «после». Проверьте переходы функций, потенциальные потери, пересечения и источники каждого вывода.</p></div><div className="sample-actions"><button className="ghost-button" onClick={() => sample("organizer")} disabled={busy}><Play size={16} /> Пример №8 → №9</button><button className="ghost-button" onClick={() => sample("control")} disabled={busy}><Play size={16} /> Контрольный пример</button></div></section>
      <section className="workflow-card"><div className="steps"><span className="active"><b>1</b> Документы</span><i /><span><b>2</b> Анализ</span><i /><span><b>3</b> Проверка выводов</span></div>
        <div className="upload-grid"><Drop title="До реорганизации" files={before} setFiles={setBefore} /><div className="compare-icon"><GitCompareArrows size={20} /></div><Drop title="После реорганизации" files={after} setFiles={setAfter} /></div>
        <div className="action-row"><span>До 12 файлов на комплект. Сканам PDF нужен OCR.</span><button className="primary-button" onClick={createFromFiles} disabled={!before.length || !after.length || busy}><UploadCloud size={17} /> Загрузить комплект</button></div>
      </section>
      {error && <div className="error-banner"><AlertTriangle size={18} /> {error}</div>}
      <section className="project-control"><div className="control-title"><h2>Проект анализа</h2><p>{project ? project.stage : "Выберите пример или загрузите документы"}</p></div><select aria-label="Открыть проект" value={project?.id || ""} onChange={e => e.target.value && openProject(e.target.value)}><option value="">История проектов</option>{history.map(p => <option value={p.id} key={p.id}>{new Date(p.created).toLocaleString("ru")} · {p.status} · {p.id.slice(0, 8)}</option>)}</select></section>
      {project && <section className="project-body"><div className="document-chips">{project.documents.map((d, i) => <span key={i}><FileText size={15} /> {d.side === "before" ? "До" : "После"}: {d.name} · {d.clauses.length} фрагментов</span>)}</div>
        {project.status === "ready" || project.status === "failed" ? <div className="analysis-start"><p>ИИ сопоставит структуру и функции подразделений, найдёт возможные потери и пересечения и покажет источники выводов. Анализ выполняется через OpenAI.</p><button className="primary-button" onClick={start} disabled={busy}>{busy ? <RefreshCw className="spin" size={17} /> : <FileSearch size={17} />} Начать анализ</button></div> : null}
        {project.status === "running" && <div className="progress"><RefreshCw className="spin" size={19} /> {project.stage}</div>}
      </section>}
      {result && project && <section className="results" id="results"><div className="results-head"><div><span className="eyebrow"><CheckCircle2 size={14} /> Анализ завершён</span><h2>Результаты сравнения</h2><p>Обработано {result.coverage.clauses_processed} фрагментов · функций до: {result.coverage.before_functions}, после: {result.coverage.after_functions}</p></div><div className="export-actions"><a className="ghost-button" href={`/api/projects/${project.id}/export?format=docx`}><Download size={16} /> Word</a><a className="ghost-button" href={`/api/projects/${project.id}/export?format=csv`}><Download size={16} /> CSV</a><a className="ghost-button" href={`/api/projects/${project.id}/export?format=md`}><Download size={16} /> Markdown</a><a className="ghost-button" href={`/api/projects/${project.id}/export?format=json`}><Download size={16} /> JSON</a></div></div>
        <div className="metrics"><div><span>Переходы</span><strong>{result.unit_changes.length}</strong><small>подразделений и ролей</small></div><div><span>Передано</span><strong>{result.counts.transferred || 0}</strong><small>функций</small></div><div><span>Потери</span><strong>{result.counts.not_found || 0}</strong><small>кандидатов</small></div><div><span>Дубли</span><strong>{result.counts.duplication || 0}</strong><small>кандидатов</small></div><div><span>Конфликты</span><strong>{result.counts.conflict || 0}</strong><small>кандидатов</small></div></div>
        <div className="tabs" role="tablist"><button className={tab === "map" ? "active" : ""} onClick={() => setTab("map")}><GitCompareArrows size={17} /> Карта функций</button><button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}><Building2 size={17} /> Структура</button><button className={tab === "functions" ? "active" : ""} onClick={() => setTab("functions")}><FileSearch size={17} /> Все выводы <b>{result.findings.length}</b></button><button className={tab === "risks" ? "active" : ""} onClick={() => setTab("risks")}><ShieldAlert size={17} /> Риски</button><button className={tab === "report" ? "active" : ""} onClick={() => setTab("report")}><FileText size={17} /> Заключение</button></div>
        {tab === "map" && <div className="fate-map"><div className="map-intro"><h3>Карта судьбы функций</h3><p>Каждая строка — функция из редакции «до» и её найденный путь в редакции «после». Нажмите «Проверить доказательства», чтобы увидеть точные пункты. Возможная потеря означает лишь отсутствие убедительного соответствия в загруженном комплекте.</p></div><div className="map-header"><span>До · владелец и функция</span><span>Результат</span><span>После · владелец и функция</span><span>Проверка</span></div>{mapFindings.map(f => <div className={`map-row map-${f.kind}`} key={f.id}><div className="map-side">{f.before_ids.length ? f.before_ids.map(id => <div key={id}><strong>{catalog.get(id)?.owner || "—"}</strong><p>{catalog.get(id)?.action} {catalog.get(id)?.object !== catalog.get(id)?.action ? catalog.get(id)?.object : ""}</p></div>) : <span className="map-muted">Не установлено</span>}</div><div className="map-status"><span className={`pill ${["not_found", "uncertain"].includes(f.kind) ? "pill-danger" : ""}`}>{f.label}</span><ArrowRight size={16} /></div><div className="map-side">{f.after_ids.length ? f.after_ids.map(id => <div key={id}><strong>{catalog.get(id)?.owner || "—"}</strong><p>{catalog.get(id)?.action} {catalog.get(id)?.object !== catalog.get(id)?.action ? catalog.get(id)?.object : ""}</p></div>) : <span className="map-muted">Убедительный владелец не найден</span>}</div><button className="ghost-button" onClick={() => showFinding(f)}>Доказательства</button></div>)}</div>}
        {tab === "structure" && <div className="panel">{result.unit_changes.map((u, i) => <article className="transition" key={i}><div><strong>{u.before_names.join(", ") || "—"}</strong></div><div className="status">{unitLabels[u.status] || u.status}<ArrowRight size={14} /></div><div><strong>{u.after_names.join(", ") || "—"}</strong><p>{u.explanation}</p><EvidenceList items={u.evidence} /></div></article>)}</div>}
        {tab === "functions" && <div className="panel"><div className="list-controls"><input placeholder="Поиск по функции или владельцу" value={search} onChange={e => setSearch(e.target.value)} /><select value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Все статусы</option>{Object.keys(labels).map(key => <option value={key} key={key}>{labels[key]}</option>)}</select></div>{findings.map(f => <article className="finding-row" key={f.id}><div><span className={`pill ${["not_found", "duplication", "conflict", "uncertain"].includes(f.kind) ? "pill-danger" : ""}`}>{f.label}</span><h3>{f.title}</h3><p>{ownerNames(f.before_ids)} → {ownerNames(f.after_ids)}</p></div><button className="ghost-button" onClick={() => showFinding(f)}>{project.reviews[f.id]?.decision === "confirmed" ? "Подтверждено" : project.reviews[f.id]?.decision === "rejected" ? "Отклонено" : "Проверить доказательства"}</button></article>)}{!findings.length && <div className="empty">Нет выводов по выбранному фильтру.</div>}<section className="function-register"><h3>Извлечённые функции и источники</h3><p>Реестр позволяет проверить полноту извлечения до оценки выводов.</p>{result.functions.map(f => <div className="register-row" key={f.id}><span>{f.side === "before" ? "До" : "После"}</span><strong>{f.owner}</strong><div>{f.action}{f.object !== f.action ? ` — ${f.object}` : ""}<EvidenceList items={evidenceFor(f)} /></div></div>)}</section></div>}
        {tab === "risks" && <div className="risk-grid">{result.findings.filter(f => ["not_found", "duplication", "conflict"].includes(f.kind)).map(f => <article className="risk-card" key={f.id}><div className="risk-top"><span><AlertTriangle size={18} /></span><div><small>{f.label}</small><h3>{f.title}</h3></div></div><p>{f.explanation}</p><div className="recommendation">Рекомендация: {f.recommendation}</div><button className="ghost-button" onClick={() => showFinding(f)}>Источники и решение</button></article>)}</div>}
        {tab === "report" && <div className="report-panel"><h3>Аналитическое заключение</h3><pre>{result.report}</pre><h3>Ограничения</h3><ul>{result.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul></div>}
      </section>}
    </main>
    {selected && <div className="modal-backdrop" onMouseDown={e => e.target === e.currentTarget && setSelected(null)}><section className="detail-modal" role="dialog" aria-modal="true" aria-label="Проверка доказательств"><div className="modal-head"><div><small>{selected.label}</small><h2>{selected.title}</h2></div><button onClick={() => setSelected(null)} aria-label="Закрыть"><X size={19} /></button></div><p><b>Вывод системы:</b> {selected.explanation}</p><p><b>Рекомендация:</b> {selected.recommendation}</p><div className="verification"><CheckCircle2 size={18} /><span>Файлы, пункты и дословные цитаты проверены сервером. Это подтверждает источники, но не правильность смыслового вывода — его проверяет аналитик.</span></div><h3>Доказательства по редакциям</h3><EvidenceComparison items={selected.evidence} lost={selected.kind === "not_found"} />{selected.search_scope && <div className="search-audit"><h3>Где искали соответствие</h3><p>Просмотрено {selected.search_scope.catalog_size} извлечённых функций в документах: {selected.search_scope.documents.join(", ") || "—"}.</p><p>Владельцы: {selected.search_scope.owners?.join(", ") || "сведения появятся после обновления API"}.</p>{Boolean(selected.search_scope.candidates?.length) && <><strong>Ближайшие формулировки для ручной проверки:</strong><ul>{selected.search_scope.candidates?.map(c => <li key={c.id}>{c.owner}: {c.action}{c.object !== c.action ? ` — ${c.object}` : ""}</li>)}</ul></>}{selected.search_scope.note && <small>{selected.search_scope.note}</small>}</div>}<div className="review-form"><label>Решение аналитика<select value={decision} onChange={e => setDecision(e.target.value as Review["decision"])}><option value="pending">Требует проверки</option><option value="confirmed">Подтверждено</option><option value="rejected">Отклонено</option></select></label><label>Комментарий<textarea value={comment} onChange={e => setComment(e.target.value)} placeholder="Почему вы приняли это решение" /></label><button className="primary-button" onClick={saveReview} disabled={busy}>Сохранить решение</button></div></section></div>}
    <footer><span>ОргКонтур · React + FastAPI</span><span>Выводы рекомендательные, проверяйте источники</span></footer>
  </div>;
}
