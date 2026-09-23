"""Parse documents without inventing page numbers or rewriting quoted text."""
import hashlib
import io
import re
import zipfile
from pathlib import Path

from .schemas import Clause, Document, Side

MAX_BYTES = 10 * 1024 * 1024
NUMBER = re.compile(r"^(\d+(?:\.\d+)+)\.?\s*(.*)$")

def pdf_blocks(content: str, page: int) -> list[tuple[str, str]]:
    """Reassemble PDF text runs; retain page and physical line provenance.

    Some PDF writers emit one word per line. Newlines are therefore not
    paragraph boundaries. Numbered clauses and list markers are boundaries.
    """
    boundaries = {0, len(content)}
    for match in re.finditer(r"(?<!\S)\d+(?:\.\d+)+\.?\s+(?=\S)", content):
        line_start = content.rfind("\n", 0, match.start()) + 1
        at_line_start = not content[line_start:match.start()].strip()
        if at_line_start or content[match.end()].isupper():
            boundaries.add(match.start())
    for match in re.finditer(r"(?m)^[ \t]*[а-яА-Я][.)][ \t]+(?=\S)", content):
        boundaries.add(match.start())
    positions = sorted(boundaries)
    blocks = []
    for start, end in zip(positions, positions[1:]):
        # Bound long unnumbered sections without dropping or rewriting words.
        cursor = start
        while cursor < end:
            stop = min(cursor + 6000, end)
            if stop < end:
                whitespace = max(content.rfind(" ", cursor, stop), content.rfind("\n", cursor, stop))
                if whitespace > cursor:
                    stop = whitespace
            raw = content[cursor:stop]
            text = re.sub(r"\s+", " ", raw).strip()
            if text:
                first = content.count("\n", 0, cursor) + 1
                last = content.count("\n", 0, stop) + 1
                blocks.append((f"стр. {page}, строки {first}–{last}", text))
            cursor = stop
    return blocks

def parse_document(name: str, data: bytes, side: Side, document_id: str) -> Document:
    name = Path(name.replace("\\", "/")).name
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Файл пуст или превышает 10 МБ")
    suffix = Path(name).suffix.lower()
    if suffix in {".docx", ".xlsx"}:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if sum(x.file_size for x in archive.infolist()) > 60 * 1024 * 1024:
                raise ValueError("Слишком большой распакованный документ")
    blocks: list[tuple[str, str]] = []
    if suffix == ".txt":
        blocks = [(f"строка {i}", line) for i, line in enumerate(data.decode("utf-8-sig").splitlines(), 1)]
    elif suffix == ".docx":
        from docx import Document as WordDocument
        from docx.table import Table
        doc = WordDocument(io.BytesIO(data))
        for i, block in enumerate(doc.iter_inner_content(), 1):
            if isinstance(block, Table):
                for j, row in enumerate(block.rows, 1):
                    blocks.append((f"блок {i}, строка таблицы {j}", " | ".join(c.text for c in row.cells)))
            else:
                blocks.append((f"абзац {i}", block.text))
    elif suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("PDF зашифрован. Загрузите незашифрованную копию")
        if len(reader.pages) > 200:
            raise ValueError("Максимум 200 страниц PDF")
        for i, page in enumerate(reader.pages, 1):
            content = page.extract_text() or ""
            if len(content.strip()) < 10:
                raise ValueError(f"PDF: страница {i} без текста. Сначала выполните OCR; неполный анализ запрещён")
            blocks.extend(pdf_blocks(content, i))
    elif suffix == ".xlsx":
        from openpyxl import load_workbook
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=False)
        try:
            for sheet in book:
                if sheet.max_row and sheet.max_row > 20000:
                    raise ValueError("Excel: максимум 20000 строк на лист")
                for i, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    text = " | ".join(str(c) for c in row if c is not None)
                    if text.strip():
                        blocks.append((f"лист {sheet.title}, строка {i}", text))
        finally:
            book.close()
    else:
        raise ValueError("Поддерживаются .txt, .docx, .pdf с текстом, .xlsx. Старые .doc/.xls нужно пересохранить")
    clauses: list[Clause] = []
    current_number = ""
    for locator, text in blocks:
        text = text.strip()
        if not text:
            continue
        match = NUMBER.match(text)
        if match:
            current_number = match.group(1)
        elif not re.match(r"^[а-яa-z][.)]\s|^[-–•]\s", text, re.I):
            current_number = ""
        if current_number:
            locator = f"п. {current_number}; {locator}"
        clauses.append(Clause(id=f"{document_id}:c{len(clauses)+1}", document=name, side=side, locator=locator, text=text))
    if not clauses or sum(len(c.text) for c in clauses) < 20:
        raise ValueError("В документе недостаточно извлекаемого текста")
    return Document(id=document_id, name=name, side=side, sha256=hashlib.sha256(data).hexdigest(), clauses=clauses)
