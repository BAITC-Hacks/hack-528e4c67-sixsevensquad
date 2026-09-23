from collections import Counter
from difflib import SequenceMatcher
import re
from .schemas import FunctionRecord
from .evidence import EvidenceError, anchor_extraction, validate_extraction, hydrate

LABELS = {"preserved": "Сохранена", "transferred": "Передана", "split": "Разделена", "changed": "Изменена",
          "not_found": "Потенциальная потеря", "uncertain": "Недостаточно данных", "new": "Без соответствия до",
          "duplication": "Возможное дублирование", "conflict": "Возможный конфликт"}

NUMBER = re.compile(r"^(\d+(?:\.\d+)*)\.\s")

def extraction_context(document, start, batch, related_documents):
    """Keep only nearby/ancestor headings instead of resending a whole document."""
    preceding = document.clauses[:start]
    first = next((match for clause in batch if (match := NUMBER.match(clause.text))), None)
    if first is None:
        first = next((match for clause in reversed(preceding) if (match := NUMBER.match(clause.text))), None)
    section = first.group(1) if first else ""
    ancestors = {".".join(section.split(".")[:n]) for n in range(1, len(section.split(".")))} if section else set()
    headings = {}
    for clause in preceding:
        number = NUMBER.match(clause.text)
        if number and number.group(1) in ancestors:
            headings[number.group(1)] = clause
    structural = [c for c in preceding if NUMBER.match(c.text) and NUMBER.match(c.text).group(1) == "3.4"][-1:]
    headers = list({c.id: c for c in [*structural, *headings.values()]}.values())[-6:]
    previous = [c for c in preceding[-6:] if len(c.text) <= 1200][-3:]
    related = []
    for other in related_documents:
        candidates = [c for c in other.clauses if NUMBER.match(c.text) and
                      NUMBER.match(c.text).group(1) in {"3.4", "3.5"}]
        related.extend(candidates[:2])
    related = related[:4]
    return {"headers": [c.model_dump() for c in headers],
            "previous": [c.model_dump() for c in previous],
            "related_headers": [c.model_dump() for c in related]}

def lexical_candidates(source, pool, limit=3):
    def tokens(text):
        return set(re.findall(r"[а-яёa-z]{4,}", text.lower()))
    query = f"{source.action} {source.object} {source.scope}"
    query_tokens = tokens(query)
    scored = []
    for item in pool:
        target = f"{item.action} {item.object} {item.scope}"
        target_tokens = tokens(target)
        overlap = len(query_tokens & target_tokens) / max(1, len(query_tokens | target_tokens))
        score = max(overlap, SequenceMatcher(None, query[:300].lower(), target[:300].lower()).ratio())
        scored.append((score, item))
    return [{"id": item.id, "owner": item.owner, "action": item.action,
             "object": item.object, "lexical_score": round(score, 2)}
            for score, item in sorted(scored, key=lambda pair: pair[0], reverse=True)[:limit]]

def infer_baseline_reorganizations(changes, units, findings, catalog):
    """A conservative offline hint: old department functions flow into new departments."""
    created = {c["after_names"][0]: c for c in changes if c["status"] == "created" and
               len(c["after_names"]) == 1 and units["after"][c["after_names"][0]].kind == "department"}
    used_new = set()
    replaced = set()
    inferred = []
    for old in changes:
        if old["status"] != "not_found" or len(old["before_names"]) != 1:
            continue
        old_name = old["before_names"][0]
        if units["before"][old_name].kind != "department":
            continue
        linked_ids = set()
        supports = []
        for finding in findings:
            if finding["kind"] not in {"transferred", "split", "changed"}:
                continue
            if any(catalog[i].owner == old_name for i in finding["before_ids"]):
                linked_ids.update(finding["after_ids"])
                supports.append(finding)
        for finding in findings:
            if finding["kind"] == "duplication" and linked_ids.intersection(finding["after_ids"]):
                linked_ids.update(finding["after_ids"])
                supports.append(finding)
        new_names = sorted({catalog[i].owner for i in linked_ids if catalog[i].owner in created and catalog[i].owner not in used_new})
        if not new_names:
            continue
        used_new.update(new_names)
        replaced.update([id(old), *(id(created[name]) for name in new_names)])
        source_rows = [*old["evidence"], *(e for name in new_names for e in created[name]["evidence"]),
                       *(e for finding in supports for e in finding["evidence"])]
        unique_sources = list({(e["clause_id"], e["quote"]): e for e in source_rows}.values())
        inferred.append({"before_names": [old_name], "after_names": new_names,
                         "status": "reorganized", "explanation":
                         "Вероятное преобразование по переходу функций; юридический статус и полноту передачи требуется проверить.",
                         "evidence": unique_sources})
    return [c for c in changes if id(c) not in replaced] + inferred

def batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i+size]

def retain_target_supported(result, target_ids):
    """Context establishes ownership but cannot create a record on its own."""
    result.units = [item for item in result.units if any(e.clause_id in target_ids for e in item.evidence)]
    result.functions = [item for item in result.functions if any(e.clause_id in target_ids for e in item.evidence)]

def clause_batches(clauses, limit=16000):
    batch, length = [], 0
    for c in clauses:
        if batch and length + len(c.text) > limit:
            yield batch
            batch, length = [], 0
        if len(c.text) > limit:
            raise ValueError("Один пункт слишком длинный. Разбейте документ на абзацы")
        batch.append(c)
        length += len(c.text)
    if batch:
        yield batch

def analyze(documents, provider, mode, progress=lambda text: None):
    index = {c.id:c for d in documents for c in d.clauses}
    records, units = [], {"before": {}, "after": {}}
    for d in documents:
        offset = 0
        related = [other for other in documents if other.side == d.side and other.id != d.id]
        document_batches = list(clause_batches(d.clauses))
        for number, batch in enumerate(document_batches, 1):
            progress(f"Извлечение: {d.name}, часть {number} из {len(document_batches)}")
            context = extraction_context(d, offset, batch, related)
            context_ids = {x["id"] for group in context.values() for x in group}
            valid_context = [c for c in index.values() if c.id in context_ids] + batch
            result = provider.extract(batch, context)
            target_ids = {c.id for c in batch}
            for attempt in range(2):
                try:
                    anchor_extraction(result, valid_context)
                    validate_extraction(result, valid_context)
                    retain_target_supported(result, target_ids)
                    break
                except EvidenceError as exc:
                    if attempt or not hasattr(provider, "repair_extraction"):
                        raise EvidenceError(f"Не удалось подтвердить источники: {d.name}, часть {number}. {exc}") from exc
                    progress(f"Уточнение цитат: {d.name}, часть {number} из {len(document_batches)}")
                    result = provider.repair_extraction(batch, context, result, exc)
            for item in result.functions:
                existing = next((f for f in records if f.side == d.side and f.owner == item.owner and f.action == item.action and f.object == item.object and f.scope == item.scope), None)
                if existing:
                    existing.evidence.extend(e for e in item.evidence if e not in existing.evidence)
                else:
                    records.append(FunctionRecord(**item.model_dump(), id=f"f{len(records)+1}", side=d.side))
            for unit in result.units:
                existing = units[d.side].get(unit.name)
                if existing:
                    existing.evidence.extend(e for e in unit.evidence if e not in existing.evidence)
                else:
                    units[d.side][unit.name] = unit
            offset += len(batch)
    before = [f for f in records if f.side == "before"]
    after = [f for f in records if f.side == "after"]
    if not before or not after:
        raise ValueError("Не удалось извлечь функции с обеих сторон. Проверьте содержимое документов")
    if len(records) > 700:
        raise ValueError("Слишком большой каталог для MVP (максимум 700 функций). Разделите анализ")
    catalog = {f.id:f for f in records}
    # Include verified evidence in comparisons; no similarity-only final decisions.
    after_payload = [f.model_dump() for f in after]
    progress("Сопоставление подразделений и должностей")
    unit_changes = provider.units([u.model_dump() for u in units["before"].values()], [u.model_dump() for u in units["after"].values()])
    covered_units = {"before":set(), "after":set()}
    unit_results = []
    for change in unit_changes.changes:
        b, a = change.before_names, change.after_names
        if (not b and not a) or any(n not in units["before"] for n in b) or any(n not in units["after"] for n in a):
            raise EvidenceError("Некорректная ссылка на подразделение")
        if len(set(b)) != len(b) or len(set(a)) != len(a) or set(b) & covered_units["before"] or set(a) & covered_units["after"]:
            raise EvidenceError("Подразделение сопоставлено более одного раза")
        if change.status in {"preserved", "reorganized"} and (not b or not a):
            raise EvidenceError("Изменение подразделения требует обеих сторон")
        if b and a and {units["before"][n].kind for n in b} != {units["after"][n].kind for n in a}:
            raise EvidenceError("Нельзя сопоставить должность с подразделением как одну структурную единицу")
        if change.status == "created" and (b or not a) or change.status == "not_found" and (a or not b):
            raise EvidenceError("Статус подразделения не согласован со сторонами")
        covered_units["before"].update(b); covered_units["after"].update(a)
        evidence = [e for s,names in [("before", b), ("after", a)] for n in names for e in units[s][n].evidence]
        unit_results.append({**change.model_dump(), "evidence": hydrate(evidence, index)})
    if any(covered_units[s] != set(units[s]) for s in covered_units):
        raise EvidenceError("Сопоставление подразделений неполное")
    findings, used_after = [], set()
    def add(kind, b, a, explanation, recommendation):
        fs = [catalog[i] for i in b+a]
        evidence = list({(e.clause_id, e.quote): e for f in fs for e in f.evidence}.values())
        cited = hydrate(evidence, index)
        sides = {e["side"] for e in cited}
        if kind == "not_found" or (kind == "uncertain" and not a):
            required = {"before"}
        elif kind in {"new", "duplication", "conflict"}:
            required = {"after"}
        else:
            required = {"before", "after"}
        if not required <= sides:
            raise EvidenceError("Вывод не подтверждён источниками нужных редакций")
        search_scope = None
        if kind in {"not_found", "new", "uncertain"}:
            pool = after if kind != "new" else before
            source = catalog[(b or a)[0]]
            search_scope = {"documents": [d.name for d in documents if d.side == ("before" if kind == "new" else "after")],
                            "catalog_size": len(pool), "owners": sorted({f.owner for f in pool}),
                            "candidates": lexical_candidates(source, pool),
                            "note": "Кандидаты подобраны по словам для ручной проверки; их сходство не доказывает совпадение функций."}
        findings.append({"id": f"finding-{len(findings)+1}", "kind":kind, "label": LABELS[kind],
            "before_ids": b, "after_ids": a, "title": f"{fs[0].action} — {fs[0].object}",
            "explanation":explanation, "recommendation":recommendation,
            "requires_review":True, "evidence":cited,
            "evidence_check":{"exact_quotes":True, "required_sides_present":True,
                              "interpretation":"requires_review"},
            "search_scope": search_scope})
    for chunk in batches(before, 16):
        progress(f"Сопоставление функций: {len(findings)} / {len(before)}")
        result = provider.match([f.model_dump() for f in chunk], after_payload)
        expected = {f.id for f in chunk}
        returned = [m.before_id for m in result.matches]
        if len(set(returned)) != len(returned) or set(returned) != expected:
            raise EvidenceError("ИИ не сопоставил каждую функцию ровно один раз")
        for m in result.matches:
            if any(i not in catalog or catalog[i].side != "after" for i in m.after_ids):
                raise EvidenceError("ИИ сослался на неизвестную функцию после")
            if m.status == "not_found" and m.after_ids or m.status in {"preserved", "transferred", "changed"} and len(m.after_ids) != 1:
                raise EvidenceError("Статус и связи функции противоречат друг другу")
            if m.status == "split" and len(set(m.after_ids)) < 2:
                raise EvidenceError("Разделение требует двух функций-получателей")
            if m.status == "uncertain" and len(set(m.after_ids)) > 3:
                raise EvidenceError("Для спорного соответствия допустимо не более трёх кандидатов")
            used_after.update(m.after_ids)
            add(m.status, [m.before_id], list(dict.fromkeys(m.after_ids)), m.explanation, m.recommendation)
    for f in after:
        if f.id not in used_after:
            add("new", [], [f.id], "В извлечённом каталоге до не установлено соответствие. Это не доказывает, что функция ранее не выполнялась.", "Проверить общие обязанности и дополнительные документы до реорганизации.")
    seen_risks = set()
    for chunk in batches(after, 25):
        progress(f"Проверка пересечений и конфликтов: {chunk[0].id}")
        result = provider.risks([f.model_dump() for f in chunk], after_payload)
        for risk in result.risks:
            ids = sorted(set(risk.function_ids))
            if len(ids) < 2 or any(i not in catalog or catalog[i].side != "after" for i in ids) or not set(ids) & {f.id for f in chunk}:
                raise EvidenceError("Риск содержит некорректные ссылки")
            if risk.kind == "duplication" and len({catalog[i].owner for i in ids}) < 2:
                raise EvidenceError("Дублирование требует разных владельцев")
            if risk.kind == "conflict" and len({catalog[i].owner for i in ids}) != 1:
                raise EvidenceError("Самопроверка требует одного владельца")
            key = (risk.kind, tuple(ids))
            if key not in seen_risks:
                seen_risks.add(key)
                add(risk.kind, [], ids, risk.explanation, risk.recommendation)
    if mode == "baseline":
        unit_results = infer_baseline_reorganizations(unit_results, units, findings, catalog)
    counts = dict(Counter(f["kind"] for f in findings))
    result = {"mode":mode, "model":getattr(provider,"model",None), "usage":provider.usage, "calls":provider.calls,
        "documents":[d.model_dump() for d in documents], "functions":[f.model_dump() for f in records],
        "units":{s:[u.model_dump() for u in us.values()] for s,us in units.items()},
        "unit_changes":unit_results, "findings":findings, "counts":counts,
        "coverage":{"before_functions":len(before), "after_functions":len(after), "clauses_processed":len(index)},
        "limitations":["Выводы рекомендательные; наличие точной цитаты не доказывает правильность интерпретации.",
            "Потенциальная потеря означает отсутствие соответствия только в извлечённом каталоге предоставленных документов.",
            "Полнота извлечения функций не гарантируется моделью; требуется проверка аналитика."] +
            (["Лексический тестовый анализ: смысловые конфликты, переименования и разделения требуют дополнительной проверки."] if mode=="baseline" else [])}
    result["report"] = build_report(result)
    return result

