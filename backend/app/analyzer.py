from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable


UNIT_PATTERN = re.compile(
    r"\b(департамент|управление|отдел|служба|блок|центр|дирекция|комитет)\s+"
    r"([^.;:\n]{3,100})",
    re.IGNORECASE,
)
POINT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)+\.?)\s*(.*)$")
FUNCTION_WORDS = (
    "организует", "осуществляет", "проводит", "контролирует", "обеспечивает",
    "разрабатывает", "готовит", "согласовывает", "анализирует", "оценивает",
    "формирует", "взаимодействует", "координирует", "мониторинг", "проверка",
)
STOP_WORDS = {
    "который", "которая", "которые", "также", "общества", "общество", "внутреннего",
    "аудита", "работы", "работников", "порядке", "данного", "настоящего", "части",
}


@dataclass
class Evidence:
    document: str
    point: str
    quote: str


def clean_text(value: str) -> str:
    value = value.replace("\u00a0", " ").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def paragraphs(text: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    current_point = "—"
    current_text: list[str] = []
    for raw_line in clean_text(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = POINT_PATTERN.match(line)
        if match:
            if current_text:
                result.append((current_point, " ".join(current_text)))
            current_point = match.group(1).rstrip(".")
            current_text = [match.group(2)]
        else:
            current_text.append(line)
    if current_text:
        result.append((current_point, " ".join(current_text)))
    return result


def normalize_unit_name(name: str) -> str:
    name = re.sub(r"\([^)]*\)", "", name.lower())
    name = re.sub(r"[^а-яёa-z0-9 ]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def short_name(name: str) -> str | None:
    match = re.search(r"\(([А-ЯA-ZЁ]{2,12})\)", name)
    return match.group(1) if match else None


def extract_units(text: str, document: str) -> list[dict]:
    found: dict[str, dict] = {}
    for point, paragraph in paragraphs(text):
        for match in UNIT_PATTERN.finditer(paragraph):
            raw = f"{match.group(1)} {match.group(2)}".strip()
            raw = re.split(r"\s+[а-я]\.|\s+и\s+имеет|\s+в\s+соответствии", raw, maxsplit=1)[0]
            raw = raw.strip(" ,:-")
            if len(raw) > 110:
                raw = raw[:110].rsplit(" ", 1)[0]
            key = normalize_unit_name(raw)
            if key and key not in found:
                found[key] = {
                    "name": raw,
                    "shortName": short_name(raw),
                    "evidence": asdict(Evidence(document, point, paragraph[:260])),
                }
    return list(found.values())


def tokens(text: str) -> set[str]:
    words = re.findall(r"[а-яёa-z]{5,}", text.lower())
    return {word[:7] for word in words if word not in STOP_WORDS}


def similarity(left: str, right: str) -> float:
    left_tokens, right_tokens = tokens(left), tokens(right)
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence = SequenceMatcher(None, normalize_unit_name(left), normalize_unit_name(right)).ratio()
    return round(overlap * 0.65 + sequence * 0.35, 3)


def extract_functions(text: str, document: str) -> list[dict]:
    result: list[dict] = []
    for point, paragraph in paragraphs(text):
        lowered = paragraph.lower()
        if not any(word in lowered for word in FUNCTION_WORDS):
            continue
        sentences = re.split(r"(?<=[.;])\s+", paragraph)
        for sentence in sentences:
            if len(sentence) < 35 or not any(word in sentence.lower() for word in FUNCTION_WORDS):
                continue
            result.append({
                "id": f"{document}:{point}:{len(result)}",
                "text": sentence.strip()[:520],
                "point": point,
                "document": document,
                "evidence": asdict(Evidence(document, point, sentence.strip()[:320])),
            })
    return result[:250]


def compare_units(before: list[dict], after: list[dict]) -> list[dict]:
    transitions: list[dict] = []
    used_after: set[int] = set()
    for old in before:
        best_index, best_score = -1, 0.0
        for index, new in enumerate(after):
            if index in used_after:
                continue
            score = similarity(old["name"], new["name"])
            if old.get("shortName") and old.get("shortName") == new.get("shortName"):
                score = 1.0
            if score > best_score:
                best_index, best_score = index, score
        if best_index >= 0 and best_score >= 0.44:
            new = after[best_index]
            used_after.add(best_index)
            status = "Сохранено" if best_score >= 0.82 else "Преобразовано"
            transitions.append({
                "before": old["name"], "after": new["name"], "status": status,
                "confidence": round(best_score * 100),
                "evidenceBefore": old["evidence"], "evidenceAfter": new["evidence"],
            })
        else:
            transitions.append({
                "before": old["name"], "after": "Владелец не найден", "status": "Упразднено",
                "confidence": 0, "evidenceBefore": old["evidence"], "evidenceAfter": None,
            })
    for index, new in enumerate(after):
        if index not in used_after:
            transitions.append({
                "before": "—", "after": new["name"], "status": "Создано", "confidence": 100,
                "evidenceBefore": None, "evidenceAfter": new["evidence"],
            })
    return transitions


def compare_functions(before: list[dict], after: list[dict]) -> tuple[list[dict], list[dict]]:
    mapping: list[dict] = []
    findings: list[dict] = []
    after_matches: dict[int, list[int]] = {}
    for old_index, old in enumerate(before):
        scores = [(index, similarity(old["text"], new["text"])) for index, new in enumerate(after)]
        best_index, best_score = max(scores, key=lambda item: item[1], default=(-1, 0.0))
        if best_index >= 0 and best_score >= 0.35:
            new = after[best_index]
            after_matches.setdefault(best_index, []).append(old_index)
            mapping.append({
                "before": old["text"], "after": new["text"], "status": "Передана",
                "confidence": round(best_score * 100), "beforeEvidence": old["evidence"],
                "afterEvidence": new["evidence"],
            })
        else:
            mapping.append({
                "before": old["text"], "after": "Подтверждение в новых документах не найдено",
                "status": "Возможная потеря", "confidence": 0,
                "beforeEvidence": old["evidence"], "afterEvidence": None,
            })
            findings.append({
                "type": "Потеря функции", "severity": "high",
                "title": "Для прежней функции не найден новый владелец",
                "description": old["text"], "evidence": [old["evidence"]],
                "recommendation": "Проверить должностные инструкции и закрепить функцию за подразделением.",
            })

    for index, matched_old in after_matches.items():
        if len(matched_old) > 2:
            findings.append({
                "type": "Концентрация функций", "severity": "medium",
                "title": "Несколько прежних функций переданы одному новому пункту",
                "description": after[index]["text"], "evidence": [after[index]["evidence"]],
                "recommendation": "Уточнить границы ответственности и исполнителей.",
            })
    return mapping[:120], findings[:40]


def rule_findings(texts: Iterable[tuple[str, str]]) -> list[dict]:
    findings: list[dict] = []
    for document, text in texts:
        for point, paragraph in paragraphs(text):
            lowered = paragraph.lower()
            if "конфликт" in lowered and "интерес" in lowered:
                findings.append({
                    "type": "Конфликт интересов", "severity": "high",
                    "title": "Документ содержит условие о потенциальном конфликте интересов",
                    "description": paragraph[:420],
                    "evidence": [asdict(Evidence(document, point, paragraph[:320]))],
                    "recommendation": "Проверить меры независимости, раскрытие совмещения и порядок согласования.",
                })
            if "внутренн" in lowered and "аудит" in lowered and any(
                word in lowered for word in ("внедрять операционные", "принимать управленческие решения", "утверждать транзакции")
            ):
                findings.append({
                    "type": "Независимость", "severity": "medium",
                    "title": "Найдены ограничения полномочий внутреннего аудита",
                    "description": paragraph[:420],
                    "evidence": [asdict(Evidence(document, point, paragraph[:320]))],
                    "recommendation": "Сверить новые функции с установленными ограничениями независимости.",
                })
    return findings[:30]


def analyze(before_docs: list[dict], after_docs: list[dict]) -> dict:
    before_units = [unit for doc in before_docs for unit in extract_units(doc["text"], doc["name"])]
    after_units = [unit for doc in after_docs for unit in extract_units(doc["text"], doc["name"])]
    before_functions = [item for doc in before_docs for item in extract_functions(doc["text"], doc["name"])]
    after_functions = [item for doc in after_docs for item in extract_functions(doc["text"], doc["name"])]
    transitions = compare_units(before_units, after_units)
    function_map, function_findings = compare_functions(before_functions, after_functions)
    rules = rule_findings([(doc["name"], doc["text"]) for doc in before_docs + after_docs])
    findings = function_findings + rules
    summary = {
        "preserved": sum(item["status"] == "Сохранено" for item in transitions),
        "created": sum(item["status"] == "Создано" for item in transitions),
        "transformed": sum(item["status"] == "Преобразовано" for item in transitions),
        "removed": sum(item["status"] == "Упразднено" for item in transitions),
        "losses": sum(item["type"] == "Потеря функции" for item in findings),
        "risks": len(findings),
    }
    return {
        "summary": summary,
        "transitions": transitions[:80],
        "functionMap": function_map,
        "findings": findings,
        "documents": {
            "before": [{"name": doc["name"], "characters": len(doc["text"])} for doc in before_docs],
            "after": [{"name": doc["name"], "characters": len(doc["text"])} for doc in after_docs],
        },
        "engine": "rules-v1",
        "note": "Предварительный анализ выполнен без ИИ. Спорные выводы требуют проверки человеком.",
    }
