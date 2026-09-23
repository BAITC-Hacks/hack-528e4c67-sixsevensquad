"""Explicit temporary storage for a single local server; no external database."""
from copy import deepcopy
from threading import RLock
import re
import uuid

from .storage import now
from .project_meta import summary


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
        for pid, p in list(self.projects.items()):
            if p["status"] == "running":
                self.update(pid, status="failed", stage="Прервано перезапуском сервера",
                            error="Можно продолжить: завершённые запросы сохранены", finished=now())

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
            return [summary(p) for p in rows]

    def status(self, pid):
        with self.lock:
            return deepcopy(summary(self.projects[pid]))

    def cache_get(self, pid, key):
        with self.lock:
            return deepcopy(self.projects[pid].get("_cache", {}).get(key))

    def cache_put(self, pid, key, value):
        with self.lock:
            cache = deepcopy(self.projects[pid].get("_cache", {}))
            cache[key] = value
            self.update(pid, _cache=cache)

    def update(self, pid, **changes):
        with self.lock:
            p = self.projects[pid]
            p.update(deepcopy(changes))
            return {k: p[k] for k in ("id", "status", "stage")}

    def start(self, pid, mode):
        with self.lock:
            p = self.projects[pid]
            if p["status"] not in {"ready", "failed", "cancelled"} or p["result"] is not None:
                raise ValueError("Анализ уже запущен или результат сохранён. Для нового анализа создайте проект")
            self.update(pid, status="running", stage="В очереди", mode=mode, error=None,
                        started=now(), finished=None, attempts=p.get("attempts", 0)+1)
            return self.get(pid)

    def review(self, pid, finding_id, review):
        with self.lock:
            p = self.projects[pid]
            if not re.fullmatch(r"finding-\d+", finding_id) or not p["result"] or finding_id not in {f["id"] for f in p["result"]["findings"]}:
                raise KeyError(finding_id)
            value = {**deepcopy(review), "updated": now()}
            reviews = deepcopy(p["reviews"])
            reviews[finding_id] = value
            self.update(pid, reviews=reviews)
            return deepcopy(value)
