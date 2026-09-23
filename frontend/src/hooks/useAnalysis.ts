import { useEffect, useRef, useState } from "react";
import { api } from "../lib";
import type { Health, Page, Project, ProjectSummary, Review } from "../types";

const pages: Page[] = ["overview", "documents", "map", "functions", "structure", "risks", "report", "history"];
const message = (error: unknown) => error instanceof Error ? error.message : "Не удалось выполнить действие. Повторите попытку.";

/** The existing FastAPI contract is the only source of projects and results. */
export function useAnalysis() {
  const [page, setPage] = useState<Page>("documents");
  const [project, setProject] = useState<Project | null>(null);
  const [history, setHistory] = useState<ProjectSummary[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [connection, setConnection] = useState<"checking" | "online" | "offline">("checking");
  const [busy, setBusy] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [notice, setNotice] = useState("");
  const [restored, setRestored] = useState(false);
  const generation = useRef(0);

  async function loadHistory() {
    try { setHistory(await api<ProjectSummary[]>("/api/projects")); setHistoryError(""); }
    catch (e) { setHistoryError(message(e)); }
  }
  async function refreshConnection() {
    setConnection("checking");
    try {
      const next = await api<Health>("/api/health", { signal: AbortSignal.timeout(8000) });
      setHealth(next); setConnection(["memory", "connected"].includes(next.database) ? "online" : "offline");
    } catch { setHealth(null); setConnection("offline"); }
  }
  function navigate(next: Page) {
    setPage(next);
    if (next === "history") void loadHistory();
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function applyProject(next: Project, nextPage?: Page) {
    setProject(next);
    setError(next.status === "failed" ? next.error || "Анализ завершился с ошибкой." : "");
    if (nextPage) navigate(nextPage);
  }
  async function openProject(id: string, preferredPage?: Page) {
    const version = ++generation.current;
    setBusy(true); setError(""); setReviewError("");
    try {
      const next = await api<Project>("/api/projects/" + encodeURIComponent(id));
      if (version === generation.current) applyProject(next, preferredPage || (next.result ? "overview" : "documents"));
    } catch (e) { if (version === generation.current) setError(message(e)); }
    finally { if (version === generation.current) setBusy(false); }
  }
  function newProject() {
    generation.current++; setProject(null); setBusy(false); setError(""); setReviewError(""); navigate("documents");
  }
  async function createProject(url: string, body?: FormData) {
    const version = ++generation.current;
    setBusy(true); setError("");
    let createdId: string | undefined;
    try {
      const created = await api<{ id: string }>(url, { method: "POST", body });
      createdId = created.id;
      const next = await api<Project>("/api/projects/" + created.id);
      if (version === generation.current) {
        applyProject(next, "documents"); setNotice("Документы загружены. Можно запускать анализ.");
        void loadHistory(); return true;
      }
    } catch (e) {
      if (version === generation.current) {
        setError(createdId ? "Комплект сохранён, но получить его не удалось. Откройте проект в истории." : message(e));
        void loadHistory();
      }
    } finally { if (version === generation.current) setBusy(false); }
    return false;
  }
  async function upload(before: File[], after: File[]) {
    if (!before.length || !after.length) { setError("Добавьте документы в обе редакции."); return false; }
    const form = new FormData();
    before.forEach(file => form.append("before", file)); after.forEach(file => form.append("after", file));
    return createProject("/api/projects", form);
  }
  const loadSample = (kind: "control" | "organizer") => createProject("/api/projects/sample?kind=" + kind);
  async function startAnalysis() {
    if (!project || project.status === "running") return;
    const id = project.id, version = generation.current;
    setBusy(true); setError("");
    try {
      await api("/api/projects/" + id + "/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: "openai" }) });
      if (version === generation.current) {
        setProject(current => current?.id === id ? { ...current, status: "running", stage: "Подготовка анализа", error: undefined } : current);
      }
    } catch (e) { if (version === generation.current) { setError(message(e)); void refreshConnection(); } }
    finally { if (version === generation.current) setBusy(false); }
  }
  async function saveReview(findingId: string, review: Review) {
    if (!project) return false;
    const id = project.id, version = generation.current;
    setReviewBusy(true); setReviewError("");
    try {
      await api("/api/projects/" + id + "/findings/" + findingId + "/review", {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(review),
      });
      const next = await api<Project>("/api/projects/" + id);
      if (version === generation.current) { setProject(next); setNotice("Решение сохранено и включено в заключение."); return true; }
    } catch (e) { if (version === generation.current) setReviewError(message(e)); }
    finally { setReviewBusy(false); }
    return false;
  }

  useEffect(() => {
    void refreshConnection(); void loadHistory();
    const params = new URLSearchParams(window.location.search);
    const id = params.get("project"), requestedPage = params.get("view") as Page;
    if (id) void openProject(id, pages.includes(requestedPage) ? requestedPage : undefined).finally(() => setRestored(true));
    else { if (pages.includes(requestedPage)) setPage(requestedPage); setRestored(true); }
  }, []);
  useEffect(() => {
    if (!restored) return;
    const url = new URL(window.location.href);
    if (project) url.searchParams.set("project", project.id); else url.searchParams.delete("project");
    url.searchParams.set("view", page);
    window.history.replaceState(null, "", url);
  }, [project?.id, page, restored]);
  useEffect(() => {
    if (!project || project.status !== "running") return;
    const id = project.id, version = generation.current;
    let cancelled = false, timer = 0;
    async function poll() {
      try {
        const next = await api<Project>("/api/projects/" + id);
        if (cancelled || version !== generation.current) return;
        setProject(next); setError("");
        if (next.status === "completed") { navigate("overview"); setNotice("Анализ завершён. Проверьте выводы и источники."); void loadHistory(); return; }
        if (next.status === "failed") { setError(next.error || "Не удалось завершить анализ."); void loadHistory(); return; }
      } catch (e) { if (!cancelled && version === generation.current) setError(message(e)); }
      if (!cancelled) timer = window.setTimeout(poll, 1800);
    }
    timer = window.setTimeout(poll, 500);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [project?.id, project?.status]);
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(""), 5000); return () => clearTimeout(timer); }, [notice]);

  return { page, project, history, health, connection, busy, reviewBusy, error, reviewError, historyError, notice,
    navigate, newProject, openProject, upload, loadSample, startAnalysis, saveReview, loadHistory, refreshConnection,
    setError, setReviewError, setNotice };
}
