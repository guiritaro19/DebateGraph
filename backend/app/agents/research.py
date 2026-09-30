import asyncio

from langgraph.graph import END, START, StateGraph

from app.config.catalog import candidate
from app.graph.state import DebateState
from app.models.schemas import ResearchResult


def build_research_agent(topic_retriever, search):
    def understand_topic(state):
        ids = [state["candidate_a"], state["candidate_b"]]
        return {
            "research": {
                "topic": state["topic"],
                "queries": [
                    f"{candidate(cid)['name']} {state['topic']} programa de governo site:tse.jus.br"
                    for cid in ids
                ],
            }
        }

    async def retrieve_and_rank(state):
        reports = []
        for cid in [state["candidate_a"], state["candidate_b"]]:
            reports.append(
                await search.research_candidate(
                    state["topic"], cid, "QUESTION", topic_retriever.candidate_retriever
                )
            )
        contexts = await asyncio.to_thread(
            topic_retriever.retrieve, state["topic"], [state["candidate_a"], state["candidate_b"]]
        )
        for report in reports:
            ids = [d["source_id"] for d in report["discoveries"] if d.get("status") == "ingested"]
            if ids:
                fresh = await asyncio.to_thread(
                    topic_retriever.candidate_retriever.retrieve,
                    state["topic"],
                    report["candidate_id"],
                    source_ids=ids,
                    limit=3,
                )
                old = contexts[report["candidate_id"]]
                seen = {e["chunk_id"] for e in fresh}
                contexts[report["candidate_id"]] = [*fresh, *(e for e in old if e["chunk_id"] not in seen)][
                    :6
                ]
        evidence = [e for context in contexts.values() for e in context]
        discoveries = [item for report in reports for item in report["discoveries"]]
        research = ResearchResult(
            topic=state["topic"],
            queries=state["research"]["queries"],
            source_ids=list(dict.fromkeys(e["source_id"] for e in evidence)),
            evidence=evidence,
            discoveries=discoveries,
        )
        return {"research": research.model_dump(), "web_research_history": reports}

    graph = StateGraph(DebateState)
    graph.add_node("understand_topic", understand_topic)
    graph.add_node("retrieve_and_rank_evidence", retrieve_and_rank)
    graph.add_edge(START, "understand_topic")
    graph.add_edge("understand_topic", "retrieve_and_rank_evidence")
    graph.add_edge("retrieve_and_rank_evidence", END)
    return graph.compile()
