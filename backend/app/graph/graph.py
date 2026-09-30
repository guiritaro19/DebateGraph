import asyncio
import codecs
from time import perf_counter
from uuid import uuid4

import tiktoken
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents.candidate import build_candidate_agent
from app.agents.dialogue import question_participants
from app.agents.question import generate_question
from app.agents.research import build_research_agent
from app.config.catalog import candidate
from app.graph.routing import route_next_phase, route_round
from app.graph.state import DebateState
from app.models.schemas import LABEL, DebateConfig, DebateMessage, now
from app.rag.retrieval import TopicRetriever
from app.services.observability import LoggingObserver
from app.services.profiles import build_profile


def initial_state(session_id, config):
    return {
        "session_id": session_id,
        "topic": config.topic,
        "candidate_a": config.candidate_a,
        "candidate_b": config.candidate_b,
        "current_phase": "SETUP",
        "messages": [],
        "turn_number": 0,
        "max_turns": config.max_turns,
        "debate_config": config.model_dump(),
        "execution_metadata": [],
        "profiles": {},
    }


def build_graph(store, provider, retriever, search, checkpointer=None, observer=None):
    observer = observer or LoggingObserver()
    candidate_agent = build_candidate_agent(provider, retriever, search)
    research_agent = build_research_agent(TopicRetriever(retriever), search)

    def tracked(name, fn):
        async def run(state):
            writer = get_stream_writer()
            writer({"type": "node_start", "node": name, "phase": state.get("current_phase"), "at": now()})
            started = perf_counter()
            try:
                update = await fn(state)
            except Exception as error:
                # Preserve the failed node for checkpoint-based retry, with a safe client error.
                observer.node(
                    {"session_id": state["session_id"], "node": name, "error": type(error).__name__}
                )
                writer({"type": "node_error", "node": name, "error": type(error).__name__})
                raise
            event = {
                "session_id": state["session_id"],
                "node": name,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "tokens": update.pop("_tokens", 0),
                "model": provider.model,
                "retrieval_count": len(update.get("retrieved_context", state.get("retrieved_context", []))),
                "retrieval_query": state["topic"],
                "at": now(),
            }
            if name == "research_topic":
                event["web_research"] = update.get("web_research_history", [])
                event["retrieval_count"] = len(update.get("research", {}).get("evidence", []))
            if "retrieve" in name or name == "research_topic":
                event["retrieval_latency_ms"] = event["duration_ms"]
            subevents = update.pop("_subevents", [])
            update["execution_metadata"] = [*state.get("execution_metadata", []), *subevents, event]
            observer.node(event)
            writer({"type": "node_end", **event, "state": {**state, **update}})
            return update

        return run

    async def validate_debate(state):
        config = DebateConfig.model_validate(state["debate_config"])
        for cid in [config.candidate_a, config.candidate_b]:
            info = candidate(cid)
            if config.mode == "fixture" and not info["fictional"]:
                raise ValueError("Fixture mode requires fictional agents")
            if config.mode == "live" and provider.model.startswith("fixture"):
                raise ValueError("Live mode requires a real generation provider")
        return {"current_phase": "RESEARCH"}

    async def research(state):
        result = await research_agent.ainvoke(state)
        return {
            "research": result["research"],
            "web_research_history": [
                *state.get("web_research_history", []),
                *result.get("web_research_history", []),
            ],
            "_tokens": sum(r.get("tokens", 0) for r in result.get("web_research_history", [])),
        }

    async def profiles(state):
        output = {}
        tokens = 0
        for cid in [state["candidate_a"], state["candidate_b"]]:
            evidence = await asyncio.to_thread(store.program_evidence, cid, retriever.embeddings.model)
            if not evidence:
                evidence = [e for e in state["research"]["evidence"] if e["candidate_id"] == cid]
            profile, used = await build_profile(provider, cid, evidence, store.runtime_dir / "playbooks")
            output[cid] = profile.model_dump()
            tokens += used
        return {"profiles": output, "_tokens": tokens}

    async def question(state):
        question_research = {}
        if state["turn_number"] > 0:
            fresh = await research_agent.ainvoke(state)
            question_research = {
                "research": fresh["research"],
                "web_research_history": [
                    *state.get("web_research_history", []),
                    *fresh.get("web_research_history", []),
                ],
            }
        result, tokens = await generate_question(provider, {**state, **question_research})
        tokens += sum(
            r.get("tokens", 0)
            for r in question_research.get("web_research_history", [])[
                len(state.get("web_research_history", [])) :
            ]
        )
        cid, _ = question_participants(state)
        message = DebateMessage(
            id=str(uuid4()),
            candidate_id=cid,
            phase="QUESTION",
            content=result.content,
            timestamp=now(),
            label=LABEL,
            citations=[{"source_id": sid} for sid in result.source_ids],
        ).model_dump()
        writer = get_stream_writer()
        writer({"type": "message", "message": message})
        return {
            **question_research,
            "question": result.content,
            "current_phase": "QUESTION",
            "messages": [*state["messages"], message],
            "_tokens": tokens,
        }

    def other(state, cid):
        return state["candidate_b"] if cid == state["candidate_a"] else state["candidate_a"]

    async def answer(state):
        first = state["debate_config"]["responds_first"]
        cid = state["candidate_a"] if first == "a" else state["candidate_b"]
        if state["turn_number"] % 2:
            cid = other(state, cid)
        return {"current_phase": "ANSWER", "current_speaker": cid}

    async def rebuttal(state):
        return {"current_phase": "REBUTTAL", "current_speaker": other(state, state["current_speaker"])}

    async def counter(state):
        return {
            "current_phase": "COUNTER_REBUTTAL",
            "current_speaker": other(state, state["current_speaker"]),
        }

    async def run_candidate(state):
        result = await candidate_agent.ainvoke(state)
        return {
            "pending_response": result["response"],
            "argument_plan": result.get("argument_plan", {}),
            "dialogue_context": result["dialogue_context"],
            "retrieval_query": result["retrieval_query"],
            "phase_web_research": result["phase_web_research"],
            "web_research_history": [*state.get("web_research_history", []), result["phase_web_research"]],
            "retrieved_context": result["retrieved_context"],
            "validation": result["validation"],
            "retries": result["retries"],
            "validation_history": result.get("validation_history", []),
            "_subevents": result.get("candidate_metadata", []),
            "_tokens": 0,
        }

    async def save_turn(state):
        response = state["pending_response"]
        message = DebateMessage(
            id=str(uuid4()),
            timestamp=now(),
            label=LABEL,
            validation={**state["validation"], "attempts": state.get("validation_history", [])},
            **response,
        ).model_dump()
        writer = get_stream_writer()
        # Only approved content reaches the UI. Token playback uses actual UTF-8-safe BPE tokens.
        writer(
            {
                "type": "message_start",
                "message": {**message, "content": ""},
                "streaming": "validated_token_playback",
            }
        )
        encoder = tiktoken.get_encoding("cl100k_base")
        decoder = codecs.getincrementaldecoder("utf-8")()
        for token in encoder.encode(message["content"]):
            piece = decoder.decode(encoder.decode_single_token_bytes(token))
            if piece:
                writer({"type": "token", "message_id": message["id"], "text": piece})
                await asyncio.sleep(0.008)
        tail = decoder.decode(b"", final=True)
        if tail:
            writer({"type": "token", "message_id": message["id"], "text": tail})
        writer({"type": "message_end", "message": message})
        update = {"messages": [*state["messages"], message]}
        await asyncio.to_thread(store.save_state, {**state, **update})
        return update

    async def round_done(state):
        return {"turn_number": state["turn_number"] + 1, "round_complete": True}

    def round_pause(state):
        if state["debate_config"]["pause_after_round"]:
            interrupt({"reason": "Round complete; resume to continue", "turn_number": state["turn_number"]})
        return {}

    async def complete(state):
        return {"current_phase": "COMPLETE"}

    graph = StateGraph(DebateState)
    nodes = {
        "validate_debate": validate_debate,
        "research_topic": research,
        "build_candidate_profiles": profiles,
        "generate_question": question,
        "candidate_answer": answer,
        "candidate_rebuttal": rebuttal,
        "candidate_counter_rebuttal": counter,
        "candidate_agent": run_candidate,
        "save_turn": save_turn,
        "round_complete": round_done,
        "complete": complete,
    }
    for name, fn in nodes.items():
        graph.add_node(name, tracked(name, fn))
    graph.add_node("round_pause", round_pause)
    graph.add_edge(START, "validate_debate")
    graph.add_edge("validate_debate", "research_topic")
    graph.add_edge("research_topic", "build_candidate_profiles")
    graph.add_edge("build_candidate_profiles", "generate_question")
    graph.add_edge("generate_question", "candidate_answer")
    for node in ["candidate_answer", "candidate_rebuttal", "candidate_counter_rebuttal"]:
        graph.add_edge(node, "candidate_agent")
    graph.add_edge("candidate_agent", "save_turn")
    graph.add_conditional_edges(
        "save_turn",
        route_next_phase,
        {
            "rebuttal": "candidate_rebuttal",
            "counter": "candidate_counter_rebuttal",
            "round": "round_complete",
        },
    )
    graph.add_edge("round_complete", "round_pause")
    graph.add_conditional_edges(
        "round_pause", route_round, {"complete": "complete", "next": "generate_question"}
    )
    graph.add_edge("complete", END)
    return graph.compile(checkpointer=checkpointer)
