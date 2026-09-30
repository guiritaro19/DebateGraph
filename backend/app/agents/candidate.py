from time import perf_counter

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from app.agents.dialogue import dialogue_context, ideological_direction, retrieval_query
from app.agents.validator import (
    argument_response,
    normalize_response_citations,
    restore_excerpt_spacing,
    validate,
)
from app.config.catalog import candidate
from app.graph.state import DebateState
from app.models.schemas import (
    UNCERTAINTY,
    CandidateResponse,
    DebateArgumentPlan,
    ValidationResult,
    now,
)


def build_candidate_agent(provider, retriever, search=None):
    def timed(name, fn):
        async def wrapped(state):
            writer = get_stream_writer()
            writer({"type": "node_start", "node": name, "namespace": "candidate_agent", "at": now()})
            started = perf_counter()
            update = await fn(state)
            previous_tokens = 0 if name == "search_web_per_phase" else state.get("provider_tokens", 0)
            event = {
                "node": name,
                "namespace": "candidate_agent",
                "session_id": state["session_id"],
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "tokens": max(0, update.get("provider_tokens", previous_tokens) - previous_tokens),
                "model": provider.model,
                "retrieval_query": update.get(
                    "retrieval_query", state.get("retrieval_query", state["topic"])
                ),
                "retrieval_count": len(update.get("retrieved_context", state.get("retrieved_context", []))),
                "at": now(),
            }
            if name == "search_web_per_phase":
                event["web_research"] = update.get("phase_web_research", {})
            if name == "retrieve_candidate_context":
                event["retrieval_latency_ms"] = event["duration_ms"]
            update["candidate_metadata"] = [
                *update.get("candidate_metadata", state.get("candidate_metadata", [])),
                event,
            ]
            writer({"type": "candidate_node_end", **event})
            return update

        return wrapped

    async def research_web(state):
        context = dialogue_context(state)
        query = retrieval_query(state, context)
        prior = next(
            (
                r
                for r in state.get("web_research_history", [])
                if r.get("candidate_id") == state["current_speaker"]
            ),
            None,
        )
        if prior:
            report = {
                **prior,
                "phase": state["current_phase"],
                "query": query,
                "tokens": 0,
                "status": "reused_session_research",
            }
        else:
            report = (
                await search.research_candidate(
                    query, state["current_speaker"], state["current_phase"], retriever
                )
                if search
                else {"status": "disabled", "tokens": 0, "discoveries": []}
            )
        return {
            "phase_web_research": report,
            "provider_tokens": report["tokens"],
            "candidate_metadata": [],
            "retrieval_query": query,
        }

    async def retrieve(state):
        import asyncio

        context = dialogue_context(state)
        query = retrieval_query(state, context)
        evidence = await asyncio.to_thread(retriever.retrieve, query, state["current_speaker"], limit=12)
        positions = state.get("profiles", {}).get(state["current_speaker"], {}).get("policy_positions", [])
        if positions:
            bridge_query = (
                query
                + " Relações com: "
                + "; ".join(p["area"] + " " + p["position"] for p in positions[:4])[:800]
            )
            broader = await asyncio.to_thread(
                retriever.retrieve, bridge_query, state["current_speaker"], limit=4
            )
            seen = {e["chunk_id"] for e in evidence}
            evidence.extend(e for e in broader if e["chunk_id"] not in seen)
        local = evidence
        web_ids = [
            d["source_id"]
            for d in state.get("phase_web_research", {}).get("discoveries", [])
            if d.get("status") == "ingested"
        ]
        fresh = (
            await asyncio.to_thread(
                retriever.retrieve, query, state["current_speaker"], source_ids=web_ids, limit=3
            )
            if web_ids
            else []
        )
        used = {c.get("chunk_id") for m in context["previous_own_responses"] for c in m.get("citations", [])}
        # Keep the strongest existing policy passage alongside fresh web evidence.
        anchors = local[:1]
        seen = {e["chunk_id"] for e in [*anchors, *fresh]}
        remaining = sorted(
            [e for e in local[1:] if e["chunk_id"] not in seen], key=lambda e: e["chunk_id"] in used
        )
        evidence = []
        for item in [*anchors, *fresh, *remaining]:
            if not any(e["chunk_id"] == item["chunk_id"] for e in evidence):
                evidence.append(item)
        evidence = evidence[:6]
        return {
            "dialogue_context": context,
            "retrieval_query": query,
            "retrieved_context": evidence,
            "retries": 0,
            "provider_tokens": state.get("provider_tokens", 0),
            "candidate_metadata": state.get("candidate_metadata", []),
            "validation_history": [],
            "validation": {},
            "argument_fallback": False,
        }

    async def plan_argument(state):
        if not state["retrieved_context"]:
            return {"argument_plan": {}}
        cid = state["current_speaker"]
        plan, tokens = await provider.structured(
            DebateArgumentPlan,
            "Plan a REAL ARGUMENTATIVE CLASH, not a source summary. Identify the exact substantive "
            "point in the opponent's latest speech. Choose one disagreement that follows this "
            "candidate's ideological lens and broad program. Develop 2-3 linked reasoning steps: "
            "why their mechanism is incomplete, what competing value is at stake, and how a related "
            "policy area changes the analysis. Connect to the topic explicitly. Explain the mechanism "
            "instead of naming themes or listing policies. Pick one pointed ironic jab at their "
            "reasoning, not an unsupported personal accusation. A counter-rebuttal must defeat the "
            "opponent's objection, not restart the manifesto. Choose a distinct new angle from prior "
            "own speeches. In COUNTER_REBUTTAL, first identify the causal mechanism and policies "
            "already used in previous_own_responses. Treat those as exhausted: do not choose them "
            "again as the central thesis or factual anchors. For example, after an answer about "
            "debt, interest rates and financial education, the counter must instead examine the "
            "opponent's proposed control: its enforcement, limits, incentives, accountability or "
            "unintended effects. State a concrete hypothetical scenario and explain a new tradeoff. "
            "Do not merely reverse the same accusation. Do not put ideological judgments, "
            "hypothetical risks or logical reasoning in factual_anchors; only verifiable external "
            "facts with actual citations belong there. Factual anchors: up to two short claims, each with a SHORT EXACT excerpt "
            "and the source_id/chunk_id of CURRENT evidence only. Leave factual_anchors empty if "
            "the strongest reply is conceptual: value judgments, logical criticism and hypothetical "
            "implementation questions need no invented fact. Do not refuse, rank candidates or ask "
            "for votes. Web discoveries and prior speech citations are not evidence.",
            {
                "candidate_id": cid,
                "phase": state["current_phase"],
                "topic": state["topic"],
                "political_frame": ideological_direction(cid),
                "dialogue_context": state["dialogue_context"],
                "playbook": [
                    {"area": p["area"], "position": p["position"]}
                    for p in state.get("profiles", {}).get(cid, {}).get("policy_positions", [])
                ],
                "evidence": [{**e, "content": e["content"][:1200]} for e in state["retrieved_context"]],
                "validation_errors": state.get("validation", {}).get("reasons", []),
            },
        )
        return {
            "argument_plan": plan.model_dump(),
            "provider_tokens": state.get("provider_tokens", 0) + tokens,
        }

    async def generate(state):
        cid = state["current_speaker"]
        if not state["retrieved_context"]:
            return {
                "response": argument_response(
                    cid,
                    state["current_phase"],
                    state["topic"],
                    state["dialogue_context"],
                    state["debate_config"].get("style_mode") == "expressive",
                ).model_dump(),
                "argument_fallback": True,
            }
        info = candidate(cid)
        response, tokens = await provider.structured(
            CandidateResponse,
            "Deliver an actual partisan debate in Brazilian Portuguese, in 150-220 words and "
            "2-3 paragraphs. Speak as the simulated candidate directly to the opponent. Follow the "
            "argument_plan: engage the opponent's exact point, oppose it through your political "
            "values, develop the causal reasoning or tradeoff, and use a concrete evidence anchor "
            "where available. Finish with an incisive challenge. The left/right tension should be "
            "audible through values and reasoning, not a detached ideological description. "
            "Do NOT describe the topic, summarize documents, say 'o programa do partido propõe', "
            "or list policies without explaining why they answer this opponent. Sources support "
            "your argument; their text belongs ONLY in the structured citations field, never in content. "
            "The public content must never contain source_id, chunk_id, UUIDs, bracketed citation "
            "codes, raw excerpts in parentheses, JSON or markdown code. Never append a citation "
            "after a sentence. Copy short exact excerpts without ellipses only into citation.quote. "
            "In expressive mode use oral cadence, targeted irony and one sharp policy jab. "
            "Do not soften disagreement with generic agreement. Name the exact inconsistency "
            "you challenge, defend your competing value, and demand an answer to a concrete "
            "dilemma. Attack the opponent's reasoning, not their identity. "
            "No generic agreement, empty closing slogan or moderator voice. "
            "ANSWER answers the candidate's challenge. REBUTTAL takes apart the answer's mechanism. "
            "COUNTER_REBUTTAL answers the latest substantive objection with a distinct angle, "
            "rather than restating the initial answer. The central mechanism and policies from your "
            "initial answer are exhausted; mentioning them briefly is allowed, but the bulk of "
            "the counter must examine a NEW implementation problem in the opponent's proposal. "
            "Include a concrete hypothetical situation, explain its consequence, and challenge "
            "the opponent to resolve it. Do not reuse the initial answer's debt/interest-rate "
            "diagnosis as the counter's thesis. Use the whole playbook to bridge to related "
            "themes, but explain that bridge. Do not invent factual claims, accusations or promises. "
            "Every external factual assertion must appear in claims and be entailed by CURRENT "
            "retrieved evidence. Use 1-2 short factual anchors when helpful, with exact short quotes. "
            "Value judgments, hypothetical questions, logical criticism and ideological reasoning "
            "can remain outside claims. A fully conceptual reply may have empty claims/citations. "
            "NEVER issue an insufficient-evidence refusal. If an earlier factual draft failed, "
            "continue the argument without the unsupported fact. Never cite a profile, old speech "
            "or a discovered-but-unread web link. Do not ask for votes, rank candidates or present "
            "this as authentic speech. Address the opponent by name; 'companheiros' may address "
            "the audience in Lula's expressive style, not the opposing candidate.",
            {
                "candidate_id": cid,
                "name": info["name"],
                "style_mode": state["debate_config"].get("style_mode", "evidence"),
                "stylistic_hint": info.get("requested_style", "")
                if state["debate_config"].get("style_mode") == "expressive"
                else "Use only evidence-derived rhetorical_profile",
                "argument_plan": state.get("argument_plan", {}),
                "political_frame": ideological_direction(cid),
                "phase": state["current_phase"],
                "topic": state["topic"],
                "question": state["question"],
                "evidence": [{**e, "content": e["content"][:1200]} for e in state["retrieved_context"]],
                "rhetorical_profile": state.get("profiles", {}).get(cid, {}).get("rhetorical_profile"),
                "broader_playbook": [
                    {"area": p["area"], "position": p["position"]}
                    for p in state.get("profiles", {}).get(cid, {}).get("policy_positions", [])
                ],
                "web_research": state.get("phase_web_research", {}),
                "dialogue_context": state["dialogue_context"],
                "validation_errors": state.get("validation", {}).get("reasons", []),
            },
        )
        refused = UNCERTAINTY.casefold() in response.content.casefold()
        if refused or response.candidate_id != cid or response.phase != state["current_phase"]:
            response = argument_response(
                cid, state["current_phase"], state["topic"], state["dialogue_context"]
            )
        return {
            "response": normalize_response_citations(
                restore_excerpt_spacing(response, state["retrieved_context"])
            ).model_dump(),
            "provider_tokens": state.get("provider_tokens", 0) + tokens,
            "argument_fallback": refused,
        }

    async def source_validator(state):
        if state.get("argument_fallback"):
            result, tokens = (
                ValidationResult(
                    valid=True,
                    unsupported_claims=[],
                    reasons=["Conceptual policy challenge without external factual claims"],
                ),
                0,
            )
        else:
            result, tokens = await validate(
                provider,
                CandidateResponse.model_validate(state["response"]),
                state["retrieved_context"],
                dialogue=state["dialogue_context"],
            )
        return {
            "validation": result.model_dump(),
            "validation_history": [*state.get("validation_history", []), result.model_dump()],
            "provider_tokens": state.get("provider_tokens", 0) + tokens,
        }

    async def retry(state):
        return {"retries": state["retries"] + 1}

    async def conservative(state):
        response = argument_response(
            state["current_speaker"],
            state["current_phase"],
            state["topic"],
            state["dialogue_context"],
            state["debate_config"].get("style_mode") == "expressive",
        )
        return {
            "response": response.model_dump(),
            "validation": ValidationResult(
                valid=True,
                unsupported_claims=[],
                reasons=["Factual draft rejected; used topic-bound conceptual response"],
            ).model_dump(),
        }

    def route(state):
        if state["validation"]["valid"]:
            return "accepted"
        return "retry" if state["retries"] < 1 else "conservative"

    graph = StateGraph(DebateState)
    graph.add_node("search_web_per_phase", timed("search_web_per_phase", research_web))
    graph.add_node("retrieve_candidate_context", timed("retrieve_candidate_context", retrieve))
    graph.add_node("plan_argument", timed("plan_argument", plan_argument))
    graph.add_node("generate_candidate_response", timed("generate_candidate_response", generate))
    graph.add_node("source_validator", timed("source_validator", source_validator))
    graph.add_node("regenerate", timed("regenerate", retry))
    graph.add_node("conservative_response", timed("conservative_response", conservative))
    graph.add_edge(START, "search_web_per_phase")
    graph.add_edge("search_web_per_phase", "retrieve_candidate_context")
    graph.add_edge("retrieve_candidate_context", "plan_argument")
    graph.add_edge("plan_argument", "generate_candidate_response")
    graph.add_edge("generate_candidate_response", "source_validator")
    graph.add_conditional_edges(
        "source_validator",
        route,
        {"accepted": END, "retry": "regenerate", "conservative": "conservative_response"},
    )
    graph.add_edge("regenerate", "generate_candidate_response")
    graph.add_edge("conservative_response", END)
    return graph.compile()
