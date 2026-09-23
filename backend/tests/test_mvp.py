import io
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.baseline import BaselineProvider
from backend.app.evidence import EvidenceError, validate_evidence
from backend.app.main import create_app
from backend.app.memory_storage import MemoryStore
from backend.app.parsers import parse_document
from backend.app.pipeline import analyze
from backend.app.schemas import Evidence

ROOT = Path(__file__).resolve().parents[2]


def fixture_documents(prefix):
    return [
        parse_document(f"{prefix}-{side}.txt", (ROOT / "data" / "samples" / f"{prefix}-{side}.txt").read_bytes(), side, side)
        for side in ("before", "after")
    ]


def test_control_set_covers_required_risks_and_sources():
    result = analyze(fixture_documents("control"), BaselineProvider(), "baseline")
    assert result["counts"]["not_found"] >= 1
    assert result["counts"]["duplication"] >= 1
    assert result["counts"]["conflict"] >= 1
    assert result["counts"]["transferred"] >= 1
    assert all(f["evidence"] and all(e["quote"] in e["text"] for e in f["evidence"]) for f in result["findings"])


def test_organizer_structure_is_not_polluted_by_incidental_mentions():
    result = analyze(fixture_documents("organizer"), BaselineProvider(), "baseline")
    changes = result["unit_changes"]
    assert len(changes) == 5
    assert sum(c["status"] == "preserved" for c in changes) == 2
    assert sum(c["status"] == "created" for c in changes) == 2
    assert any("ДИТААД" in c["after_names"][0] for c in changes if c["status"] == "created")
    assert any("ДОА" in c["after_names"][0] for c in changes if c["status"] == "created")


def test_unverified_quote_is_rejected():
    doc = fixture_documents("control")[0]
    try:
        validate_evidence([Evidence(clause_id=doc.clauses[0].id, quote="Выдуманное правило")],
                          {c.id: c for c in doc.clauses})
    except EvidenceError:
        pass
    else:
        raise AssertionError("Неподтверждённая цитата прошла проверку")


def test_api_upload_review_and_exports():
    app = create_app(store=MemoryStore())
    with TestClient(app) as client:
        response = client.post("/api/projects/sample?kind=control")
        assert response.status_code == 201
        pid = response.json()["id"]
        assert client.post(f"/api/projects/{pid}/analyze", json={"mode": "baseline"}).status_code == 202
        for _ in range(100):
            project = client.get(f"/api/projects/{pid}").json()
            if project["status"] != "running":
                break
            time.sleep(.02)
        assert project["status"] == "completed", project.get("error")
        finding_id = project["result"]["findings"][0]["id"]
        review = client.put(f"/api/projects/{pid}/findings/{finding_id}/review",
                            json={"decision": "confirmed", "comment": "Проверено на исходнике"})
        assert review.status_code == 200
        assert "Проверено на исходнике" in client.get(f"/api/projects/{pid}/export?format=md").text
        assert client.get(f"/api/projects/{pid}/export?format=json").status_code == 200
        assert client.get(f"/api/projects/{pid}/export?format=csv").content.startswith(b"\xef\xbb\xbf")
        docx = client.get(f"/api/projects/{pid}/export?format=docx")
        assert docx.status_code == 200 and docx.content.startswith(b"PK")


def test_upload_parse_word_excel_and_reject_scan():
    from docx import Document
    from openpyxl import Workbook
    from pypdf import PdfWriter

    word = Document()
    word.add_paragraph("1.1. Отдел контроля:")
    word.add_table(rows=1, cols=1).cell(0, 0).text = "Проверяет расходы филиалов."
    stream = io.BytesIO()
    word.save(stream)
    parsed = parse_document("case.docx", stream.getvalue(), "before", "d1")
    assert "строка таблицы" in parsed.clauses[1].locator

    book = Workbook()
    book.active.append(["Владелец", "Функция"])
    book.active.append(["Отдел контроля", "Проверяет расходы"])
    stream = io.BytesIO()
    book.save(stream)
    parsed = parse_document("case.xlsx", stream.getvalue(), "after", "d2")
    assert "строка 2" in parsed.clauses[1].locator

    pdf = PdfWriter()
    pdf.add_blank_page(width=300, height=300)
    stream = io.BytesIO()
    pdf.write(stream)
    try:
        parse_document("scan.pdf", stream.getvalue(), "before", "d3")
    except ValueError as exc:
        assert "OCR" in str(exc)
    else:
        raise AssertionError("Пустой скан ошибочно принят")
