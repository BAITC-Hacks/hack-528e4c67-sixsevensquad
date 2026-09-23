export type Side = "before" | "after";
export type Evidence = { document: string; locator: string; quote: string; clause_id: string; side: Side; text: string };
export type Clause = Omit<Evidence, "quote" | "clause_id"> & { id: string };
export type DocumentRecord = { id?: string; name: string; side: Side; clauses: Clause[] };
export type FunctionRecord = { id: string; owner: string; action: string; object: string; scope: string; side: Side; evidence: { clause_id: string; quote: string }[] };
export type Finding = {
  id: string; kind: string; label: string; title: string; explanation: string; recommendation: string;
  before_ids: string[]; after_ids: string[]; evidence: Evidence[];
  evidence_check?: { exact_quotes: boolean; required_sides_present: boolean; interpretation: string };
  search_scope?: { documents: string[]; catalog_size: number; owners?: string[]; candidates?: { id: string; owner: string; action: string; object: string; lexical_score: number }[]; note?: string } | null;
};
export type UnitChange = { before_names: string[]; after_names: string[]; status: string; explanation: string; evidence: Evidence[] };
export type Review = { decision: "pending" | "confirmed" | "rejected"; comment: string };
export type AnalysisResult = {
  mode: string; report: string; counts: Record<string, number>;
  coverage: { before_functions: number; after_functions: number; clauses_processed: number };
  functions: FunctionRecord[]; findings: Finding[]; unit_changes: UnitChange[]; limitations: string[];
};
export type Project = { id: string; created: string; status: string; stage: string; error?: string; documents: DocumentRecord[]; result: AnalysisResult | null; reviews: Record<string, Review> };
export type ProjectSummary = Pick<Project, "id" | "created" | "status" | "stage">;
export type Health = { database: string; openai_configured: boolean; model: string };
export type Page = "overview" | "documents" | "map" | "functions" | "structure" | "risks" | "report" | "history";
