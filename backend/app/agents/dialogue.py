import re
from difflib import SequenceMatcher

from app.config.catalog import candidate


def question_participants(state):
    cid = state["candidate_a"] if state["debate_config"]["asks_first"] == "a" else state["candidate_b"]
    if state["turn_number"] % 2:
        cid = state["candidate_b"] if cid == state["candidate_a"] else state["candidate_a"]
    target = state["candidate_b"] if cid == state["candidate_a"] else state["candidate_a"]
    return cid, target


def dialogue_context(state):
    cid = state["current_speaker"]
    opponent = state["candidate_b"] if cid == state["candidate_a"] else state["candidate_a"]
    messages = state.get("messages", [])
    previous = [m for m in messages if m["candidate_id"] == cid and m["phase"] != "QUESTION"]
    opposing = [m for m in messages if m["candidate_id"] == opponent]
    return {
        "opponent_id": opponent,
        "opponent_name": candidate(opponent)["name"],
        "latest_opponent_message": opposing[-1] if opposing else None,
        "previous_own_responses": previous,
        "recent_exchange": messages[-4:],
    }


def retrieval_query(state, context):
    message = context["latest_opponent_message"] or {}
    claims = [c["text"] for c in message.get("claims", [])]
    focus = " ".join(claims) or message.get("content", "")
    return f"{state['topic']}. Argumento a responder: {focus[:900]}"


def repeated_response(content, previous):
    def normalize(text):
        return re.sub(r"\W+", " ", text.casefold()).strip()

    text = normalize(content)
    return any(SequenceMatcher(None, text, normalize(m["content"])).ratio() >= 0.98 for m in previous)


def ideological_direction(cid):
    # User-directed dramatic framing; specific promises still require documentary evidence.
    return {
        "lula": "Left-wing framing: collective protection, social rights, public services and state responsibility; challenge the claim that markets or individual choice alone solve social harms.",
        "flavio": "Right-wing framing: individual autonomy, economic freedom, fiscal responsibility and skepticism of excessive state control; challenge broad state promises and argue practical responsibility.",
    }.get(
        cid,
        "Derive the political values, view of state and markets, and policy priorities from this candidate's supplied program playbook. Do not invent an ideological label.",
    )
