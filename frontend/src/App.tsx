import { useEffect, useState } from "react";
import { ArrowRight, ArrowUpRight, CheckCircle2, Clock3, FileCheck2, FileText, FolderOpen, GitCompareArrows, History, Info, LoaderCircle, Plus, RefreshCw, Search, ShieldCheck, Sparkles, UploadCloud, X } from "lucide-react";
import type { Evidence, Finding, Page } from "./types";
import { dateLabel, isRisk, projectName, statusLabels } from "./lib";
import { useAnalysis } from "./hooks/useAnalysis";
import { AppShell } from "./components/AppShell";
import { Badge, Empty, EvidenceModal, Modal } from "./components/ui";
import { DocumentLibrary, UploadWorkspace } from "./components/Documents";
import AnalysisOverview from "./components/AnalysisOverview";
import Comparison from "./components/Comparison";
import FindingDetails from "./components/FindingDetails";
import { ExportMenu, FindingsRegistry, Report, Risks, Structure } from "./components/Results";

const copy: Record<Page, { title: string; text: string }> = {
  documents: { title: "Документы для анализа", text: "Загрузите организационные структуры, положения и инструкции до и после реорганизации." },
  overview: { title: "Результаты анализа", text: "Изменения подразделений, сопоставления функций и выводы, требующие проверки." },
  structure: { title: "Изменения структуры", text: "Сохранённые, преобразованные и созданные подразделения с основаниями из документов." },
  map: { title: "Сравнение функций", text: "Исходная функция, её новый владелец и точная формулировка в новой редакции." },
  functions: { title: "Все выводы и реестр", text: "Проверка сопоставлений и полного списка извлечённых функций с источниками." },
  risks: { title: "Риски и отклонения", text: "Потенциальные потери, дублирование, конфликты интересов и недостаток данных." },
  report: { title: "Аналитическое заключение", text: "Выводы системы, подтверждающие пункты, рекомендации и решения аналитика." },
  history: { title: "История проектов", text: "Документы, результаты сравнения и сохранённые решения." },
};

