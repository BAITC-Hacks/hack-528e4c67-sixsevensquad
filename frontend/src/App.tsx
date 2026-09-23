import { ChangeEvent, DragEvent, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CheckCircle2,
  ChevronDown,
  Download,
  FileCheck2,
  FileSearch,
  FileText,
  GitCompareArrows,
  Layers3,
  Play,
  Plus,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";

type Evidence = { document: string; point: string; quote: string };
type Transition = {
  before: string;
  after: string;
  status: string;
  confidence: number;
  evidenceBefore: Evidence | null;
  evidenceAfter: Evidence | null;
};
type Finding = {
  type: string;
  severity: "high" | "medium" | "low";
  title: string;
  description: string;
  evidence: Evidence[];
  recommendation: string;
};
type FunctionMapItem = {
  before: string;
  after: string;
  status: string;
  confidence: number;
  beforeEvidence: Evidence;
  afterEvidence: Evidence | null;
};
type Analysis = {
  summary: {
    preserved: number;
    created: number;
    transformed: number;
    removed: number;
    losses: number;
    risks: number;
  };
  transitions: Transition[];
  functionMap: FunctionMapItem[];
  findings: Finding[];
  note: string;
  engine: string;
};

const ACCEPT = ".pdf,.docx,.xlsx,.xlsm,.txt,.md";

const demoBefore = `ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ (редакция №8)
3.4. Блок внутреннего аудита состоит из следующих структурных подразделений: Департамент непрерывного мониторинга системы внутреннего контроля (ДНМ). Департамент контроля качества аудита и методологии (ДККМ).
3.5. Главному аудитору подчиняется Директор направления внутреннего аудита.
5.3. Директор направления внутреннего аудита организует плановые и внеплановые проверки, формирует график проведения проверки и контролирует устранение выявленных недостатков.
5.4. Директор ДНМ осуществляет непрерывный мониторинг системы внутреннего контроля и анализирует результаты непрерывного аудита.
5.5. Директор ДККМ организует контроль качества аудита, разрабатывает методические материалы и формирует план работ.`;

const demoAfter = `ПОЛОЖЕНИЕ О ВНУТРЕННЕМ АУДИТЕ (редакция №9)
3.4. Блок внутреннего аудита состоит из следующих структурных подразделений: Департамент ИТ-аудита и анализа данных (ДИТААД). Департамент операционного аудита (ДОА). Департамент непрерывного мониторинга системы внутреннего контроля (ДНМ). Департамент контроля качества аудита и методологии (ДККМ).
4.4. Главный аудитор может участвовать в органах управления подконтрольных обществ, предусмотрев меры для сохранения независимости и раскрытие потенциального конфликта интересов.
5.3. Директоры ДИТААД и ДОА организуют плановые и внеплановые проверки, формируют график и контролируют устранение выявленных недостатков. ДИТААД проводит аудит ИТ-систем, информационной безопасности, персональных данных и анализ данных. ДОА проводит аудит операционных и поддерживающих процессов.
5.4. Директор ДНМ осуществляет непрерывный мониторинг системы внутреннего контроля и анализирует результаты непрерывного аудита.
5.5. Директор ДККМ организует контроль качества аудита, разрабатывает методические материалы и формирует план работ.`;

function FileDrop({
  title,
  hint,
  files,
  onFiles,
}: {
  title: string;
  hint: string;
  files: File[];
  onFiles: (files: File[]) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const addFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    onFiles([...files, ...Array.from(incoming)]);
  };
  const onDrop = (event: DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  };
  return (
    <section className="upload-card">
      <div className="upload-heading">
        <span className="version-dot" />
        <div><h3>{title}</h3><p>{hint}</p></div>
      </div>
      <label
        className={`dropzone ${dragging ? "dragging" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input type="file" multiple accept={ACCEPT} onChange={(event: ChangeEvent<HTMLInputElement>) => addFiles(event.target.files)} />
        <UploadCloud size={24} />
        <strong>Перетащите документы</strong>
        <span>или нажмите для выбора</span>
        <small>PDF, DOCX, XLSX, TXT · до 20 МБ</small>
      </label>
      <div className="file-list">
        {files.map((file, index) => (
          <div className="file-row" key={`${file.name}-${index}`}>
            <FileText size={17} />
            <span><b>{file.name}</b><small>{Math.max(1, Math.round(file.size / 1024))} КБ</small></span>
            <button aria-label={`Удалить ${file.name}`} onClick={() => onFiles(files.filter((_, current) => current !== index))}><X size={16} /></button>
          </div>
        ))}
      </div>
    </section>
  );
}

function EvidenceBlock({ evidence }: { evidence: Evidence }) {
  return (
    <details className="evidence">
      <summary><FileSearch size={15} /> {evidence.document} · пункт {evidence.point} <ChevronDown size={15} /></summary>
      <blockquote>{evidence.quote}</blockquote>
    </details>
  );
}

function App() {
  const [beforeFiles, setBeforeFiles] = useState<File[]>([]);
  const [afterFiles, setAfterFiles] = useState<File[]>([]);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"structure" | "functions" | "risks">("structure");

  const totalFiles = beforeFiles.length + afterFiles.length;
  const canAnalyze = beforeFiles.length > 0 && afterFiles.length > 0 && !loading;
  const seriousRisks = useMemo(() => analysis?.findings.filter((item) => item.severity === "high").length ?? 0, [analysis]);

  const loadDemo = () => {
    setBeforeFiles([new File([demoBefore], "Положение_редакция_8.txt", { type: "text/plain" })]);
    setAfterFiles([new File([demoAfter], "Положение_редакция_9.txt", { type: "text/plain" })]);
    setAnalysis(null);
    setError("");
  };

  const runAnalysis = async () => {
    if (!canAnalyze) return;
    setLoading(true);
    setError("");
    const form = new FormData();
    beforeFiles.forEach((file) => form.append("before", file));
    afterFiles.forEach((file) => form.append("after", file));
    try {
      const response = await fetch("/api/analyze", { method: "POST", body: form });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Не удалось выполнить анализ");
      setAnalysis(payload);
      setTab("structure");
      requestAnimationFrame(() => document.getElementById("results")?.scrollIntoView({ behavior: "smooth" }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Сервис анализа недоступен");
    } finally {
      setLoading(false);
    }
  };

  const exportReport = () => {
    if (!analysis) return;
    const blob = new Blob([JSON.stringify(analysis, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "orgkontur-report.json";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark"><Layers3 size={20} /></span><span>ОргКонтур<small>Анализ реорганизации</small></span></a>
        <div className="engine-status"><span /> Анализ по правилам <b>ИИ подключим позже</b></div>
      </header>

      <main id="top">
        <section className="intro">
          <div><span className="eyebrow"><Sparkles size={14} /> Новый анализ</span><h1>Сравните структуру и функции<br />до и после реорганизации</h1><p>Загрузите два комплекта документов. Сервис найдёт изменения, возможные потери функций, дублирование и конфликты интересов.</p></div>
          <button className="ghost-button" onClick={loadDemo}><Play size={17} /> Загрузить демо</button>
        </section>

        <section className="workflow-card">
          <div className="steps">
            <span className="active"><b>1</b> Документы</span><i /><span><b>2</b> Сравнение</span><i /><span><b>3</b> Заключение</span>
          </div>
          <div className="upload-grid">
            <FileDrop title="До реорганизации" hint="Действующая структура и положения" files={beforeFiles} onFiles={setBeforeFiles} />
            <div className="compare-icon"><GitCompareArrows size={20} /></div>
            <FileDrop title="После реорганизации" hint="Новая структура и документы" files={afterFiles} onFiles={setAfterFiles} />
          </div>
          {error && <div className="error-banner"><AlertTriangle size={18} /><span>{error}</span></div>}
          <div className="action-row">
            <span>{totalFiles ? `Выбрано документов: ${totalFiles}` : "Добавьте минимум по одному документу в каждый комплект"}</span>
            <button className="primary-button" disabled={!canAnalyze} onClick={runAnalysis}>
              {loading ? <><RefreshCw className="spin" size={18} /> Анализируем документы…</> : <><FileSearch size={18} /> Начать анализ</>}
            </button>
          </div>
        </section>

        {!analysis && (
          <section className="capabilities">
            <div><Building2 /><h3>Структура</h3><p>Созданные, сохранённые, преобразованные и упразднённые подразделения.</p></div>
            <div><GitCompareArrows /><h3>Функции</h3><p>Карта перехода функций и потенциальные потери ответственности.</p></div>
            <div><ShieldAlert /><h3>Риски</h3><p>Дублирование, конфликт интересов и ссылки на подтверждающие пункты.</p></div>
          </section>
        )}

        {analysis && (
          <section className="results" id="results">
            <div className="results-head">
              <div><span className="eyebrow"><CheckCircle2 size={14} /> Анализ завершён</span><h2>Результаты сравнения</h2><p>{analysis.note}</p></div>
              <button className="ghost-button" onClick={exportReport}><Download size={17} /> Скачать отчёт</button>
            </div>
            <div className="metrics">
              <div><span>Сохранено</span><strong>{analysis.summary.preserved}</strong><small>подразделений</small></div>
              <div><span>Создано</span><strong>{analysis.summary.created}</strong><small>подразделений</small></div>
              <div><span>Преобразовано</span><strong>{analysis.summary.transformed}</strong><small>подразделений</small></div>
              <div className={analysis.summary.losses ? "danger" : ""}><span>Возможные потери</span><strong>{analysis.summary.losses}</strong><small>функций</small></div>
              <div className={seriousRisks ? "warning" : ""}><span>Риски</span><strong>{analysis.summary.risks}</strong><small>требуют проверки</small></div>
            </div>

            <div className="tabs" role="tablist">
              <button className={tab === "structure" ? "active" : ""} onClick={() => setTab("structure")}><Building2 size={17} /> Структура <b>{analysis.transitions.length}</b></button>
              <button className={tab === "functions" ? "active" : ""} onClick={() => setTab("functions")}><GitCompareArrows size={17} /> Функции <b>{analysis.functionMap.length}</b></button>
              <button className={tab === "risks" ? "active" : ""} onClick={() => setTab("risks")}><ShieldAlert size={17} /> Риски <b>{analysis.findings.length}</b></button>
            </div>

            {tab === "structure" && <div className="panel"><div className="table-head"><span>До</span><span>Изменение</span><span>После</span><span>Уверенность</span></div>{analysis.transitions.length ? analysis.transitions.map((item, index) => <article className="transition" key={`${item.before}-${item.after}-${index}`}><div><strong>{item.before}</strong>{item.evidenceBefore && <EvidenceBlock evidence={item.evidenceBefore} />}</div><div className={`status status-${item.status.toLowerCase()}`}>{item.status}<ArrowRight size={15} /></div><div><strong>{item.after}</strong>{item.evidenceAfter && <EvidenceBlock evidence={item.evidenceAfter} />}</div><div className="confidence"><b>{item.confidence}%</b><span><i style={{ width: `${item.confidence}%` }} /></span></div></article>) : <Empty text="Подразделения не распознаны. Проверьте качество текста документов." />}</div>}

            {tab === "functions" && <div className="panel function-panel">{analysis.functionMap.length ? analysis.functionMap.map((item, index) => <article className="function-row" key={index}><div className="function-number">{String(index + 1).padStart(2, "0")}</div><div><small>Функция до</small><p>{item.before}</p><EvidenceBlock evidence={item.beforeEvidence} /></div><ArrowRight className="function-arrow" size={18} /><div><small>Функция после</small><p>{item.after}</p>{item.afterEvidence && <EvidenceBlock evidence={item.afterEvidence} />}</div><span className={`pill ${item.status.includes("потер") ? "pill-danger" : ""}`}>{item.status} · {item.confidence}%</span></article>) : <Empty text="Функции не найдены в загруженных документах." />}</div>}

            {tab === "risks" && <div className="risk-grid">{analysis.findings.length ? analysis.findings.map((item, index) => <article className={`risk-card severity-${item.severity}`} key={index}><div className="risk-top"><span><AlertTriangle size={18} /></span><div><small>{item.type}</small><h3>{item.title}</h3></div><b>{item.severity === "high" ? "Высокий" : item.severity === "medium" ? "Средний" : "Низкий"}</b></div><p>{item.description}</p><div className="recommendation"><FileCheck2 size={17} /><span><small>Рекомендация</small>{item.recommendation}</span></div>{item.evidence.map((evidence, evidenceIndex) => <EvidenceBlock evidence={evidence} key={evidenceIndex} />)}</article>) : <div className="clean-state"><CheckCircle2 size={28} /><h3>Явные риски не найдены</h3><p>Это предварительный результат. Перед утверждением структуры проверьте выводы вручную.</p></div>}</div>}
          </section>
        )}
      </main>
      <footer><span>ОргКонтур · MVP без ИИ</span><span>Результаты требуют экспертной проверки</span></footer>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty"><FileSearch size={28} /><p>{text}</p></div>;
}

export default App;

