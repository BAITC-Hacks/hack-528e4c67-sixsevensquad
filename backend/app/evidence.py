import re
from difflib import SequenceMatcher
from .schemas import Evidence, Clause, Extraction

class EvidenceError(ValueError):
    pass

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

def exact_source_quote(source: str, proposed: str, max_length: int = 1200) -> str:
    """Return an exact excerpt from the source even if the model paraphrased it."""
    if proposed in source:
        return proposed
    words = proposed.split()
    if words:
        flexible = re.compile(r"\s+".join(re.escape(word) for word in words), re.IGNORECASE)
        match = flexible.search(source)
        if match:
            return match.group(0)
    if len(source) <= max_length:
        return source
    pieces = [piece.strip() for piece in re.split(r"(?<=[.!?;:])\s+", source) if len(piece.strip()) >= 8]
    if not pieces:
        return source[:max_length]
    target = normalize(proposed).lower()
    target_words = set(re.findall(r"[а-яёa-z]{3,}", target))
    def score(piece):
        clean = normalize(piece).lower()
        words = set(re.findall(r"[а-яёa-z]{3,}", clean))
        overlap = len(target_words & words) / max(1, len(target_words | words))
        return max(overlap, SequenceMatcher(None, target[:800], clean[:800]).ratio())
    best = max(pieces, key=score)
    return best if len(best) <= max_length else best[:max_length].rsplit(" ", 1)[0]

def anchor_extraction(result: Extraction, clauses: list[Clause]) -> None:
    """Resolve model citations to exact server-owned excerpts by clause ID."""
    index = {c.id: c for c in clauses}
    for item in [*result.units, *result.functions]:
        for evidence in item.evidence:
            clause = index.get(evidence.clause_id)
            if clause is None:
                raise EvidenceError(f"Несуществующий источник: {evidence.clause_id}")
            evidence.quote = exact_source_quote(clause.text, evidence.quote)

def validate_evidence(evidence: list[Evidence], clauses: dict[str, Clause]) -> None:
    for e in evidence:
        clause = clauses.get(e.clause_id)
        if not clause or normalize(e.quote) not in normalize(clause.text):
            raise EvidenceError(f"Неподтверждённая цитата: {e.clause_id}")

def validate_extraction(result: Extraction, clauses: list[Clause]) -> None:
    index = {c.id: c for c in clauses}
    for item in [*result.units, *result.functions]:
        validate_evidence(item.evidence, index)

def hydrate(evidence: list[Evidence], index: dict[str, Clause]) -> list[dict]:
    validate_evidence(evidence, index)
    return [{**e.model_dump(), **index[e.clause_id].model_dump(), "clause_id": e.clause_id} for e in evidence]
