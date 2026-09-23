"""Opt-in real API/Atlas/OpenAI acceptance run. Does not reset existing projects.

Creates one project, keeps it in history, verifies exports and reconnect persistence.
Use --project-id to resume a failed run without losing the request cache or budget.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.storage import Store
from scripts.live_smoke import verify_control


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--project-id")
    parser.add_argument("--budget", type=float, default=.03)
    args = parser.parse_args()
    if bool(args.before) != bool(args.after) or (args.project_id and args.before):
        parser.error("Use both --before and --after, or --project-id")
    settings = Settings(kontur_budget_usd=args.budget)
    if settings.kontur_storage != "mongodb":
        parser.error("This integration check requires KONTUR_STORAGE=mongodb")
    store = Store(settings)
    pid = args.project_id
    try:
        store.ping()
        if store.connect().projects.find_one({"status":"running"}, {"_id":1}):
            print("An analysis is already running (or interrupted). Resolve it before this check.", flush=True)
            return 1
        with TestClient(create_app(settings=settings, store=store)) as client:
            assert client.get("/api/health").json()["database"] == "connected"
            if not pid:
                if args.before:
                    response = client.post("/api/projects", files=[
                        ("before", (args.before.name, args.before.read_bytes())),
                        ("after", (args.after.name, args.after.read_bytes()))])
                else:
                    response = client.post("/api/projects/sample?kind=control")
                assert response.status_code == 201, "Upload failed"
                pid = response.json()["id"]
            print(json.dumps({"project_id":pid,"database":settings.mongodb_database,"budget_usd":args.budget}), flush=True)
            current = client.get(f"/api/projects/{pid}").json()
            if current["status"] != "completed":
                response = client.post(f"/api/projects/{pid}/analyze", json={"mode":"openai"})
                assert response.status_code == 202, "Analysis could not start"
                previous = None
                while True:
                    status = client.get(f"/api/projects/{pid}/status").json()
                    if status["stage"] != previous:
                        print(status["stage"], flush=True)
                        previous = status["stage"]
                    if status["status"] != "running":
                        break
                    time.sleep(2)
            project = client.get(f"/api/projects/{pid}").json()
            if project["status"] != "completed":
                print(json.dumps({"status":project["status"],"error":project.get("error"),"metrics":project.get("metrics")}, ensure_ascii=False), flush=True)
                return 1
            result = project["result"]
            assert all(f["evidence"] and all(e["quote"] in e["text"] for e in f["evidence"]) for f in result["findings"])
            before_ids = [i for f in result["findings"] for i in f["before_ids"]]
            assert len(before_ids) == len(set(before_ids)) == result["coverage"]["before_functions"]
            assert "_cache" not in project
            for extension in ("json", "csv", "docx", "md"):
                response = client.get(f"/api/projects/{pid}/export?format={extension}")
                assert response.status_code == 200 and response.content, f"Export failed: {extension}"
            print(json.dumps({"status":"completed", "exports":"json,csv,docx,md", "counts":result["counts"],
                "coverage":result["coverage"], "warnings":result.get("warnings", []), "metrics":project.get("metrics")}, ensure_ascii=False), flush=True)
        reopened = Store(settings)
        try:
            assert reopened.get(pid)["result"] == result
            assert reopened.status(pid)["status"] == "completed"
            print("ATLAS_RESULT_REOPEN_VERIFIED", flush=True)
        finally:
            reopened.close()
        if not args.before and not args.project_id:
            verify_control(result)
        return 0
    except Exception as exc:
        # Provider exceptions can contain sensitive connection/response data.
        print(json.dumps({"status":"failed","project_id":pid,"error_type":type(exc).__name__}), flush=True)
        return 1
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
