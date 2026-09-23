"""Paid verification of an existing local project; explicit project ID and budget."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.app.config import Settings
from backend.app.local_storage import LocalStore
from backend.app.pipeline import analyze
from backend.app.provider import OpenAIProvider
from backend.app.schemas import Document
from backend.app.storage import now


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_id")
    parser.add_argument("--budget",type=float,default=.15)
    args = parser.parse_args()
    settings = Settings(kontur_budget_usd=args.budget)
    store = LocalStore(settings.kontur_data_dir); store.initialize()
    project = store.get(args.project_id)
    if project["status"] == "completed":
        print(json.dumps({"status":"already_completed","metrics":project.get("metrics")},ensure_ascii=False)); return
    pid = project["id"]
    store.start(pid,"openai")
    provider = OpenAIProvider(settings,cache_get=lambda k:store.cache_get(pid,k),
        cache_put=lambda k,v:store.cache_put(pid,k,v),metrics=project.get("metrics"),
        on_metrics=lambda metrics:store.update(pid,metrics=metrics))
    def progress(stage):
        store.update(pid,stage=stage); print(stage,flush=True)
    try:
        result = analyze([Document.model_validate(d) for d in project["documents"]],provider,"openai",progress)
        store.update(pid,status="completed",stage="Анализ завершён с замечаниями" if result.get("warnings") else "Анализ завершён",finished=now(),result=result)
        print(json.dumps({"status":"completed","counts":result["counts"],"coverage":result["coverage"],"warnings":result["warnings"],"metrics":provider.snapshot()},ensure_ascii=False),flush=True)
    except Exception as exc:
        detail = str(exc)[:500] if isinstance(exc,ValueError) else type(exc).__name__
        store.update(pid,status="failed",stage="Проверка анализа не пройдена",error=detail,finished=now())
        print(json.dumps({"status":"failed","detail":detail,"metrics":provider.snapshot()},ensure_ascii=False),flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
