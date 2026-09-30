from typing import TypedDict


class DebateState(TypedDict, total=False):
    session_id: str
    topic: str
    candidate_a: str
    candidate_b: str
    current_speaker: str
    current_phase: str
    question: str
    messages: list[dict]
    retrieved_context: list[dict]
    citations: list[dict]
    turn_number: int
    max_turns: int
    debate_config: dict
    research: dict
    profiles: dict
    execution_metadata: list[dict]
    round_complete: bool
    pending_response: dict
    response: dict
    retries: int
    validation: dict
    provider_tokens: int
    candidate_metadata: list[dict]
    validation_history: list[dict]
    dialogue_context: dict
    retrieval_query: str
    phase_web_research: dict
    web_research_history: list[dict]

    argument_fallback: bool

    argument_plan: dict
