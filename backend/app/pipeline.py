from collections import Counter
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import re
from .schemas import FunctionRecord, Extraction
from .provider import IncompleteResponse
from .evidence import EvidenceError, anchor_extraction, validate_extraction, hydrate

LABELS = {"preserved": "Сохранена", "transferred": "Передана", "split": "Разделена", "changed": "Изменена",
          "not_found": "Потенциальная потеря", "uncertain": "Недостаточно данных", "new": "Без соответствия до",
          "duplication": "Возможное дублирование", "conflict": "Возможный конфликт"}

NUMBER = re.compile(r"^(\d+(?:\.\d+)*)(?:\.\s|\s)")
STRUCTURE = re.compile(r"структур|состав подразделени|организац|бөлім|department|division", re.I)

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
    structural = [c for c in preceding if len(c.text) < 2000 and STRUCTURE.search(c.text)][-2:]
    owner_headers = [c for c in preceding if len(c.text) < 250 and
                     re.match(r"^(?:\d+(?:\.\d+)*[.)]?\s+)?(?:отдел|департамент|управление|служба|директор|начальник|department|division)\b", c.text, re.I) and
                     (c.text.endswith(":") or not re.search(r"вед[её]т|проверя|обеспечива|осуществля", c.text, re.I))][-2:]
    headers = list({c.id: c for c in [*structural, *owner_headers, *headings.values()]}.values())[-8:]
    previous = [c for c in preceding[-6:] if len(c.text) <= 1200][-3:]
    related = []
    for other in related_documents:
        candidates = [c for c in other.clauses if len(c.text) < 2000 and STRUCTURE.search(c.text)]
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

