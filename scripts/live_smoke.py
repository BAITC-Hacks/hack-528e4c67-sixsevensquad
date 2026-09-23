"""Small opt-in paid check: one durable project, at most $0.08 across reruns."""
import json
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import Settings
from backend.app.local_storage import LocalStore
from backend.app.parsers import parse_document
from backend.app.provider import OpenAIProvider
from backend.app.pipeline import analyze
from backend.app.storage import now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--control", action="store_true", help="Paid TZ control case, capped at $0.03")
    parser.add_argument("--refresh", action="store_true", help="Recheck a completed test using cached requests; retains spend limits")
    args = parser.parse_args()
    settings = Settings(kontur_budget_usd=.03 if args.control else .08, kontur_max_calls=8,
                        kontur_max_output_tokens=3000, kontur_request_timeout=45,
                        kontur_analysis_seconds=180)
    store = LocalStore(ROOT/"runtime"/("live-control" if args.control else "live-smoke"))
    store.initialize(); store.recover()
    existing = store.list()
    if existing:
        project = store.get(existing[0]["id"])
    elif args.control:
        project = store.create([parse_document(f"control-{side}.txt",
            (ROOT/"data"/"samples"/f"control-{side}.txt").read_bytes(),side,side)
            for side in ("before", "after")])
    else:
        before = """Положение о логистике. Редакция до изменений.
1.1. Отдел перевозок:
1.1.1. Ведёт реестр страхования грузов.
1.1.2. Проверяет сроки поверки складских весов.
1.2. Отдел закупок:
1.2.1. Утверждает договоры закупки упаковочных материалов.
"""
        after = """Положение о логистике. Редакция после изменений.
1.1. Центр доставки:
1.1.1. Ведёт реестр страхования грузов.
1.2. Отдел закупок:
1.2.1. Утверждает договоры закупки упаковочных материалов.
"""
        project = store.create([parse_document("логистика-до.txt",before.encode(),"before","before"),
                                parse_document("логистика-после.txt",after.encode(),"after","after")])
    pid = project["id"]
    if project["status"] == "completed" and not args.refresh:
        print(json.dumps({"status":"cached_completed","metrics":project.get("metrics")},ensure_ascii=False))
        if args.control:
            verify_control(project["result"])
        return
    if project["status"] == "completed":
        store.update(pid, status="ready", result=None)
    provider = OpenAIProvider(settings,cache_get=lambda key:store.cache_get(pid,key),
        cache_put=lambda key,value:store.cache_put(pid,key,value),metrics=project.get("metrics"),
        on_metrics=lambda metrics:store.update(pid,metrics=metrics))
    from backend.app.schemas import Document
    store.start(pid,"openai")
    try:
        result = analyze([Document.model_validate(d) for d in project["documents"]],provider,"openai",lambda stage:print(stage,flush=True))
        store.update(pid,status="completed",stage="Завершён",result=result,finished=now())
        print(json.dumps({"status":"completed","counts":result["counts"],"coverage":result["coverage"],
                          "warnings":result["warnings"],"metrics":provider.snapshot()},ensure_ascii=False),flush=True)
        if args.control:
            verify_control(result)
    except Exception as exc:
        # Never print provider response bodies or credentials.
        store.update(pid,status="failed",stage=type(exc).__name__,finished=now())
        print(json.dumps({"status":"failed","error_type":type(exc).__name__,"metrics":provider.snapshot()},ensure_ascii=False),flush=True)
        raise SystemExit(1)


def verify_control(result):
    """Acceptance assertions belong only in the test, never in the analyzer."""
    checks = {
        "reorganization": any(c["status"] == "reorganized" and
            "Отдел финансового контроля" in c["before_names"] and
            {"Отдел операционного аудита", "Отдел риск-контроля"} <= set(c["after_names"])
            for c in result["unit_changes"]),
        "loss": any(f["kind"] == "not_found" and "страхов" in f["title"].lower() for f in result["findings"]),
        "duplication": any(f["kind"] == "duplication" and "расход" in f["title"].lower() for f in result["findings"]),
        "conflict": any(f["kind"] == "conflict" and "закуп" in " ".join(e["quote"] for e in f["evidence"]).lower() for f in result["findings"]),
        "exact_sources": all(f["evidence"] and all(e["quote"] in e["text"] for e in f["evidence"]) for f in result["findings"]),
    }
    print(json.dumps({"acceptance_checks":checks}, ensure_ascii=False), flush=True)
    if not all(checks.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
