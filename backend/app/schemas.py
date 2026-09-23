from typing import Literal
from pydantic import BaseModel, Field

Side = Literal["before", "after"]

class Clause(BaseModel):
    id: str
    document: str
    side: Side
    locator: str
    text: str

class Document(BaseModel):
    id: str
    name: str
    side: Side
    sha256: str
    clauses: list[Clause]

class Evidence(BaseModel):
    clause_id: str
    quote: str = Field(min_length=8)

class Unit(BaseModel):
    name: str = Field(min_length=2)
    kind: Literal["department", "role", "organization"]
    evidence: list[Evidence] = Field(min_length=1)

class Function(BaseModel):
    owner: str = Field(min_length=2)
    action: str = Field(min_length=2)
    object: str = Field(min_length=2)
    scope: str = Field(min_length=2)
    evidence: list[Evidence] = Field(min_length=1)

class Extraction(BaseModel):
    units: list[Unit]
    functions: list[Function]

class FunctionRecord(Function):
    id: str
    side: Side

class Match(BaseModel):
    before_id: str
    after_ids: list[str]
    status: Literal["preserved", "transferred", "split", "changed", "not_found", "uncertain"]
    explanation: str
    recommendation: str

class Matches(BaseModel):
    matches: list[Match]

class Risk(BaseModel):
    kind: Literal["duplication", "conflict"]
    function_ids: list[str] = Field(min_length=2)
    explanation: str
    recommendation: str

class Risks(BaseModel):
    risks: list[Risk]

class UnitChange(BaseModel):
    before_names: list[str]
    after_names: list[str]
    status: Literal["preserved", "reorganized", "created", "not_found", "uncertain"]
    explanation: str

class UnitChanges(BaseModel):
    changes: list[UnitChange]

class AnalysisRequest(BaseModel):
    mode: Literal["openai", "baseline"] = "openai"

class Review(BaseModel):
    decision: Literal["pending", "confirmed", "rejected"]
    comment: str = Field(default="", max_length=3000)
