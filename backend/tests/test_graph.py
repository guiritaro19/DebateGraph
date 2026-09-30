from uuid import uuid4

import pytest
from app.graph.graph import build_graph, initial_state
from app.models.schemas import DebateConfig
from app.rag.embeddings import FixtureEmbeddings
from app.rag.retrieval import CandidateRetriever
from app.services.providers import FixtureProvider
from app.services.runtime import Runtime
from app.services.search import SearchProvider
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command


@pytest.mark.parametrize(
    "depth,phases",
    [
        (1, ["QUESTION", "ANSWER"]),
        (2, ["QUESTION", "ANSWER", "REBUTTAL"]),
        (3, ["QUESTION", "ANSWER", "REBUTTAL", "COUNTER_REBUTTAL"]),
    ],
)
async def test_complete_graph_routing(store, settings, depth, phases):
    graph = build_graph(
        store,
        FixtureProvider(),
        CandidateRetriever(store, FixtureEmbeddings()),
        SearchProvider(settings),
        InMemorySaver(),
    )
    config = DebateConfig(
        candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", depth=depth, mode="fixture"
    )
    state = await graph.ainvoke(
        initial_state(str(uuid4()), config), {"configurable": {"thread_id": str(uuid4())}}
    )
    assert [m["phase"] for m in state["messages"]] == phases
    assert state["current_phase"] == "COMPLETE"
    assert all(m["label"] == "AI-generated simulation based on public sources." for m in state["messages"])
    assert [m["candidate_id"] for m in state["messages"]] == ["atlas", "nova", "atlas", "nova"][: depth + 1]


async def test_round_switch_and_checkpoint_resume(settings):
    from scripts.seed_fixtures import seed

    session_id = str(uuid4())
    config = DebateConfig(
        candidate_a="atlas",
        candidate_b="nova",
        topic="Inteligência artificial",
        mode="fixture",
        depth=1,
        max_turns=2,
        pause_after_round=True,
    )
    runtime = Runtime(settings)
    await runtime.start()
    seed(runtime.store, FixtureEmbeddings())
    runtime.store.create_session(session_id, config)
    cfg = {"configurable": {"thread_id": session_id}}
    partial = await runtime.graph("fixture").ainvoke(initial_state(session_id, config), cfg)
    assert len(partial["messages"]) == 2
    await runtime.close()
    # A new runtime reopens SQLite checkpoints, preserving interruption and thread identity.
    second = Runtime(settings)
    await second.start()
    try:
        graph = second.graph("fixture")
        assert (await graph.aget_state(cfg)).interrupts
        resumed = await graph.ainvoke(Command(resume=True), cfg)
        assert [m["candidate_id"] for m in resumed["messages"]] == ["atlas", "nova", "nova", "atlas"]
        final = await graph.ainvoke(Command(resume=True), cfg)
        assert final["current_phase"] == "COMPLETE"
        second.store.save_state(final, "complete")
        assert len(second.store.get_session(session_id)["messages"]) == 4
    finally:
        await second.close()


async def test_fixture_rejects_real_candidates(store, settings):
    config = DebateConfig(candidate_a="lula", candidate_b="flavio", topic="Educação", mode="fixture")
    graph = build_graph(
        store, FixtureProvider(), CandidateRetriever(store, FixtureEmbeddings()), SearchProvider(settings)
    )
    with pytest.raises(ValueError, match="fictional"):
        await graph.ainvoke(initial_state(str(uuid4()), config))


async def test_stream_reassembles_approved_utf8(store, settings):
    graph = build_graph(
        store, FixtureProvider(), CandidateRetriever(store, FixtureEmbeddings()), SearchProvider(settings)
    )
    config = DebateConfig(
        candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", mode="fixture", depth=1
    )
    tokens = {}
    completed = []
    async for event in graph.astream(initial_state(str(uuid4()), config), stream_mode="custom"):
        if event["type"] == "token":
            tokens.setdefault(event["message_id"], "")
            tokens[event["message_id"]] += event["text"]
        if event["type"] == "message_end":
            completed.append(event["message"])
    assert completed
    for message in completed:
        assert tokens[message["id"]] == message["content"]
        assert message["validation"]["valid"]
