import re
from .schemas import Evidence, Clause, Extraction

class EvidenceError(ValueError):
    pass

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def exact_source_quote(source: str, proposed: str, max_length: int = 1200) -> str:
    """Accept verbatim text or whitespace/case differences, never a paraphrase."""
    if len(normalize(proposed)) < 8:
        raise EvidenceError("Цитата слишком короткая или состоит из пробелов")
    if proposed in source:
        return proposed
    words = proposed.split()
    if words:
        flexible = re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)
        match = flexible.search(source)
        if match:
            return match.group(0)
    raise EvidenceError("Цитата отсутствует в указанном фрагменте; пересказ нельзя выдавать за источник")

def anchor_extraction(result: Extraction, clauses: list[Clause]) -> None:
    """Resolve model citations to exact server-owned excerpts by clause ID."""
    index = {c.id: c for c in clauses}
    for item in [*result.units, *result.functions]:
        for evidence in item.evidence:
            clause = index.get(evidence.clause_id)
            if clause is None:
                raise EvidenceError(f"Несуществующий источник: {evidence.clause_id}")
            try:
                evidence.quote = exact_source_quote(clause.text, evidence.quote)
            except EvidenceError:
                # Correct a mistaken locator only for a unique verbatim match.
                matches = []
                for candidate in clauses:
                    try:
                        matches.append((candidate, exact_source_quote(candidate.text, evidence.quote)))
                    except EvidenceError:
                        continue
                unique = {candidate.id:(candidate,quote) for candidate,quote in matches}
                if len(unique) != 1:
                    raise
                candidate, quote = next(iter(unique.values()))
                evidence.clause_id, evidence.quote = candidate.id, quote

def validate_evidence(evidence: list[Evidence], clauses: dict[str, Clause]) -> None:
    for e in evidence:
        clause = clauses.get(e.clause_id)
        if not clause or len(normalize(e.quote)) < 8 or normalize(e.quote) not in normalize(clause.text):
            raise EvidenceError(f"Неподтверждённая цитата: {e.clause_id}")

def validate_extraction(result: Extraction, clauses: list[Clause]) -> None:
    index = {c.id: c for c in clauses}
    for item in [*result.units, *result.functions]:
        validate_evidence(item.evidence, index)

def hydrate(evidence: list[Evidence], index: dict[str, Clause]) -> list[dict]:
    validate_evidence(evidence, index)
    return [{**e.model_dump(), **index[e.clause_id].model_dump(), "clause_id": e.clause_id} for e in evidence]
