"""MongoDB persistence; large immutable analysis results are stored in GridFS."""
import json
import re
import uuid
from datetime import datetime, timezone

from gridfs import GridFS
from pymongo import MongoClient, ReturnDocument, DESCENDING
from pymongo.server_api import ServerApi
from .project_meta import summary


class StorageUnavailable(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, settings, client=None):
        self.settings = settings
        self.client = client

    @property
    def configured(self):
        return self.client is not None or bool(self.settings.mongodb_uri.get_secret_value())

    def connect(self):
        if self.client is None:
            uri = self.settings.mongodb_uri.get_secret_value()
            if not uri:
                raise StorageUnavailable("Укажите MONGODB_URI в .env и перезапустите сервер")
            self.client = MongoClient(uri, server_api=ServerApi("1"),
                serverSelectionTimeoutMS=5000, connectTimeoutMS=5000, socketTimeoutMS=30000)
        return self.client[self.settings.mongodb_database]

    def initialize(self):
        self.ping()
        self.connect().projects.create_index([("created", DESCENDING)])

    def ping(self):
        self.connect().command("ping")

    def close(self):
        if self.client is not None:
            self.client.close()

    def _public(self, project):
        if project is None:
            raise KeyError("project")
        project["id"] = project.pop("_id")
        result_file = project.pop("result_file", None)
        project["result"] = json.loads(GridFS(self.connect()).get(result_file).read()) if result_file else None
        return project

    def create(self, documents):
        project = {"_id":str(uuid.uuid4()), "created":now(), "status":"ready", "stage":"Документы разобраны",
            "documents":[d.model_dump() for d in documents], "result_file":None, "reviews":{}, "error":None}
        self.connect().projects.insert_one(project)
        return self._public(project)

    def get(self, pid):
        return self._public(self.connect().projects.find_one({"_id":pid}))

    def update(self, pid, **changes):
        db = self.connect()
        blob = None
        if "result" in changes:
            result = changes.pop("result")
            changes["counts"] = result.get("counts", {})
            blob = GridFS(db).put(json.dumps(result, ensure_ascii=False).encode(),
                filename=f"{pid}.json", contentType="application/json")
            changes["result_file"] = blob
        try:
            document = db.projects.find_one_and_update({"_id":pid}, {"$set":changes}, return_document=ReturnDocument.AFTER)
            if document is None:
                raise KeyError(pid)
        except KeyError:
            if blob is not None:
                GridFS(db).delete(blob)
            raise
        # Progress updates must not fetch the complete analysis blob.
        return {"id":pid, "status":document["status"], "stage":document["stage"]}

    def start(self, pid, mode):
        doc = self.connect().projects.find_one_and_update(
            {"_id":pid, "status":{"$in":["ready","failed","cancelled"]}, "result_file":None},
            {"$set":{"status":"running", "stage":"В очереди", "mode":mode, "error":None,
                      "started":now(), "finished":None}, "$inc":{"attempts":1}},
            return_document=ReturnDocument.AFTER)
        if doc is None:
            existing = self.connect().projects.find_one({"_id":pid}, {"status":1})
            if existing is None:
                raise KeyError(pid)
            raise ValueError("Анализ уже запущен или результат сохранён. Для нового анализа создайте проект")
        return self._public(doc)

    def review(self, pid, finding_id, review):
        project = self.get(pid)
        if not re.fullmatch(r"finding-\d+", finding_id) or not project["result"] or finding_id not in {f["id"] for f in project["result"]["findings"]}:
            raise KeyError(finding_id)
        value = {**review, "updated":now()}
        result = self.connect().projects.update_one({"_id":pid}, {"$set":{f"reviews.{finding_id}":value}})
        if not result.matched_count:
            raise KeyError(pid)
        return value

    def list(self):
        fields = {k:1 for k in ("created", "status", "stage", "error", "started", "finished", "metrics", "attempts", "mode", "counts", "reviews", "documents.name", "documents.side", "documents.clauses.id")}
        cursor = self.connect().projects.find({}, fields).sort("created", DESCENDING).limit(100)
        return [summary({"id":p.pop("_id"), **p}) for p in cursor]

    def cache_get(self, pid, key):
        db = self.connect()
        cached = db.analysis_cache.find_one({"_id":f"{pid}:{key}"})
        return json.loads(GridFS(db).get(cached["file"]).read()) if cached else None

    def status(self, pid):
        fields = {k:1 for k in ("created", "status", "stage", "error", "started", "finished", "metrics", "attempts", "mode", "counts", "reviews", "documents.name", "documents.side", "documents.clauses.id")}
        p = self.connect().projects.find_one({"_id":pid}, fields)
        if p is None:
            raise KeyError(pid)
        return summary({"id":p.pop("_id"), **p})

    def cache_put(self, pid, key, value):
        db = self.connect()
        blob = GridFS(db).put(json.dumps(value, ensure_ascii=False).encode())
        try:
            old = db.analysis_cache.find_one_and_replace({"_id":f"{pid}:{key}"},
                {"_id":f"{pid}:{key}", "file":blob}, upsert=True)
        except Exception:
            GridFS(db).delete(blob)
            raise
        if old:
            GridFS(db).delete(old["file"])

    def recover(self):
        self.connect().projects.update_many({"status":"running"}, {"$set":{
            "status":"failed", "stage":"Прервано перезапуском сервера",
            "error":"Повторите анализ; незавершённый результат не опубликован"}})
