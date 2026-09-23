"""Explicit temporary storage for a single local server; no external database."""
from copy import deepcopy
from threading import RLock
import re
import uuid

from .storage import now


class MemoryStore:
    configured = True

    def __init__(self):
        self.projects = {}
        self.lock = RLock()

    def initialize(self):
        pass

    def ping(self):
        pass

    def recover(self):
        pass

    def close(self):
        pass

    def create(self, documents):
        with self.lock:
            pid = str(uuid.uuid4())
            self.projects[pid] = {"id": pid, "created": now(), "status": "ready",
                "stage": "Документы разобраны", "documents": [d.model_dump() for d in documents],
                "result": None, "reviews": {}, "error": None}
            return self.get(pid)

    def get(self, pid):
        with self.lock:
            return deepcopy(self.projects[pid])

    def list(self):
        with self.lock:
            rows = sorted(self.projects.values(), key=lambda p: p["created"], reverse=True)[:100]
            return [{k: p[k] for k in ("id", "created", "status", "stage")} for p in rows]

    def update(self, pid, **changes):
        with self.lock:
            p = self.projects[pid]
            p.update(deepcopy(changes))
            return {k: p[k] for k in ("id", "status", "stage")}

    def start(self, pid, mode):
        with self.lock:
            p = self.projects[pid]
            if p["status"] not in {"ready", "failed"} or p["result"] is not None:
                raise ValueError("Анализ уже запущен или результат сохранён. Для нового анализа создайте проект")
            self.update(pid, status="running", stage="В очереди", mode=mode, error=None)
            return self.get(pid)

    def review(self, pid, finding_id, review):
        with self.lock:
            p = self.projects[pid]
            if not re.fullmatch(r"finding-\d+", finding_id) or not p["result"] or finding_id not in {f["id"] for f in p["result"]["findings"]}:
                raise KeyError(finding_id)
            value = {**deepcopy(review), "updated": now()}
            p["reviews"][finding_id] = value
            return deepcopy(value)