def clause_batches(clauses, limit=8000):
    batch, length = [], 0
    for c in clauses:
        if batch and (length + len(c.text) > limit or len(batch) >= 32):
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
    warnings = []
    incomplete_sides = set()
    jobs = []
    for d in documents:
        offset = 0
        related = [other for other in documents if other.side == d.side and other.id != d.id]
        document_batches = list(clause_batches(d.clauses))
        for number, batch in enumerate(document_batches, 1):
            context = extraction_context(d, offset, batch, related)
            jobs.append((d, batch, context, number, len(document_batches)))
            offset += len(batch)

    extraction_failed = Event()
    def extract_job_inner(job):
        d, batch, context, number, total = job
        progress(f"Извлечение: {d.name}, часть {number} из {total}")
        context_ids = {x["id"] for group in context.values() for x in group}
        valid_context = [c for c in index.values() if c.id in context_ids] + batch
        try:
            result = provider.extract(batch, context)
        except IncompleteResponse:
            if len(batch) < 2:
                raise ValueError("Ответ для одного фрагмента слишком большой. Разделите сложный пункт документа") from None
            progress(f"Делим сложную часть документа {d.name} на меньшие фрагменты")
            middle = len(batch)//2
            results = []
            for part in (batch[:middle], batch[middle:]):
                start = next(i for i,c in enumerate(d.clauses) if c.id == part[0].id)
                related = [other for other in documents if other.side == d.side and other.id != d.id]
                subcontext = extraction_context(d, start, part, related)
                results.append(extract_job_inner((d, part, subcontext, number, total))[1])
            return d, Extraction(units=[u for r in results for u in r.units], functions=[f for r in results for f in r.functions])
        target_ids = {c.id for c in batch}
        for attempt in range(2):
            try:
                anchor_extraction(result, valid_context)
                validate_extraction(result, valid_context)
                retain_target_supported(result, target_ids)
                break
            except EvidenceError as exc:
                if not hasattr(provider, "repair_extraction"):
                    raise EvidenceError(f"Не удалось подтвердить источники: {d.name}, часть {number}. {exc}") from exc
                if attempt:
                    rejected = 0
                    for field in ("units", "functions"):
                        verified = []
                        for item in getattr(result, field):
                            single = Extraction(units=[item] if field == "units" else [], functions=[item] if field == "functions" else [])
                            try:
                                anchor_extraction(single, valid_context)
                                validate_extraction(single, valid_context)
                                verified.append(item)
                            except EvidenceError:
                                rejected += 1
                        setattr(result, field, verified)
                    retain_target_supported(result, target_ids)
                    incomplete_sides.add(d.side)
                    warnings.append(f"{d.name}, часть {number}: исключено записей без проверяемых цитат — {rejected}. Извлечение этой части неполное; проверьте исходный документ.")
                    break
                progress(f"Уточнение цитат: {d.name}, часть {number} из {total}")
                try:
                    result = provider.repair_extraction(batch, context, result, exc)
                except IncompleteResponse:
                    # Keep the original response for the per-record verification above.
                    # A truncated repair must not discard already verified records.
                    warnings.append(f"{d.name}, часть {number}: ответ исправления цитат обрезан; проверены записи исходного ответа.")
        return d, result

    def extract_job(job):
        if extraction_failed.is_set():
            raise EvidenceError("Извлечение остановлено после ошибки другой части; готовые запросы сохранены")
        try:
            return extract_job_inner(job)
        except Exception:
            extraction_failed.set()
            raise

    with ThreadPoolExecutor(max_workers=getattr(provider, "workers", 1)) as workers:
        for d, result in workers.map(extract_job, jobs):
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
    before = [f for f in records if f.side == "before"]
    after = [f for f in records if f.side == "after"]
    if not before or not after:
        raise ValueError("Не удалось извлечь функции с обеих сторон. Проверьте содержимое документов")
    if len(records) > 700:
        raise ValueError("Слишком большой каталог для MVP (максимум 700 функций). Разделите анализ")
    catalog = {f.id:f for f in records}
    # Provider sends compact functions; verified evidence is hydrated server-side.
    after_payload = [f.model_dump() for f in after]
    progress("Сопоставление подразделений и должностей")
    unit_changes = provider.units([u.model_dump() for u in units["before"].values()], [u.model_dump() for u in units["after"].values()])
    covered_units = {"before":set(), "after":set()}
    unit_results = []
    for side, label in (("before", "до"), ("after", "после")):
        if not units[side]:
            warnings.append(f"Не извлечён реестр подразделений и ролей {label}; сравнение структуры неполное. Проверьте приложения с оргструктурой.")
    for change in unit_changes.changes:
        b, a = change.before_names, change.after_names
        invalid = (not b and not a) or any(n not in units["before"] for n in b) or any(n not in units["after"] for n in a)
        invalid = invalid or len(set(b)) != len(b) or len(set(a)) != len(a) or bool(set(b) & covered_units["before"] or set(a) & covered_units["after"])
        invalid = invalid or (change.status in {"preserved", "reorganized"} and (not b or not a))
        invalid = invalid or (change.status == "created" and (b or not a)) or (change.status == "not_found" and (a or not b))
        if not invalid and b and a:
            invalid = {units["before"][n].kind for n in b} != {units["after"][n].kind for n in a}
        if invalid:
            warnings.append("Некорректное сопоставление подразделений исключено; непокрытые записи требуют проверки.")
            continue
        covered_units["before"].update(b); covered_units["after"].update(a)
        evidence = [e for s,names in [("before", b), ("after", a)] for n in names for e in units[s][n].evidence]
        row = {**change.model_dump(), "evidence": hydrate(evidence, index)}
        if ((change.status == "not_found" and "after" in incomplete_sides) or
                (change.status == "created" and "before" in incomplete_sides)):
            row.update(status="uncertain", explanation="Извлечение противоположной редакции неполное. Нельзя установить отсутствие или создание подразделения; требуется ручная проверка.")
        unit_results.append(row)
    for side in ("before", "after"):
        for name in sorted(set(units[side]) - covered_units[side]):
            unit_results.append({"before_names":[name] if side == "before" else [],
                "after_names":[name] if side == "after" else [], "status":"uncertain",
                "explanation":"Модель не дала проверяемого сопоставления этой записи. Требуется ручная проверка; это не потеря и не создание подразделения.",
                "evidence":hydrate(units[side][name].evidence, index)})
            warnings.append("Сопоставление части подразделений неполное: такие записи отмечены «Недостаточно данных».")
    if hasattr(provider, "unit_changes"):
        provider.unit_changes = [{k:v for k,v in item.items() if k != "evidence"} for item in unit_results]
    findings, used_after = [], set()
    def add(kind, b, a, explanation, recommendation):
        fs = [catalog[i] for i in b+a]
        evidence = list({(e.clause_id, e.quote): e for f in fs for e in f.evidence}.values())
        cited = hydrate(evidence, index)
        sides = {e["side"] for e in cited}
        if kind == "uncertain":
            required = ({"before"} if b else set()) | ({"after"} if a else set())
        elif kind == "not_found":
            required = {"before"}
        elif kind in {"new", "duplication", "conflict"}:
            required = {"after"}
        else:
            required = {"before", "after"}
        if not required <= sides:
            raise EvidenceError("Вывод не подтверждён источниками нужных редакций")
        search_scope = None
        if kind in {"not_found", "new", "uncertain"}:
            pool = after if b else before
            source = catalog[(b or a)[0]]
            search_scope = {"documents": [d.name for d in documents if d.side == ("after" if b else "before")],
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
        if set(returned) - expected:
            warnings.append("Лишние ссылки в ответе сопоставления функций исключены.")
        for function in chunk:
            candidates = [m for m in result.matches if m.before_id == function.id]
            m = candidates[0] if len(candidates) == 1 else None
            invalid = m is None
            if m is not None:
                invalid = any(i not in catalog or catalog[i].side != "after" for i in m.after_ids)
                invalid = invalid or len(set(m.after_ids)) != len(m.after_ids)
                invalid = invalid or (m.status == "not_found" and bool(m.after_ids))
                invalid = invalid or (m.status in {"preserved", "transferred", "changed"} and len(m.after_ids) != 1)
                invalid = invalid or (m.status == "split" and len(set(m.after_ids)) < 2)
                invalid = invalid or (m.status == "uncertain" and len(m.after_ids) > 3)
            if invalid:
                add("uncertain", [function.id], [], "Модель пропустила функцию или вернула некорректные связи. Соответствие не проверено.", "Проверить функцию по документам обеих редакций вручную.")
                warnings.append("Часть функций требует ручного сопоставления из-за неполного ответа модели.")
                continue
            used_after.update(m.after_ids)
            if m.status == "not_found" and "after" in incomplete_sides:
                add("uncertain", [m.before_id], [], "Извлечение редакции после неполное: отсутствие соответствия пока нельзя оценить.", "Проверить пропущенные фрагменты новой редакции.")
            else:
                add(m.status, [m.before_id], list(dict.fromkeys(m.after_ids)), m.explanation, m.recommendation)
    for f in after:
        if f.id not in used_after:
            add("uncertain" if "before" in incomplete_sides else "new", [], [f.id], "В извлечённом каталоге до не установлено соответствие. Это не доказывает, что функция ранее не выполнялась.", "Проверить общие обязанности и дополнительные документы до реорганизации.")
    seen_risks = set()
    for chunk in batches(after, 25):
        progress(f"Проверка пересечений и конфликтов: {chunk[0].id}")
        result = provider.risks([f.model_dump() for f in chunk], after_payload)
        for risk in result.risks:
            ids = sorted(set(risk.function_ids))
            if len(ids) < 2 or any(i not in catalog or catalog[i].side != "after" for i in ids) or not set(ids) & {f.id for f in chunk}:
                warnings.append("Кандидат риска с некорректными источниками исключён; проверка рисков неполна.")
                continue
            if risk.kind == "duplication" and len({catalog[i].owner for i in ids}) < 2:
                warnings.append("Кандидат дублирования у одного владельца исключён.")
                continue
            if risk.kind == "conflict" and len({catalog[i].owner for i in ids}) != 1:
                warnings.append("Кандидат самопроверки с разными владельцами исключён.")
                continue
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
        "coverage":{"before_functions":len(before), "after_functions":len(after), "clauses_processed":len(index), "incomplete_sides":sorted(incomplete_sides)},
        "limitations":["Выводы рекомендательные; наличие точной цитаты не доказывает правильность интерпретации.",
            "Потенциальная потеря означает отсутствие соответствия только в извлечённом каталоге предоставленных документов.",
            "Полнота извлечения функций не гарантируется моделью; требуется проверка аналитика."] +
            (["Лексический тестовый анализ: смысловые конфликты, переименования и разделения требуют дополнительной проверки."] if mode=="baseline" else [])}
    result["warnings"] = sorted(set(warnings))
    result["limitations"].extend(result["warnings"])
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
