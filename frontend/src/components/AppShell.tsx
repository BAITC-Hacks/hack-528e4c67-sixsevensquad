import { useState, type ReactNode } from "react";
import { ArrowUpRight, BookOpen, ChevronRight, CircleHelp, FileCheck2, FileSearch, FolderOpen, GitCompareArrows, History, LayoutDashboard, Menu, Network, ShieldAlert, X } from "lucide-react";
import type { Health, Page } from "../types";
import { Logo } from "./ui";

export const navigation = [
  { id: "documents", label: "Документы", icon: FolderOpen },
  { id: "overview", label: "Результаты анализа", icon: LayoutDashboard },
  { id: "structure", label: "Структура", icon: Network },
  { id: "map", label: "Сравнение функций", icon: GitCompareArrows },
  { id: "functions", label: "Все выводы и реестр", icon: FileSearch },
  { id: "risks", label: "Риски", icon: ShieldAlert },
  { id: "report", label: "Заключение", icon: FileCheck2 },
] as const;

export function AppShell({ children, page, onNavigate, health, connection, onRefresh, onHelp, pendingRisks }: {
  children: ReactNode; page: Page; onNavigate: (page: Page) => void; health: Health | null;
  connection: "checking" | "online" | "offline"; onRefresh: () => void; onHelp: () => void; pendingRisks: number;
}) {
  const [open, setOpen] = useState(false);
  const go = (next: Page) => { setOpen(false); onNavigate(next); };
  return <div className="app-shell">
    <a href="#main-content" className="skip-link">Перейти к содержимому</a>
    {open && <button className="sidebar-scrim" aria-label="Закрыть меню" onClick={() => setOpen(false)} />}
    <aside className={"sidebar " + (open ? "is-open" : "")}>
      <div className="sidebar-brand-row"><button className="brand-button" onClick={() => go("documents")} aria-label="ОргКонтур — документы"><Logo /></button><button className="icon-button mobile-close" onClick={() => setOpen(false)} aria-label="Закрыть навигацию"><X size={20} /></button></div>
      <div className="workspace-label"><span className="workspace-dot" />Рабочее пространство</div>
      <nav className="sidebar-nav" aria-label="Основная навигация">{navigation.map(({ id, label, icon: Icon }) => <button key={id} onClick={() => go(id)} aria-current={page === id ? "page" : undefined} className={page === id ? "active" : ""}><Icon size={19} strokeWidth={1.7} /><span>{label}</span>{id === "risks" && pendingRisks > 0 && <b className="nav-count">{pendingRisks}</b>}</button>)}</nav>
      <div className="sidebar-divider" /><button className={"history-nav " + (page === "history" ? "active" : "")} onClick={() => go("history")}><History size={19} strokeWidth={1.7} />История проектов</button>
      <div className="sidebar-bottom"><button className="sidebar-help" onClick={onHelp}><BookOpen size={18} /><span>Как провести анализ</span><ArrowUpRight size={15} /></button><div className="track-signature"><span className="track-monogram">КТ</span><div><strong>Казахтелеком</strong><small>Анализ реорганизации</small></div></div></div>
    </aside>
    <div className="app-body"><header className="topbar">
      <button className="icon-button mobile-menu" aria-label="Открыть меню" aria-expanded={open} onClick={() => setOpen(true)}><Menu size={21} /></button>
      <div className="breadcrumbs"><span>ОргКонтур</span><ChevronRight size={14} /><strong>{page === "history" ? "История проектов" : navigation.find(item => item.id === page)?.label}</strong></div>
      <div className="topbar-actions"><span className="engine-label">{health?.openai_configured ? "OpenAI · " + health.model : "OpenAI не подключён"}</span><button className={"connection-status " + connection} onClick={onRefresh} title="Обновить состояние API"><span />{connection === "checking" ? "Подключение…" : connection === "online" ? "API доступен" : "Нет соединения"}</button><button className="icon-button help-button" onClick={onHelp} aria-label="Помощь"><CircleHelp size={20} /></button></div>
    </header><main id="main-content" tabIndex={-1}>{children}</main></div>
  </div>;
}
