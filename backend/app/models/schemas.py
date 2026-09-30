from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

LABEL = "AI-generated simulation based on public sources."
DISCLAIMER = "This application generates AI simulations based on public sources. Generated responses are not authentic candidate statements."
UNCERTAINTY = "As fontes públicas disponíveis não fornecem evidências suficientes para uma posição simulada confiável sobre este tema."
Phase = Literal["ANSWER", "REBUTTAL", "COUNTER_REBUTTAL"]
SourceType = Literal[
    "government_program",
    "official_website",
    "official_interview",
    "official_speech",
    "debate_transcript",
    "journalism",
    "synthetic_fixture",
]
TIERS = {
    "government_program": 1,
    "official_website": 2,
    "official_interview": 2,
    "official_speech": 2,
    "debate_transcript": 2,
    "journalism": 3,
    "synthetic_fixture": 0,
}


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    quote: str


class Claim(BaseModel):
    text: str
    citations: list[Citation]


class DebateArgumentPlan(BaseModel):
    opponent_point: str
    ideological_lens: str
    disagreement: str
    reasoning_steps: list[str]
    rhetorical_jab: str
    new_angle: str
    factual_anchors: list[Claim]


class ConceptualReply(BaseModel):
    content: str


class CandidateResponse(BaseModel):
    content: str
    candidate_id: str
    phase: Phase
    claims: list[Claim]
    citations: list[Citation]
    confidence: Literal["HIGH", "MEDIUM", "LOW"]


class DebateQuestion(BaseModel):
    content: str
    source_ids: list[str]


class ResearchResult(BaseModel):
    topic: str
    queries: list[str]
    source_ids: list[str]
    evidence: list[dict]
    discoveries: list[dict] = Field(default_factory=list)


class ValidationResult(BaseModel):
    valid: bool
    unsupported_claims: list[str]
    reasons: list[str]


class PolicyPosition(BaseModel):
    area: str
    position: str
    citations: list[Citation]


class RhetoricalProfile(BaseModel):
    recurring_topics: list[str]
    typical_argument_structure: str
    typical_sentence_length: str
    vocabulary_characteristics: list[str]
    debate_patterns: list[str]


class PlaybookPositionDraft(BaseModel):
    area: str = Field(max_length=80)
    position: str = Field(max_length=180)
    chunk_ids: list[str] = Field(min_length=1, max_length=2)


class CandidatePlaybookDraft(BaseModel):
    candidate_id: str
    positions: list[PlaybookPositionDraft] = Field(max_length=8)


class CandidateProfile(BaseModel):
    candidate_id: str
    name: str
    party: str
    policy_positions: list[PolicyPosition]
    rhetorical_profile: RhetoricalProfile
    source_ids: list[str]


class SourceInput(BaseModel):
    candidate_id: str
    title: str = Field(min_length=1, max_length=500)
    url: str
    source_type: SourceType
    publication_date: date | None = None
    publisher: str
    election_year: int | None = None


class DebateConfig(BaseModel):
    candidate_a: str
    candidate_b: str
    topic: str = Field(min_length=2, max_length=300)
    asks_first: Literal["a", "b"] = "a"
    responds_first: Literal["a", "b"] = "b"
    depth: int = Field(default=3, ge=1, le=3)
    max_turns: int = Field(default=1, ge=1, le=5)
    mode: Literal["live", "fixture"] = "live"
    pause_after_round: bool = False
    style_mode: Literal["evidence", "expressive"] = "expressive"

    @model_validator(mode="after")
    def distinct(self):
        if self.candidate_a == self.candidate_b:
            raise ValueError("Select two distinct candidates")
        if self.asks_first == self.responds_first:
            raise ValueError("The asking and responding candidates must differ")
        return self


class DebateMessage(BaseModel):
    id: str
    candidate_id: str
    phase: str
    content: str
    timestamp: str
    label: str = LABEL
    citations: list[dict] = Field(default_factory=list)
    claims: list[dict] = Field(default_factory=list)
    confidence: str = "LOW"
    validation: dict = Field(default_factory=dict)


def now():
    return datetime.now(UTC).isoformat()
