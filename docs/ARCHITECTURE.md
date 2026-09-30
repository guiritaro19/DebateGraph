# Architecture decisions

1. **Two storage responsibilities.** SQLAlchemy owns source/chunk/session artifacts; LangGraph's
   checkpointer owns resumable computational state. UUID session/thread IDs join their histories.
2. **Two concrete subgraphs.** Research understands the topic and ranks retrieved evidence; candidate
   subgraph retrieves, generates, validates and retries. Questions and controller are specialized nodes.
3. **Candidate isolation is enforced twice.** Candidate ID filters are applied in SQL and again in the
   validator against retrieved chunks. Synthetic sources cannot enter real candidate ingestion.
4. **Evidence first.** Profiles contain citation-bearing positions, not political stance prompts. Rhetoric
   requires speech evidence; user-requested artistic direction lives in a separate configuration field.
5. **Integrity before streaming.** Structured outputs and validation complete before BPE token playback.
   This is a deliberate latency tradeoff, not raw model streaming. Failed drafts are retained in validation
   attempt metadata, never in the candidate transcript.
6. **Portable PostgreSQL for local Windows.** A third-party binary package supplies PostgreSQL/pgvector.
   Binaries/data stay under ignored runtime/. No Docker/WSL/service installation. PostgreSQL SQL/driver
   behavior is real; SQLite is an explicitly disclosed quickstart alternative, not a pgvector substitute.
7. **Exact retrieval.** Cosine query in pgvector; no ANN index in the MVP. Candidate/model filters precede
   ranking; source tiers rank relevant results. Metadata preserves content hashes, publication dates and
   election years. Embedding spaces are independent from generation providers.
8. **Curated ingestion.** Search discovery is optional; discovered URLs do not silently become evidence.
   The importer assigns source tier/publisher/candidate, which requires human curation outside the test corpus.
9. **Reproducibility.** uv.lock and npm lockfiles pin dependencies. Fixtures test mechanics offline, then
   separate live samples exercise OpenAI against synthetic and public evidence.
10. **Known boundaries.** No authentication, source truth is not independently verified, semantic
   validation is probabilistic, no OCR/ANN/reranker/alternate provider is represented as complete.
   Live SSE is not a durable event journal. No public deployment is part of this local experiment.
