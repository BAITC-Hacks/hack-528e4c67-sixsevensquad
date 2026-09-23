import { useState } from "react";
import { ArrowRight, ArrowUpRight, FileSearch, GitCompareArrows, Search } from "lucide-react";
import type { Finding, FunctionRecord, Project } from "../types";
import { functionText, labels, reviewLabels } from "../lib";
import { Badge, Empty } from "./ui";

function FunctionCell({ ids, catalog, side }: { ids: string[]; catalog: Map<string, FunctionRecord>; side: "before" | "after" }) {
  return <div className="comparison-cell"><span className="mobile-cell-label">{side === "before" ? "До реорганизации" : "После реорганизации"}</span>
    {ids.length ? ids.map(id => { const f = catalog.get(id); return f ? <div className="comparison-function" key={id}><strong>{f.owner}</strong><p>{functionText(f)}</p><small>{f.scope}</small></div> : <p key={id}>Функция не найдена в каталоге</p>; }) : <p className="comparison-absence">{side === "before" ? "Соответствие в исходной редакции не установлено" : "Убедительное соответствие не найдено"}</p>}
  </div>;
}

export default function Comparison({ project, onSelect }: { project: Project; onSelect: (finding: Finding) => void }) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const result = project.result!;
  const catalog = new Map(result.functions.map(f => [f.id, f]));
  const transitions = result.findings.filter(f => !["duplication", "conflict"].includes(f.kind));
  const visible = transitions.filter(f => (filter === "all" || f.kind === filter) && (f.title + " " + [...f.before_ids, ...f.after_ids].map(id => { const item = catalog.get(id); return item ? item.owner + " " + functionText(item) + " " + item.scope : ""; }).join(" ")).toLowerCase().includes(search.toLowerCase()));
  return <section className="panel comparison-panel"><div className="panel-heading"><div className="heading-with-icon"><span className="section-icon"><GitCompareArrows size={21} /></span><div><h2>Карта судьбы функций</h2><p>Каждая строка — отдельное сопоставление из анализа</p></div></div><span className="count-label">{visible.length} из {transitions.length}</span></div>
    <div className="filter-row"><label className="search-field"><Search size={17} /><input aria-label="Поиск в сравнении" placeholder="Функция, подразделение или область ответственности" value={search} onChange={e => setSearch(e.target.value)} /></label><select aria-label="Статус сопоставления" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Все изменения</option>{Object.entries(labels).filter(([key]) => !["duplication", "conflict"].includes(key)).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></div>
    <div className="comparison-header"><span>До · владелец и функция</span><span>Изменение</span><span>После · владелец и функция</span><span>Проверка</span></div>
    <div className="comparison-rows">{visible.map((finding, index) => <article className="comparison-row animate-row" style={{ animationDelay: Math.min(index, 8) * 25 + "ms" }} key={finding.id}>
      <FunctionCell ids={finding.before_ids} catalog={catalog} side="before" />
      <div className="comparison-status"><Badge kind={finding.kind} /><ArrowRight size={17} /></div>
      <FunctionCell ids={finding.after_ids} catalog={catalog} side="after" />
      <div className="comparison-action"><span className={"review-state " + (project.reviews[finding.id]?.decision || "pending")}>{reviewLabels[project.reviews[finding.id]?.decision || "pending"]}</span><button className="button button-secondary" onClick={() => onSelect(finding)}><FileSearch size={16} />Источники<ArrowUpRight size={14} /></button><small>{finding.evidence.length} фрагментов</small></div>
    </article>)}</div>
    {!visible.length && <Empty title="Сопоставления не найдены" text="Измените запрос или выберите другой статус." />}
    <div className="panel-footnote">Потенциальная потеря означает отсутствие убедительного соответствия в загруженном комплекте. Проверьте источники перед принятием решения.</div>
  </section>;
}
