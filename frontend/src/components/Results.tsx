import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, Building2, Check, CheckCheck, ChevronDown, CircleAlert, Download, FileCheck2, FileSearch, List, Search, ShieldAlert, X } from "lucide-react";
import type { Evidence, Finding, Project } from "../types";
import { findingTitle, functionText, isRisk, labels, ownersFor, reviewLabels, unitLabels } from "../lib";
import { Badge, Empty, SourceCard } from "./ui";

export function ExportMenu({ project }: { project: Project }) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);
  return <div className="export-menu"><button className="button button-secondary" onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Скачать заключение"><Download size={17} /><span>Скачать заключение</span><ChevronDown size={15} /></button>{open && <><button className="menu-dismiss" tabIndex={-1} aria-label="Закрыть меню экспорта" onClick={() => setOpen(false)} /><div className="export-options">{[["docx", "Word"], ["csv", "CSV"], ["md", "Markdown"], ["json", "JSON"]].map(([format, label]) => <a key={format} href={"/api/projects/" + project.id + "/export?format=" + format} onClick={() => setOpen(false)}><FileCheck2 size={16} />{label}<span>{format.toUpperCase()}</span></a>)}</div></>}</div>;
}

export function FindingsRegistry({ project, onSelect, onSource }: { project: Project; onSelect: (f: Finding) => void; onSource: (e: Evidence) => void }) {
  const [view, setView] = useState<"findings" | "register">("findings");
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("all");
  const [decision, setDecision] = useState("all");
  const [side, setSide] = useState("all");
  const result = project.result!;
  const query = search.trim().toLowerCase();
  const findings = result.findings.filter(f => (kind === "all" || f.kind === kind) && (decision === "all" || (project.reviews[f.id]?.decision || "pending") === decision) && (f.title + " " + f.explanation + " " + ownersFor([...f.before_ids, ...f.after_ids], result.functions)).toLowerCase().includes(query));
  const functions = result.functions.filter(f => (side === "all" || f.side === side) && (f.owner + " " + functionText(f) + " " + f.scope).toLowerCase().includes(query));
  const clauses = new Map(project.documents.flatMap(d => d.clauses).map(c => [c.id, c]));
  return <section className="panel registry-panel"><div className="panel-heading"><div className="heading-with-icon"><span className="section-icon"><FileSearch size={21} /></span><div><h2>Выводы и извлечённые функции</h2><p>Проверьте полноту извлечения и каждое сопоставление</p></div></div></div>
    <div className="map-subtabs" role="tablist" aria-label="Выводы или реестр"><button role="tab" aria-selected={view === "findings"} className={view === "findings" ? "active" : ""} onClick={() => setView("findings")}><List size={16} />Все выводы<span>{result.findings.length}</span></button><button role="tab" aria-selected={view === "register"} className={view === "register" ? "active" : ""} onClick={() => setView("register")}><FileSearch size={16} />Реестр функций<span>{result.functions.length}</span></button></div>
    <div className="filter-row"><label className="search-field"><Search size={17} /><input value={search} onChange={e => setSearch(e.target.value)} aria-label="Поиск функций и выводов" placeholder="Найти функцию или владельца" /></label>{view === "findings" ? <><select aria-label="Тип вывода" value={kind} onChange={e => setKind(e.target.value)}><option value="all">Все типы</option>{Object.entries(labels).map(([key, value]) => <option value={key} key={key}>{value}</option>)}</select><select aria-label="Решение аналитика — фильтр" value={decision} onChange={e => setDecision(e.target.value)}><option value="all">Все решения</option>{Object.entries(reviewLabels).map(([key, value]) => <option value={key} key={key}>{value}</option>)}</select></> : <select aria-label="Редакция функций" value={side} onChange={e => setSide(e.target.value)}><option value="all">Обе редакции</option><option value="before">До реорганизации</option><option value="after">После реорганизации</option></select>}</div>
    {view === "findings" ? <div className="all-findings">{findings.map(f => <article className="all-finding-row" key={f.id}><div><div className="finding-row-top"><Badge kind={f.kind} /><span className={"review-state " + (project.reviews[f.id]?.decision || "pending")}>{reviewLabels[project.reviews[f.id]?.decision || "pending"]}</span></div><h3>{findingTitle(f)}</h3><p>{f.explanation}</p><small>{ownersFor([...f.before_ids, ...f.after_ids], result.functions)}</small></div><button className="button button-secondary" onClick={() => onSelect(f)}><FileSearch size={16} />Проверить<ArrowUpRight size={14} /></button></article>)}{!findings.length && <Empty title="Выводов по фильтру нет" text="Измените поиск, тип вывода или статус проверки." />}</div> : <div className="function-register">{functions.map(f => <article className="register-item" key={f.id}><div className="register-meta"><span className={"side-label " + f.side}>{f.side === "before" ? "До" : "После"}</span><strong>{f.owner}</strong><small>{f.id}</small></div><h3>{functionText(f)}</h3><p>Область ответственности: {f.scope}</p><div className="register-sources">{f.evidence.map((e, index) => { const clause = clauses.get(e.clause_id); return clause && <details key={index}><summary><FileSearch size={15} />{clause.document} · {clause.locator}<ChevronDown size={15} /></summary><blockquote>«{e.quote}»</blockquote><button className="text-button" onClick={() => onSource({ ...clause, clause_id: e.clause_id, quote: e.quote })}>Исходный пункт<ArrowUpRight size={14} /></button></details>; })}</div></article>)}{!functions.length && <Empty title="Функций по фильтру нет" text="Измените поисковый запрос или редакцию." />}</div>}
  </section>;
}