def build_report(result, reviews=None):
    reviews = reviews or {}
    engine = f"ИИ-анализ OpenAI; модель: {result['model']}" if result["mode"] == "openai" else "Лексический тестовый анализ"
    lines = ["# Аналитическое заключение", "", f"Метод анализа: {engine}.",
        "Выводы требуют проверки ответственным сотрудником.", "", "## Комплект документов"]
    for d in result["documents"]:
        lines.append(f"- {d['side']}: {d['name']} (SHA-256 {d['sha256']})")
    lines += ["", "## Изменения подразделений и ролей"]
    for u in result["unit_changes"]:
        lines.append(f"- {', '.join(u['before_names']) or '—'} → {', '.join(u['after_names']) or '—'}: {u['explanation']}")
        for e in u["evidence"]:
            lines.append(f"  Источник: {e['document']}, {e['locator']}: «{e['quote']}»")
    lines += ["", "## Сводка"] + [f"- {LABELS[k]}: {v}" for k,v in result["counts"].items()]
    for f in result["findings"]:
        review = reviews.get(f["id"], {"decision":"pending", "comment":""})
        lines += ["", f"## {f['id']}: {f['label']}", f["title"], f["explanation"],
            f"Рекомендация: {f['recommendation']}", f"Проверка: {review['decision']}. {review['comment']}"]
        lines.append("Цитаты и стороны документа проверены автоматически; смысл вывода требует проверки аналитика.")
        if f.get("search_scope"):
            lines.append(f"Область поиска: {', '.join(f['search_scope']['documents'])}; {f['search_scope']['catalog_size']} извлечённых функций.")
            if f["kind"] == "not_found":
                lines.append("Документы «после» не подтверждают отсутствие функции во всей организации.")
            if f["search_scope"].get("owners"):
                lines.append(f"Проверенные владельцы: {', '.join(f['search_scope']['owners'])}.")
            for candidate in f["search_scope"].get("candidates", []):
                lines.append(f"Лексический кандидат для проверки: {candidate['owner']} — {candidate['action']} ({candidate['id']}).")
        for e in f["evidence"]:
            lines += [f"Источник: {e['document']}, {e['locator']} [{e['clause_id']}]", f"> {e['quote']}"]
    lines += ["", "## Ограничения"] + [f"- {s}" for s in result["limitations"]]
    return "\n".join(lines)
