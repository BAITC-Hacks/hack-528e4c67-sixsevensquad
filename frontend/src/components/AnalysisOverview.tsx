import { ArrowRight, ArrowUpRight, ArrowRightLeft, Building2, CircleHelp, Copy, FileCheck2, FileWarning, ShieldAlert } from "lucide-react";
import type { Finding, Page, Project } from "../types";
import { findingTitle, isRisk, unitLabels } from "../lib";
import { Badge, Empty } from "./ui";

export default function AnalysisOverview({ project, onNavigate, onSelect }: { project: Project; onNavigate: (page: Page) => void; onSelect: (finding: Finding) => void }) {
  const result = project.result!;
  const risks = result.findings.filter(isRisk);
  const reviewed = result.findings.filter(f => project.reviews[f.id]?.decision && project.reviews[f.id].decision !== "pending").length;
  const cards = [
    { label: "Изменения структуры", value: result.unit_changes.length, icon: Building2, page: "structure" as Page, note: "подразделения и роли" },
    { label: "Переданные функции", value: result.counts.transferred || 0, icon: ArrowRightLeft, page: "map" as Page, note: "с новым владельцем" },
    { label: "Потенциальные потери", value: result.counts.not_found || 0, icon: FileWarning, page: "risks" as Page, note: "требуют проверки" },
    { label: "Возможные дубли", value: result.counts.duplication || 0, icon: Copy, page: "risks" as Page, note: "пересечения функций" },
    { label: "Возможные конфликты", value: result.counts.conflict || 0, icon: ShieldAlert, page: "risks" as Page, note: "зоны ответственности" },
  ];
  return <>
    <div className="coverage-banner"><span><FileCheck2 size={19} />Обработано {result.coverage.clauses_processed} фрагментов</span><span><b>{result.coverage.before_functions}</b> функций до <ArrowRight size={15} /><b>{result.coverage.after_functions}</b> после</span><span>{project.documents.length} документов</span></div>
    <div className="summary-grid">{cards.map(({ label, value, icon: Icon, page, note }, index) => <button className="summary-card animate-row" key={label} style={{ animationDelay: index * 45 + "ms" }} onClick={() => onNavigate(page)}><span className="summary-icon"><Icon size={21} strokeWidth={1.65} /></span><ArrowUpRight className="summary-arrow" size={16} /><strong>{value}</strong><span>{label}</span><small>{note}</small></button>)}</div>
    <div className="overview-columns"><section className="panel"><div className="panel-heading"><div><h2>Изменения подразделений</h2><p>Сохранённые, преобразованные и созданные</p></div><button className="icon-button" onClick={() => onNavigate("structure")} aria-label="Открыть структуру"><ArrowUpRight size={20} /></button></div><div className="unit-summary">{Object.entries(unitLabels).map(([kind, label]) => <button key={kind} onClick={() => onNavigate("structure")}><Badge kind={kind}>{label}</Badge><strong>{result.unit_changes.filter(u => u.status === kind).length}</strong><ArrowRight size={16} /></button>)}</div><button className="panel-bottom-link" onClick={() => onNavigate("map")}>Перейти к сравнению функций<ArrowRight size={16} /></button></section>
      <section className="panel"><div className="panel-heading"><div><h2>Очередь проверки</h2><p>Выводы с потенциальными рисками</p></div><span className="count-label">{risks.length}</span></div>{risks.slice(0, 3).map(finding => <button className="attention-item" key={finding.id} onClick={() => onSelect(finding)}><Badge kind={finding.kind} /><strong>{findingTitle(finding)}</strong><ArrowUpRight size={16} /></button>)}{!risks.length && <Empty title="Риски не выявлены" text="Проверьте полноту извлечения в реестре функций." />}<button className="panel-bottom-link" onClick={() => onNavigate("risks")}>Все риски<ArrowRight size={16} /></button></section></div>
    <section className="review-overview panel"><span className="section-icon"><FileCheck2 size={23} /></span><div><h3>Проверено {reviewed} из {result.findings.length} выводов</h3><p>Решения аналитика включаются в итоговое заключение.</p><div className="review-progress"><span style={{ width: (result.findings.length ? reviewed / result.findings.length * 100 : 0) + "%" }} /></div></div><button className="button button-secondary" onClick={() => onNavigate("report")}>Заключение<ArrowUpRight size={16} /></button></section>
    {!!result.counts.uncertain && <div className="uncertain-note"><CircleHelp size={18} /><span>Для {result.counts.uncertain} сопоставлений недостаточно данных. Они выделены отдельно и не включены в число потенциальных потерь.</span></div>}
  </>;
}
