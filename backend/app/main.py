from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .analyzer import analyze
from .parsers import parse_file


app = FastAPI(
    title="ОргКонтур API",
    description="Анализ организационной структуры и функционала без подключения ИИ.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_FILE_SIZE = 20 * 1024 * 1024


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "engine": "rules-v1", "ai": False}


async def read_documents(files: list[UploadFile]) -> list[dict]:
    documents: list[dict] = []
    for upload in files:
        content = await upload.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(413, f"Файл {upload.filename} превышает 20 МБ")
        try:
            text = parse_file(upload.filename or "document", content)
        except Exception as error:
            raise HTTPException(400, f"Не удалось прочитать {upload.filename}: {error}") from error
        if not text.strip():
            raise HTTPException(400, f"В файле {upload.filename} не найден текст")
        documents.append({"name": upload.filename or "document", "text": text})
    return documents


@app.post("/api/analyze")
async def analyze_documents(
    before: Annotated[list[UploadFile], File(description="Документы до реорганизации")],
    after: Annotated[list[UploadFile], File(description="Документы после реорганизации")],
) -> dict:
    if not before or not after:
        raise HTTPException(400, "Нужен минимум один документ «до» и один документ «после»")
    before_docs = await read_documents(before)
    after_docs = await read_documents(after)
    return analyze(before_docs, after_docs)

