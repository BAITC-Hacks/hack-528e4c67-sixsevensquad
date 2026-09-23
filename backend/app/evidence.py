import re
from .schemas import Evidence, Clause, Extraction

class EvidenceError(ValueError):
    pass

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()

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
