import type { Finding, FunctionRecord, Project } from "./types";

export const labels: Record<string, string> = {
  preserved: "Сохранена", transferred: "Передана", split: "Разделена", changed: "Изменена",
  uncertain: "Недостаточно данных", not_found: "Потенциальная потеря", new: "Без соответствия до",
  duplication: "Возможное дублирование", conflict: "Возможный конфликт",
};
export const unitLabels: Record<string, string> = { preserved: "Сохранено", reorganized: "Преобразовано", created: "Создано", not_found: "Не найдено после" };
export const statusLabels: Record<string, string> = { ready: "Готов к анализу", running: "В работе", completed: "Завершён", failed: "Нужна проверка" };
export const reviewLabels = { pending: "Не проверено", confirmed: "Подтверждено", rejected: "Отклонено" };
export const counted = (n: number, one: string, few: string, many: string) => n + " " + (n % 100 >= 11 && n % 100 <= 14 ? many : n % 10 === 1 ? one : n % 10 >= 2 && n % 10 <= 4 ? few : many);
export const isRisk = (finding: Finding) => ["not_found", "duplication", "conflict", "uncertain"].includes(finding.kind);
export const functionText = (item: FunctionRecord) => item.action === item.object ? item.action : item.action + " — " + item.object;
export const findingTitle = (item: Finding) => {
  const parts = item.title.split(" — ");
  return parts.length === 2 && parts[0] === parts[1] ? parts[0] : item.title;
};
export const dateLabel = (value: string) => new Intl.DateTimeFormat("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
export const ownersFor = (ids: string[], functions: FunctionRecord[]) =>
  [...new Set(ids.map(id => functions.find(item => item.id === id)?.owner).filter(Boolean))].join(", ");
export const projectName = (project: Project | null) => {
  if (!project) return "Новый анализ";
  const name = project.documents.find(d => d.side === "before")?.name;
  return name ? name.replace(/\.[^.]+$/, "").replaceAll("_", " ") : "Анализ документов";
};

export async function api<T>(url: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(url, { ...options, signal: options?.signal ?? AbortSignal.timeout(45000) }); }
  catch { throw new Error("Не удалось связаться с сервером. Проверьте подключение и повторите попытку."); }
  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("json") ? await response.json() : null;
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Сервис временно недоступен. Попробуйте ещё раз.");
  if (data === null) throw new Error("Сервер вернул неожиданный ответ. Проверьте подключение сервиса.");
  return data as T;
}