export default function App() {
  const analysis = useAnalysis();
  const { page, project, health, busy, connection } = analysis;
  const [before, setBefore] = useState<File[]>([]);
  const [after, setAfter] = useState<File[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [help, setHelp] = useState(false);
  const [historySearch, setHistorySearch] = useState("");
  const result = project?.result;
  const selected = result?.findings.find(f => f.id === selectedId);
  const pendingRisks = result?.findings.filter(f => isRisk(f) && (!project?.reviews[f.id] || project.reviews[f.id].decision === "pending")).length || 0;
  useEffect(() => { setSelectedId(null); setEvidence(null); }, [project?.id]);

  function newProject() { setBefore([]); setAfter([]); setSelectedId(null); setEvidence(null); analysis.newProject(); }
  function selectFinding(finding: Finding) { analysis.setReviewError(""); setSelectedId(finding.id); }
  async function upload() { if (await analysis.upload(before, after)) { setBefore([]); setAfter([]); } }
  const visibleHistory = analysis.history.filter(p => (dateLabel(p.created) + " " + (statusLabels[p.status] || p.status) + " " + p.id).toLowerCase().includes(historySearch.toLowerCase()));

  return <AppShell page={page} onNavigate={analysis.navigate} health={health} connection={connection} pendingRisks={pendingRisks} onRefresh={() => { void analysis.refreshConnection(); void analysis.loadHistory(); }} onHelp={() => setHelp(true)}>
    <div className="page-heading"><div><div className="page-eyebrow">АНАЛИЗ ОРГАНИЗАЦИОННЫХ ИЗМЕНЕНИЙ</div><h1>{copy[page].title}</h1><p>{copy[page].text}</p></div><div className="heading-actions">{project?.result && <ExportMenu project={project} />}<button className="button button-primary" onClick={newProject}><Plus size={17} /><span>Новый анализ</span></button></div></div>

    <section className="project-toolbar" aria-label="Текущий проект"><div className="current-project"><span className="project-symbol"><FolderOpen size={20} /></span><div><strong>{project ? projectName(project) : "Новый комплект документов"}</strong><small>{project ? project.stage : "Выберите две редакции для сравнения"}</small></div>{project && <Badge kind={project.status}>{statusLabels[project.status] || project.status}</Badge>}</div><label className="project-picker"><History size={16} /><select aria-label="Открыть проект" value={project?.id || ""} disabled={busy} onChange={e => e.target.value && void analysis.openProject(e.target.value)}><option value="">История проектов</option>{analysis.history.map(p => <option key={p.id} value={p.id}>{dateLabel(p.created)} · {statusLabels[p.status] || p.status} · {p.id.slice(0, 6)}</option>)}</select></label></section>

    {analysis.error && <div className="alert alert-error" role="alert"><Info size={19} /><span>{analysis.error}</span><button className="icon-button" onClick={() => analysis.setError("")} aria-label="Скрыть ошибку"><X size={17} /></button></div>}
    {connection === "offline" && <div className="alert alert-info" role="status"><Info size={18} /><span>Нет соединения с API. Проверьте, что сервис проекта запущен.</span><button className="text-button" onClick={analysis.refreshConnection}><RefreshCw size={15} />Повторить</button></div>}
    {connection === "online" && !health?.openai_configured && !result && <div className="connection-note"><Info size={17} /><span>API доступен. Для запуска ИИ-анализа требуется подключение OpenAI на сервере.</span><button className="text-button" onClick={analysis.refreshConnection}>Проверить<RefreshCw size={14} /></button></div>}

    {project && ["documents", "overview"].includes(page) && <div className="project-workflow"><span className="complete"><CheckCircle2 size={17} />Документы загружены</span><i /><span className={result ? "complete" : project.status === "running" ? "current" : ""}><GitCompareArrows size={17} />Сравнение функций</span><i /><span className={result ? "current" : ""}><FileCheck2 size={17} />Проверка заключения</span></div>}
    {project && ["ready", "failed"].includes(project.status) && page !== "history" && <section className="analysis-ready"><span className="ready-icon"><Sparkles size={23} /></span><div><h3>{project.status === "failed" ? "Повторить анализ комплекта" : "Комплект готов к анализу"}</h3><p>OpenAI сопоставит подразделения и функции и вернёт выводы с источниками.</p></div><button className="button button-primary" disabled={busy || connection === "offline"} onClick={analysis.startAnalysis}>{busy ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}{project.status === "failed" ? "Повторить анализ" : "Начать анализ"}</button></section>}
    {project?.status === "running" && page !== "history" && <section className="analysis-progress" role="status"><span className="analysis-orbit"><LoaderCircle className="spin" size={25} /></span><div><strong>Анализ выполняется</strong><p>{project.stage}</p></div><div className="progress-dots" aria-hidden="true"><i /><i /><i /></div></section>}

    <div className="page-transition" key={page}>
      {page === "documents" && (project ? <DocumentLibrary project={project} onNew={newProject} /> : <>
        <UploadWorkspace before={before} after={after} setBefore={setBefore} setAfter={setAfter} onSubmit={upload} onError={analysis.setError} busy={busy} />
        <section className="sample-section"><div><span className="overline">КОНТРОЛЬНЫЕ ДОКУМЕНТЫ</span><h3>Проверить на готовом комплекте</h3><p>Примеры загружаются с сервера и проходят тот же анализ, что и ваши файлы.</p></div><div><button className="button button-secondary" disabled={busy || connection === "offline"} onClick={() => void analysis.loadSample("control")}><FileText size={17} />Контрольный пример</button><button className="button button-secondary" disabled={busy || connection === "offline"} onClick={() => void analysis.loadSample("organizer")}><GitCompareArrows size={17} />Пример №8 → №9</button></div></section>
      </>)}
      {page === "overview" && project && result && <AnalysisOverview project={project} onNavigate={analysis.navigate} onSelect={selectFinding} />}
      {page === "map" && project && result && <Comparison key={project.id} project={project} onSelect={selectFinding} />}
      {page === "functions" && project && result && <FindingsRegistry key={project.id} project={project} onSelect={selectFinding} onSource={setEvidence} />}
      {page === "structure" && project && result && <Structure key={project.id} project={project} onSource={setEvidence} />}
      {page === "risks" && project && result && <Risks key={project.id} project={project} onSelect={selectFinding} />}
      {page === "report" && project && result && <Report project={project} />}
      {!result && !["documents", "history"].includes(page) && <div className="panel"><Empty title={project?.status === "running" ? "Ожидаем результат анализа" : project ? "Результаты появятся после анализа" : "Загрузите документы для сравнения"} text={project ? "После завершения здесь будут доступны изменения структуры, функции, источники и заключение." : "Добавьте комплекты до и после реорганизации или выберите контрольный пример."}><button className="button button-primary" onClick={() => analysis.navigate("documents")}><UploadCloud size={17} />К документам</button></Empty></div>}
      {page === "history" && <section className="panel history-panel"><div className="panel-heading"><div><h2>Проекты <span className="count-label">{analysis.history.length}</span></h2><p>{health?.database === "memory" ? "Хранение в памяти — проекты доступны до перезапуска API" : "Сохранённые комплекты и результаты"}</p></div><label className="search-field"><Search size={17} /><input value={historySearch} onChange={e => setHistorySearch(e.target.value)} aria-label="Поиск в истории" placeholder="Дата, статус или номер" /></label><button className="icon-button" onClick={analysis.loadHistory} aria-label="Обновить историю"><RefreshCw size={17} /></button></div>{analysis.historyError && <div className="alert alert-info"><Info size={17} /><span>{analysis.historyError}</span><button className="text-button" onClick={analysis.loadHistory}>Повторить</button></div>}{visibleHistory.map(p => <button className="history-row" disabled={busy} key={p.id} onClick={() => void analysis.openProject(p.id)}><span className="history-icon"><FileText size={21} /></span><span><strong>Анализ документов <small>№{p.id.slice(0, 8)}</small></strong><span><Clock3 size={14} />{dateLabel(p.created)} · {p.stage}</span></span><Badge kind={p.status}>{statusLabels[p.status] || p.status}</Badge><ArrowUpRight size={18} /></button>)}{!analysis.history.length && !analysis.historyError && <Empty title="Пока нет проектов" text="Создайте первый анализ или загрузите контрольный комплект."><button className="button button-primary" onClick={newProject}><Plus size={17} />Новый анализ</button></Empty>}{analysis.history.length > 0 && !visibleHistory.length && <Empty title="Совпадений нет" text="Измените поисковый запрос." />}</section>}
    </div>
    <footer className="page-footer"><span><ShieldCheck size={15} />Выводы рекомендательные. Проверяйте источники.</span><span>ОргКонтур · Трек «Казахтелеком»</span></footer>
    {busy && <div className="request-indicator" role="status"><LoaderCircle className="spin" size={17} />Обрабатываем запрос…</div>}
    {analysis.notice && <div className="toast" role="status"><CheckCircle2 size={19} /><span>{analysis.notice}</span><button className="icon-button" onClick={() => analysis.setNotice("")} aria-label="Скрыть уведомление"><X size={16} /></button></div>}
    {selected && project && <FindingDetails key={project.id + selected.id} finding={selected} project={project} busy={analysis.reviewBusy} error={analysis.reviewError} onReview={analysis.saveReview} onSource={setEvidence} onClose={() => setSelectedId(null)} />}
    {evidence && <EvidenceModal evidence={evidence} onClose={() => setEvidence(null)} />}
    {help && <Modal title="Как провести анализ" onClose={() => setHelp(false)}><ol className="help-steps"><li><strong>Загрузите две редакции</strong><p>Оргструктуры, положения, инструкции и приложения в DOCX, PDF с текстовым слоем, XLSX или TXT. До 12 файлов суммарно, до 10 МБ каждый.</p></li><li><strong>Запустите сравнение</strong><p>Существующий сервис OpenAI извлечёт подразделения и функции, определит изменения и потенциальные риски. Текст документов передаётся провайдеру ИИ.</p></li><li><strong>Проверьте выводы</strong><p>Сравните точные формулировки, откройте пункты документов, изучите область поиска и сохраните решение с комментарием.</p></li><li><strong>Скачайте заключение</strong><p>Word, CSV, Markdown или JSON с результатами и решениями аналитика.</p></li></ol><button className="button button-primary help-done" onClick={() => setHelp(false)}>Понятно<ArrowRight size={16} /></button></Modal>}
  </AppShell>;
}
