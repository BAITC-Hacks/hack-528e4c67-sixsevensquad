"""Conservative offline analysis. The OpenAI provider uses the same typed contract."""
import re
from difflib import SequenceMatcher

from .schemas import Evidence, Extraction, Function, Match, Matches, Risk, Risks, Unit, UnitChange, UnitChanges


def canonical(text):
    text = re.sub(r"^\d+(?:\.\d+)*\.?\s*", "", text.lower().replace("ё", "е"))
    return " ".join(re.findall(r"[а-яa-z]{3,}", text))


def similarity(a, b):
    return SequenceMatcher(None, canonical(a), canonical(b)).ratio()


def keywords(text):
    stop = {"проверяет", "утверждает", "независимо", "договоры", "договоров", "отчеты", "работу", "работы", "осуществляет", "проводит"}
    return {w for w in canonical(text).split() if len(w) >= 5 and w not in stop}


class BaselineProvider:
    calls = 0
    usage = {"input_tokens": 0, "output_tokens": 0}

    def extract(self, clauses, context):
        units, functions = [], []
        side = clauses[0].side if clauses else "before"
        owner = "Владелец не определён"
        owner_clause = None
        for previous in context.get("previous", []):
            match = re.match(r"^\d+(?:\.\d+)+\.\s*(Отдел [^:]+):", previous["text"])
            if match:
                owner, owner_clause = match.group(1), previous
        section_heading = next((h for h in context.get("headers", [])
                                if re.match(r"^5\.3\.\s", h["text"])), None)
        for clause in clauses:
            text = clause.text.strip()
            number_match = re.match(r"^(\d+(?:\.\d+)+)\.", text)
            number = number_match.group(1) if number_match else ""
            if number == "3.4" or re.match(r"^[а-я][.)]\s*Департамент\s", text, re.I):
                for match in re.finditer(r"\bДепартамент\s+[^.;:]{3,95}?\s*\([А-ЯЁA-Z]{2,12}\)", text):
                    units.append(Unit(name=match.group(0), kind="department",
                                      evidence=[Evidence(clause_id=clause.id, quote=match.group(0))]))
            section = re.match(r"^\d+(?:\.\d+)+\.\s*(Отдел [^:]+):", text)
            if section:
                owner, owner_clause = section.group(1), clause.model_dump()
                units.append(Unit(name=owner, kind="department",
                                  evidence=[Evidence(clause_id=clause.id, quote=owner)]))
            if number == "5.3" and "Директор направления внутреннего аудита" in text:
                units.append(Unit(name="Директор направления внутреннего аудита", kind="role",
                                  evidence=[Evidence(clause_id=clause.id, quote="Директор направления внутреннего аудита")]))
            if not re.search(r"\b(?:организу\w+|готов\w+|провод\w+|формиру\w+|анализиру\w+|проверя\w+|утвержда\w+|контролиру\w+|разрабатыва\w+|обеспечива\w+)\b", text, re.I):
                continue
            if "не имеют права" in text.lower() or "не вправе" in text.lower():
                continue
            active_owner, source = owner, owner_clause
            if number.startswith("5.3"):
                active_owner = "Директор направления внутреннего аудита" if side == "before" else "ДИТААД и ДОА"
                if "ДИТААД" in text and "ДОА" not in text:
                    active_owner = "ДИТААД"
                elif "ДОА" in text and "ДИТААД" not in text:
                    active_owner = "ДОА"
                source = section_heading
            elif number.startswith("5.4"):
                active_owner, source = "ДНМ", None
            elif number.startswith("5.5"):
                active_owner, source = "ДККМ", None
            elif number.startswith("2.4"):
                active_owner, source = "БВА", None
            elif number.startswith(("5.1", "5.2")):
                active_owner, source = "Главный аудитор", None
            evidence = [Evidence(clause_id=clause.id, quote=text)]
            if source and source["id"] != clause.id:
                evidence.append(Evidence(clause_id=source["id"], quote=source["text"]))
            functions.append(Function(owner=active_owner, action=canonical(text), object=canonical(text),
                                      scope="Лексический режим; подтвердить смысл вручную", evidence=evidence))
        return Extraction(units=units, functions=functions)

    def match(self, before, after):
        matches = []
        for function in before:
            score, candidate = max(((similarity(function["action"], item["action"]), item) for item in after),
                                   key=lambda pair: pair[0], default=(0, None))
            found = candidate is not None and score >= .72
            status = "preserved" if found and function["owner"] == candidate["owner"] else "transferred" if found else "not_found"
            matches.append(Match(before_id=function["id"], after_ids=[candidate["id"]] if found else [],
                                 status=status, explanation="Лексическое соответствие найдено." if found else
                                 "Близкая формулировка не найдена во всём каталоге новых функций.",
                                 recommendation="Проверить смысл функции и источники вручную."))
        return Matches(matches=matches)

    def risks(self, focus, catalog):
        risks = []
        for function in focus:
            for other in catalog:
                if function["id"] >= other["id"]:
                    continue
                left, right = function["action"], other["action"]
                if function["owner"] != other["owner"] and similarity(left, right) > .95 and len(keywords(left) & keywords(right)) >= 2:
                    risks.append(Risk(kind="duplication", function_ids=[function["id"], other["id"]],
                                      explanation="Одинаковое действие над похожим объектом закреплено за разными владельцами.",
                                      recommendation="Уточнить зоны ответственности и проверить, не разделены ли объекты."))
                if function["owner"] == other["owner"]:
                    approval = next((s for s in (left, right) if "утвержда" in s), "")
                    inspection = next((s for s in (left, right) if "проверя" in s and "независим" in s), "")
                    if approval and inspection and len(keywords(approval) & keywords(inspection)) >= 2:
                        risks.append(Risk(kind="conflict", function_ids=[function["id"], other["id"]],
                                          explanation="Один владелец утверждает и независимо проверяет тот же объект.",
                                          recommendation="Разделить утверждение и независимую проверку."))
        return Risks(risks=risks)

    def units(self, before, after):
        old, new = {u["name"] for u in before}, {u["name"] for u in after}
        return UnitChanges(changes=[
            UnitChange(before_names=[name] if name in old else [], after_names=[name] if name in new else [],
                       status="preserved" if name in old & new else "created" if name in new else "not_found",
                       explanation="Сопоставление по наименованию из оргструктуры; изменение роли требует проверки.")
            for name in sorted(old | new)
        ])
