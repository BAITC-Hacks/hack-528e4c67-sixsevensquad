"""Explicit single-process durable local storage until Atlas is configured."""
import json
import os
import tempfile
from pathlib import Path

from .memory_storage import MemoryStore


class LocalStore(MemoryStore):
    def __init__(self, directory):
        super().__init__()
        self.directory = Path(directory)

    def initialize(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        for path in self.directory.glob("*.json"):
            project = json.loads(path.read_text(encoding="utf-8"))
            if path.stem != project["id"]:
                raise ValueError("Несогласованный файл проекта")
            self.projects[project["id"]] = project

    def persist(self, pid):
        with self.lock:
            fd, temporary = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(self.projects[pid], stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.directory / f"{pid}.json")
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

    def create(self, documents):
        with self.lock:
            project = super().create(documents)
            self.persist(project["id"])
            return project

    def update(self, pid, **changes):
        with self.lock:
            result = super().update(pid, **changes)
            self.persist(pid)
            return result