export function Risks({ project, onSelect }: { project: Project; onSelect: (finding: Finding) => void }) {
  const [kind, setKind] = useState("all");
  const [pending, setPending] = useState(false);
  const all = project.result!.findings.filter(isRisk);
  const visible = all.filter(f => (kind === "all" || f.kind === kind) && (!pending || !project.reviews[f.id] || project.reviews[f.id].decision === "pending"));
  return <><div className="risk-filter"><select aria-label="Тип риска" value={kind} onChange={e => setKind(e.target.value)}><option value="all">Все риски · {all.length}</option>{["not_found", "duplication", "conflict", "uncertain"].map(k => <option key={k} value={k}>{labels[k]}</option>)}</select><label className="checkbox-label"><input type="checkbox" checked={pending} onChange={e => setPending(e.target.checked)} />Только непроверенные</label></div><div className="risks-grid">{visible.map((f, index) => <article className="panel risk-item animate-row" style={{ animationDelay: Math.min(index, 6) * 40 + "ms" }} key={f.id}><div className="risk-item-top"><span className="risk-icon"><ShieldAlert size={21} /></span><Badge kind={f.kind} /><span className={"review-state " + (project.reviews[f.id]?.decision || "pending")}>{reviewLabels[project.reviews[f.id]?.decision || "pending"]}</span></div><h3>{findingTitle(f)}</h3><p>{f.explanation}</p><div className="risk-recommendation"><strong>Рекомендация</strong><p>{f.recommendation}</p></div><div className="risk-item-footer"><span><FileCheck2 size={15} />{f.evidence.length} фрагментов</span><button className="text-button" onClick={() => onSelect(f)}>Источники и решение<ArrowRight size={16} /></button></div></article>)}</div>{!visible.length && <div className="panel"><Empty title={pending ? "Непроверенных рисков по фильтру нет" : "Риски этой категории не найдены"} text="Полноту анализа можно проверить по реестру функций и исходным документам." /></div>}</>;
}

export function Structure({ project, onSource }: { project: Project; onSource: (e: Evidence) => void }) {
  const [filter, setFilter] = useState("all");
  const changes = project.result!.unit_changes;
  const visible = changes.filter(c => filter === "all" || c.status === filter);
  return <section className="panel structure-panel"><div className="panel-heading"><div><h2>Подразделения и роли</h2><p>Изменения структуры с основаниями из документов</p></div><select aria-label="Тип изменения подразделения" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Все изменения · {changes.length}</option>{Object.entries(unitLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
    <div className="structure-table-head"><span>До реорганизации</span><span>Изменение</span><span>После реорганизации</span></div>
    {visible.map((change, index) => <article className="structure-item" key={index}><div className="structure-row"><div><Building2 size={19} /><strong>{change.before_names.join(", ") || "Нет соответствия до"}</strong></div><Badge kind={change.status}>{unitLabels[change.status] || change.status}</Badge><div><Building2 size={19} /><strong>{change.after_names.join(", ") || "Не найдено в новом комплекте"}</strong></div></div><p>{change.explanation}</p><details className="structure-evidence"><summary><FileCheck2 size={14} />Источники · {change.evidence.length}<ChevronDown size={14} /></summary><div>{change.evidence.map((e, i) => <SourceCard key={i} item={e} onOpen={onSource} />)}</div></details></article>)}
    {!visible.length && <Empty title="Изменений этого типа нет" text="Выберите другой фильтр для просмотра структуры." />}
  </section>;
}

export function Report({ project }: { project: Project }) {
  const result = project.result!;
  const text = result.report;
  const reviewed = result.findings.filter(f => project.reviews[f.id]?.decision && project.reviews[f.id]?.decision !== "pending").length;
  return <div className="report-layout"><article className="panel report-paper"><div className="report-paper-top"><span className="overline">ОРГКОНТУР / АНАЛИТИКА</span><FileCheck2 size={22} /></div>{text.split("\n").map((line, index) => {
    if (!line.trim()) return null;
    if (line.startsWith("# ")) return <h2 key={index}>{line.slice(2)}</h2>;
    if (line.startsWith("## ")) return <h3 key={index}>{line.slice(3).replace(/finding-\d+: /, "")}</h3>;
    if (line.startsWith("> ")) return <blockquote key={index}>{line.slice(2)}</blockquote>;
    if (line.startsWith("- ")) return <div className="report-list-line" key={index}><span>•</span><p>{line.slice(2)}</p></div>;
    return <p key={index}>{line}</p>;
  })}</article><aside className="report-aside"><section className="panel"><span className="report-aside-icon"><CheckCheck size={22} /></span><h3>Проверка заключения</h3><p>Подтверждайте выводы после проверки источников.</p><div className="review-progress"><span style={{ width: (result.findings.length ? reviewed / result.findings.length * 100 : 0) + "%" }} /></div><strong>{reviewed} из {result.findings.length} выводов проверено</strong><div className="review-totals"><span><Check size={14} />Подтверждено<b>{Object.values(project.reviews).filter(r => r.decision === "confirmed").length}</b></span><span><CircleAlert size={14} />Ожидают проверки<b>{result.findings.length - reviewed}</b></span></div></section><section className="report-limits"><h3>Границы анализа</h3>{result.limitations.map((l, i) => <p key={i}><span>{String(i + 1).padStart(2, "0")}</span>{l}</p>)}</section></aside></div>;
}
