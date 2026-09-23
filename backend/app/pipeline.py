from collections import Counter
from .schemas import FunctionRecord
from .evidence import EvidenceError, validate_extraction, hydrate

LABELS = {"preserved": "Сохранена", "transferred": "Передана", "split": "Разделена", "changed": "Изменена",
          "not_found": "Потенциальная потеря", "new": "Без соответствия до", "duplication": "Возможное дублирование", "conflict": "Возможный конфликт"}

def batches(items, size):
    for i in range(0, len(items), size):
        yield items[i:i+size]

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
        previous = []
        # Headers are context only, every document clause is still processed as target.
        headers = [c.model_dump() for c in d.clauses if len(c.text) < 220 or c.text.endswith(":")]
        related = [c.model_dump() for other in documents if other.side == d.side and other.id != d.id
                   for c in other.clauses if len(c.text) < 220 or c.text.endswith(":")]
        for number, batch in enumerate(clause_batches(d.clauses), 1):
            progress(f"Извлечение: {d.name}, часть {number}")
            context = {"headers": headers, "previous": previous, "related_headers": related}
            context_ids = {x["id"] for x in headers + previous + related}
            valid_context = [c for c in index.values() if c.id in context_ids] + batch
            result = provider.extract(batch, context)
            validate_extraction(result, valid_context)
            target_ids = {c.id for c in batch}
            for item in result.functions:
                if not any(e.clause_id in target_ids for e in item.evidence):
                    raise EvidenceError("Функция не имеет доказательства в обрабатываемом фрагменте")
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
            previous = (previous + [c.model_dump() for c in batch])[-12:]
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
        if change.status in {"preserved", "reorganized"} and (not b or not a):
            raise EvidenceError("Изменение подразделения требует обеих сторон")
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
        findings.append({"id": f"finding-{len(findings)+1}", "kind":kind, "label": LABELS[kind],
            "before_ids": b, "after_ids": a, "title": f"{fs[0].action} — {fs[0].object}",
            "explanation":explanation, "recommendation":recommendation,
            "requires_review":True, "evidence":hydrate(evidence,index),
            "search_scope": {"documents":[d.name for d in documents if d.side == ("after" if kind == "not_found" else "before")],
                             "catalog_size":len(after) if kind == "not_found" else len(before)} if kind in {"not_found", "new"} else None})
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
            if (m.status == "not_found") != (len(m.after_ids) == 0):
                raise EvidenceError("Статус и связи функции противоречат друг другу")
            if m.status == "split" and len(set(m.after_ids)) < 2:
                raise EvidenceError("Разделение требует двух функций-получателей")
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
            key = (risk.kind, tuple(ids))
            if key not in seen_risks:
                seen_risks.add(key)
                add(risk.kind, [], ids, risk.explanation, risk.recommendation)
    counts = dict(Counter(f["kind"] for f in findings))
    result = {"mode":mode, "model":getattr(provider,"model",None), "usage":provider.usage, "calls":provider.calls,
        "documents":[d.model_dump() for d in documents], "functions":[f.model_dump() for f in records],
        "units":{s:[u.model_dump() for u in us.values()] for s,us in units.items()},
        "unit_changes":unit_results, "findings":findings, "counts":counts,
        "coverage":{"before_functions":len(before), "after_functions":len(after), "clauses_processed":len(index)},
        "limitations":["Выводы рекомендательные; наличие точной цитаты не доказывает правильность интерпретации.",
            "Потенциальная потеря означает отсутствие соответствия только в извлечённом каталоге предоставленных документов.",
            "Полнота извлечения функций не гарантируется моделью; требуется проверка аналитика."] +
            (["Лексический режим без ИИ: смысловые конфликты, переименования и разделения не выявляются надёжно."] if mode=="baseline" else [])}
    result["report"] = build_report(result)
    return result

def build_report(result, reviews=None):
    reviews = reviews or {}
    lines = ["# Аналитическое заключение", "", f"Режим: {result['mode']}; модель: {result['model'] or 'без ИИ'}.",
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
        if f.get("search_scope"):
            lines.append(f"Область поиска: {', '.join(f['search_scope']['documents'])}; {f['search_scope']['catalog_size']} извлечённых функций.")
        for e in f["evidence"]:
            lines += [f"Источник: {e['document']}, {e['locator']} [{e['clause_id']}]", f"> {e['quote']}"]
    lines += ["", "## Ограничения"] + [f"- {s}" for s in result["limitations"]]
    return "\n".join(lines)
