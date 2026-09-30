from app.agents.dialogue import ideological_direction, question_participants
from app.config.catalog import candidate
from app.models.schemas import DebateQuestion


async def generate_question(provider, state):
    asker, target = question_participants(state)
    info = candidate(asker)
    result, tokens = await provider.structured(
        DebateQuestion,
        "You are the ASKING CANDIDATE, not a moderator. Address the opposing candidate by name, "
        "in the second person, with one concrete policy challenge about the topic (40-70 words). "
        "Make the candidate's political values and disagreement audible in the challenge; do not merely "
        "describe a policy topic. Never ask about both candidates in the third person. In expressive mode, use the asker's "
        "stylistic hint and a sharp nonfactual jab about the policy tradeoff. No unsupported premises, "
        "accusations or invented positions. Ask about implementation and expose a policy tradeoff, "
        "not a general survey of proposals. Address the opponent by name, not 'companheiro'; "
        "'companheiros' can address the audience separately. Use past exchange to ask a different question in later rounds.",
        {
            "topic": state["topic"],
            "asker": info,
            "opponent": candidate(target),
            "political_frame": ideological_direction(asker),
            "playbook": state.get("profiles", {}).get(asker, {}).get("policy_positions", []),
            "style_mode": state["debate_config"].get("style_mode", "evidence"),
            "recent_exchange": state.get("messages", [])[-4:],
            "evidence": [
                {**e, "content": e["content"][:900]}
                for e in state.get("research", {}).get("evidence", [])[:8]
            ],
        },
    )
    allowed = set(state.get("research", {}).get("source_ids", []))
    if not set(result.source_ids).issubset(allowed):
        raise ValueError("Question cited unavailable sources")
    return result, tokens
