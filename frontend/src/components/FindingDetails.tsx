import { useState } from "react";
import { CheckCheck, CheckCircle2, FileSearch, Info, Lightbulb, LoaderCircle, Save, SearchCheck } from "lucide-react";
import type { Evidence, Finding, Project, Review } from "../types";
import { findingTitle, functionText, reviewLabels } from "../lib";
import { Badge, Modal, SourceCard } from "./ui";

export default function FindingDetails({ finding, project, busy, error, onReview, onSource, onClose }: {
  finding: Finding; project: Project; busy: boolean; error: string;
  onReview: (id: string, review: Review) => Promise<boolean>; onSource: (e: Evidence) => void; onClose: () => void;
}) {
  const existing = project.reviews[finding.id];
  const [decision, setDecision] = useState<Review["decision"]>(existing?.decision || "pending");
  const [comment, setComment] = useState(existing?.comment || "");
  const [saved, setSaved] = useState(false);
  const scope = finding.search_scope;
  const functions = project.result!.functions;
  return <Modal title="Проверка вывода" wide onClose={onClose}>
    <div className="finding-detail-heading"><Badge kind={finding.kind} /><span>{reviewLabels[existing?.decision || "pending"]}</span></div>
    <h3 className="finding-detail-title">{findingTitle(finding)}</h3>
    <p className="finding-detail-explanation">{finding.explanation}</p>
    <div className="detail-recommendation"><Lightbulb size={19} /><div><strong>Рекомендация</strong><p>{finding.recommendation}</p></div></div>
    <div className="evidence-comparison">{(["before", "after"] as const).map(side => {
      const records = (side === "before" ? finding.before_ids : finding.after_ids).map(id => functions.find(f => f.id === id)).filter(Boolean);
      const evidence = finding.evidence.filter(e => e.side === side);
      return <section key={side}><h4><span className={"side-label " + side}>{side === "before" ? "До" : "После"}</span>{side === "before" ? "Исходная редакция" : "Новая редакция"}</h4>
        {records.map(record => <div className="detail-function" key={record!.id}><strong>{record!.owner}</strong><p>{functionText(record!)}</p><small>Область ответственности: {record!.scope}</small></div>)}
        {evidence.map((e, index) => <SourceCard key={e.clause_id + index} item={e} onOpen={onSource} />)}
        {!evidence.length && <div className="evidence-absence"><FileSearch size={20} /><p>{side === "after" && finding.before_ids.length ? "Убедительное соответствие не установлено в загруженном комплекте. Это не доказывает исчезновение функции." : "Для этого вывода нет источника из данной редакции."}</p></div>}
      </section>;
    })}</div>
    {finding.evidence_check && <div className="verification-note"><CheckCheck size={18} /><div><strong>{finding.evidence_check.exact_quotes ? "Сервер проверил дословные цитаты" : "Цитаты требуют дополнительной проверки"}</strong><p>Наличие точной цитаты подтверждает источник. Правильность смыслового вывода проверяет аналитик.</p></div></div>}
    {scope && <details className="search-scope-detail" open><summary><SearchCheck size={18} />Область поиска соответствий<span>{scope.catalog_size} функций</span></summary><div><p><strong>Документы:</strong> {scope.documents.join(", ") || "—"}</p><p><strong>Владельцы:</strong> {scope.owners?.join(", ") || "Не указаны"}</p>{!!scope.candidates?.length && <><h4>Ближайшие формулировки для ручной проверки</h4><ul>{scope.candidates.map(candidate => <li key={candidate.id}><strong>{candidate.owner}</strong><p>{candidate.action}{candidate.object !== candidate.action ? " — " + candidate.object : ""}</p></li>)}</ul></>}{scope.note && <p className="scope-note">{scope.note}</p>}</div></details>}
    <form className="decision-form" onSubmit={async event => { event.preventDefault(); setSaved(await onReview(finding.id, { decision, comment })); }}>
      <div><h4>Решение аналитика</h4><p>Решение и комментарий сохранятся в проекте и заключении.</p></div>
      <div className="decision-inputs"><label>Статус проверки<select value={decision} disabled={busy} onChange={e => { setDecision(e.target.value as Review["decision"]); setSaved(false); }}><option value="pending">Требует проверки</option><option value="confirmed">Подтверждено</option><option value="rejected">Отклонено</option></select></label><label>Комментарий<textarea value={comment} maxLength={3000} rows={3} disabled={busy} onChange={e => { setComment(e.target.value); setSaved(false); }} placeholder="На каких пунктах основано решение" /></label></div>
      {error && <p className="inline-error" role="alert">{error}</p>}
      <div className="decision-footer"><span role="status">{saved ? <><CheckCircle2 size={17} />Решение сохранено</> : <><Info size={16} />Выводы требуют проверки человеком</>}</span><button className="button button-primary" type="submit" disabled={busy}>{busy ? <LoaderCircle size={17} className="spin" /> : <Save size={17} />}{busy ? "Сохраняем…" : "Сохранить решение"}</button></div>
    </form>
  </Modal>;
}
