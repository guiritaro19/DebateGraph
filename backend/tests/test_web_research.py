from unittest.mock import patch
from uuid import uuid4

from app.graph.graph import build_graph, initial_state
from app.models.schemas import DebateConfig
from app.rag.embeddings import FixtureEmbeddings
from app.rag.retrieval import CandidateRetriever
from app.services.providers import FixtureProvider
from app.services.search import SearchProvider
from langgraph.checkpoint.memory import InMemorySaver


def test_domain_filter_rejects_spoofed_hosts(settings):
    search = SearchProvider(settings)
    assert search.allowed_url("https://www.gov.br/fazenda")
    assert search.allowed_url("https://agenciabrasil.ebc.com.br/economia")
    assert not search.allowed_url("https://gov.br.attacker.example/fake")
    assert not search.allowed_url("https://untrusted.example/")


async def test_every_dialogue_phase_researches_in_sequence(store, settings):
    class Research:
        def __init__(self):
            self.calls = []

        async def research_candidate(self, query, cid, phase, retriever):
            self.calls.append((cid, phase, query))
            return {"tokens": 7, "discoveries": [], "status": "complete", "phase": phase}

    search = Research()
    graph = build_graph(
        store, FixtureProvider(), CandidateRetriever(store, FixtureEmbeddings()), search, InMemorySaver()
    )
    cfg = DebateConfig(
        candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", mode="fixture", depth=3
    )
    state = await graph.ainvoke(
        initial_state(str(uuid4()), cfg), {"configurable": {"thread_id": str(uuid4())}}
    )
    assert [(cid, phase) for cid, phase, _ in search.calls] == [
        ("atlas", "QUESTION"),
        ("nova", "QUESTION"),
        ("nova", "ANSWER"),
        ("atlas", "REBUTTAL"),
        ("nova", "COUNTER_REBUTTAL"),
    ]
    assert len(state["web_research_history"]) == 5
    assert sum(e["tokens"] for e in state["execution_metadata"]) == 35
    assert all("Argumento a responder" in query for _, phase, query in search.calls if phase != "QUESTION")


async def test_web_failure_falls_back_without_unverified_evidence(settings):
    search = SearchProvider(settings.model_copy(update={"search_provider": "openai"}))

    async def failed(*args):
        raise TimeoutError("test timeout")

    with patch.object(search, "search", failed):
        report = await search.research_candidate("bets", "lula", "REBUTTAL", None)
    assert report["status"] == "unavailable_using_local_evidence"
    assert report["discoveries"] == []


async def test_search_links_are_read_before_becoming_evidence(settings):
    search = SearchProvider(settings.model_copy(update={"search_provider": "openai"}))

    async def found(*args):
        return {
            "tokens": 10,
            "discoveries": [
                {"url": "https://www.gov.br/test", "title": "test", "status": "discovered_not_ingested"}
            ],
        }

    with (
        patch.object(search, "search", found),
        patch.object(search, "ingest_discovery", side_effect=ValueError("unreadable")),
    ):
        report = await search.research_candidate("bets", "lula", "ANSWER", None)
    assert report["tokens"] == 10
    assert report["discoveries"][0]["status"] == "unavailable_not_used"
    assert "source_id" not in report["discoveries"][0]


async def test_fixture_never_searches_the_web(settings):
    search = SearchProvider(settings.model_copy(update={"search_provider": "openai"}))
    with patch.object(search, "search", side_effect=AssertionError("No web in fictional mode")):
        assert (await search.research_candidate("test", "atlas", "ANSWER", None))["status"] == "disabled"


def test_query_keeps_candidate_and_topic_not_opponent_monologue(settings):
    search = SearchProvider(settings)
    queries = search.candidate_queries("Cotas raciais. Argumento a responder: um discurso enorme", "renan")
    assert queries[0] == "Renan Santos Cotas raciais"
    assert all("um discurso enorme" not in q for q in queries)
    assert "declaração entrevista" in queries[1]


async def test_unreadable_result_does_not_consume_three_source_target(settings):
    search = SearchProvider(settings.model_copy(update={"search_provider": "openai"}))
    links = [{"url": f"https://www.gov.br/{i}", "title": str(i)} for i in range(5)]

    async def found(queries):
        assert queries[0] == "Renan Santos Cotas raciais"
        return {"tokens": 1, "discoveries": links}

    def ingest(item, cid, retriever):
        if item == links[0]:
            raise ValueError("page not readable")
        return {**item, "source_id": item["title"], "status": "ingested"}

    with patch.object(search, "search", found), patch.object(search, "ingest_discovery", ingest):
        report = await search.research_candidate("Cotas raciais", "renan", "ANSWER", None)
    assert report["read_sources"] == 3
    assert report["status"] == "complete"
    assert [r["search_rank"] for r in report["discoveries"] if r["status"] == "ingested"] == [2, 3, 4]


async def test_candidate_phase_reuses_initial_session_search(store, settings):
    class Search:
        async def research_candidate(self, *args):
            raise AssertionError("Initial candidate/topic research must be reused")

    from app.agents.candidate import build_candidate_agent

    state = initial_state(
        str(uuid4()),
        DebateConfig(
            candidate_a="atlas", candidate_b="nova", topic="Inteligência artificial", mode="fixture"
        ),
    )
    state.update(
        current_speaker="atlas",
        current_phase="ANSWER",
        question="Como?",
        web_research_history=[
            {
                "candidate_id": "atlas",
                "phase": "QUESTION",
                "tokens": 7,
                "discoveries": [],
                "status": "complete",
            }
        ],
    )
    result = await build_candidate_agent(
        FixtureProvider(), CandidateRetriever(store, FixtureEmbeddings()), Search()
    ).ainvoke(state)
    assert result["phase_web_research"]["status"] == "reused_session_research"
    assert result["phase_web_research"]["tokens"] == 0
