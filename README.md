# DebateGraph

An open-source AI engineering laboratory for **evidence-grounded debate simulations**.
LangGraph controls the exchange; LangChain calls the models; PostgreSQL + pgvector stores
candidate-specific public evidence. A Next.js workspace shows the transcript, running graph,
retrieved documents, checkpoints and engineering metrics.

> This application generates AI simulations based on public sources. Generated responses are not authentic candidate statements.

No vote recommendations, rankings, predictions, polling or candidate endorsements. Confidence describes
evidence coverage only. Candidate messages always display `AI-generated simulation based on public sources.`
There is no electoral scoring field. The project has no affiliation with candidates, parties or TSE.

## Start locally without Docker

Requirements: **Python 3.12+**, **Node.js 24**, **uv**. Docker is optional.
The Windows quickstart downloads a portable PostgreSQL with pgvector into ignored `runtime/`;
it does not install a Windows service or require WSL. This binary distribution is supplied by
[@boomship/postgres-vector-embedded](https://github.com/boomship/postgres-vector-embedded), a third-party
MIT package with reproducible release builds; use your own PostgreSQL installation if preferred.

```powershell
git clone <your-repository-url> DebateGraph
cd DebateGraph
Copy-Item .env.example .env
./scripts/setup.ps1
# Add OPENAI_API_KEY to .env locally. Never commit it.
.venv/Scripts/python.exe -m scripts.ingest_all data/sources.tse-2026.json
./scripts/start.ps1
```

Open **http://127.0.0.1:3000**. API documentation: **http://127.0.0.1:8000/docs**.
Each debate selects exactly **two participants** from the five configured presidential profiles: Lula, Flávio Bolsonaro, Augusto Cury, Ronaldo Caiado and Renan Santos. Set the topic, speaking order, debate depth, rounds and style; press **Iniciar debate**.
Pause after each round to inspect state; resume uses the same `thread_id`. JSON logs can be exported.
Use `./scripts/stop.ps1` to stop services; data is preserved. Logs are in ignored `runtime/`.

For a database-free quick experiment, keep the default SQLite URL in `.env` and run
`./scripts/setup.ps1 -SQLite` and `./scripts/start.ps1 -SQLite`. SQLite still uses configured
OpenAI embeddings and exact cosine retrieval in Python; **pgvector runs only in PostgreSQL mode**.
It is not silently emulated as pgvector. Synthetic fixtures use deterministic hash vectors only for testing.

On Linux/macOS:
```bash
uv sync --frozen --extra dev --extra studio
cp .env.example .env
npm ci --prefix frontend
npm ci --prefix tools
node tools/postgres.mjs start
uv run python -m scripts.use_postgres
uv run python -m scripts.seed_fixtures
uv run python -m scripts.ingest_all data/sources.tse-2026.json
bash scripts/start.sh
```

## Architecture

```mermaid
flowchart LR
    UI[Next.js / React / TypeScript] -->|REST + SSE| API[FastAPI]
    API --> G[LangGraph controller]
    G --> R[Research subgraph]
    G --> Q[Neutral question agent]
    G --> C[Candidate subgraph]
    C --> V[Structural + semantic validator]
    V -->|at most 1 retry| C
    C --> DB[(PostgreSQL / pgvector)]
    R --> DB
    I[URL / PDF / DOCX ingestion] --> E[Independent embeddings provider]
    E --> DB
    G --> CP[(SQLite or PostgreSQL checkpoints)]
    G --> LOG[(Persisted session log)]
```

LangGraph was chosen because debate phases require **state, conditional routing, retries, subgraphs,
interrupts and durable checkpoints**. This is an actual `StateGraph`, not a chain with a diagram.
The developer graph is derived from `get_graph()` and highlights node events from execution.

The lifecycle is setup → research → evidence-derived profiles → neutral question → answer → optional
rebuttal → optional counter-rebuttal → next round → complete. Each candidate phase invokes a subgraph:
retrieve own context → structured generation → source validator → accept, regenerate or abstain.
Validation runs **after every candidate response**, before persistence and visible transmission.

## Agents and state

`DebateState` includes session identity, topic, participants, phase, speaker, question, messages,
retrieved context, citations, round number, configuration, research, profiles, validation history and telemetry.
Research creates candidate-aware search queries, retrieves evidence and prioritizes source tiers.
Questions are neutral structured outputs, constrained to consulted source IDs.
Candidate profiles derive policy positions from citations and rhetoric from official speech/interviews.
Candidate context is never a hardcoded bundle of political positions.

The requested roster lives in `data/candidates/candidates.json`: Lula/PT, Flávio Bolsonaro/PL,
Augusto Cury/Avante, Ronaldo Caiado/PSD and Renan Santos/Missão. These entries were checked against
the TSE presidential program index on 2026-09-29; this project does not assess candidacy eligibility.
Add a configuration entry and its sources to extend the roster.

**Style** has two explicit modes. `evidence` uses only the evidence-derived rhetorical profile.
`expressive` additionally uses user-directed stylistic hints (e.g. a vocative or sarcastic phrasing),
stored separately as `requested_style`; those hints are artistic direction, not factual personality claims.
They cannot support policy claims. Source excerpts and user topics are untrusted data, not instructions.

## RAG and source ingestion

URL or local document → fetch → extract → clean/normalize → overlap chunks → embed → transactional storage.
PDF, DOCX, TXT/MD and HTML are supported. Scanned PDFs require OCR before ingestion.
Sources store ID, candidate, title, URL, publisher, type, publication/retrieval dates, content hash,
election year and raw extracted text. Chunks store ID, source/candidate, content, vector, index,
embedding model and dimensions. Content hashes deduplicate unchanged content; changing embedding
models adds a separate vector representation without mixing embedding spaces.

Source hierarchy:
1. TSE-hosted official government programs (primary policy evidence).
2. Official websites, interviews, speeches and debate transcripts.
3. Reputable journalism, selected explicitly by the importer.

No unsourced social-media summaries. `data/sources.tse-2026.json` contains the **five verified direct
PDF URLs**. Publication dates are null when not known, rather than invented. Retrieval dates are automatic.
Historical sources retain their election year and are not presented as 2026 positions.

```powershell
# Import the official manifest, idempotently:
.venv/Scripts/python.exe -m scripts.ingest_all data/sources.tse-2026.json
# Curate metadata for a single official source:
.venv/Scripts/python.exe -m scripts.ingest_candidate --metadata data/my-source.json
# Import a PDF you downloaded manually with its TSE provenance URL:
.venv/Scripts/python.exe -m scripts.ingest_candidate --metadata data/my-source.json --document C:/path/program.pdf
```

Metadata example:
```json
{
  "candidate_id": "lula",
  "title": "Programa de governo 2026",
  "url": "https://www.tse.jus.br/eleicoes/eleicoes-2026-content/arquivos/proposta-pt/@@display-file/file/proposta-pt.pdf",
  "publisher": "Tribunal Superior Eleitoral",
  "source_type": "government_program",
  "publication_date": null,
  "election_year": 2026
}
```

The interface also has **Importar uma fonte**. URL ingestion rejects local/private destinations,
credentials in URLs, nonstandard ports, excessive redirects and bodies over 20 MB.
TSE content-object URLs may return HTTP 403; use the actual PDF URL ending in `@@display-file/file/…pdf`
or manually downloaded documents. Never bypass a CAPTCHA or access restriction.

## Retrieval and citations

`Retriever`, `CandidateRetriever` and `TopicRetriever` separate application logic from storage.
PostgreSQL performs cosine distance using pgvector `<=>`, with candidate filters applied **inside the SQL
query**. Optional topic, source type and minimum publication date filters are supported.
Only the matching embedding model is searched. Low similarity is excluded, then authoritative tiers
are preferred. A `Reranker` protocol allows later extension. The MVP uses exact search (no ANN index);
this is appropriate for the small corpus and straightforward to audit.

Structured Pydantic outputs include ResearchResult, CandidateResponse, Claim, Citation, DebateQuestion,
CandidateProfile and ValidationResult. Each policy claim must have an exact cited excerpt from a chunk
retrieved for the **same candidate**. The validator first checks IDs, isolation and exact excerpts, then
asks a model to assess entailment across the whole response. Invalid responses are regenerated at most once;
continued failure produces a topic-bound conceptual challenge without new factual claims. Opponent messages
never support an own-candidate position. Internal identifiers are forbidden in public speech; citations are
disclosed beneath each generated message.

At session start, web research searches candidate name + topic and a complementary query for declarations,
interviews and proposals. It tries to read three distinct pages per candidate and reuses those results during
the session, while RAG retrieval remains phase-specific.

**Limits:** model entailment checks are probabilistic, not a guarantee of factual accuracy. Imported sources
need editorial review. The local MVP has no authentication and must remain bound to loopback; before
public hosting, add authentication, ingestion access control, rate limits and hardened network egress.
The URL checks are not a complete defense against DNS rebinding. A public source can still contain
misinformation or prompt injection; test and inspect the resulting claims.

## Streaming and persistence

FastAPI streams SSE events: node start/end, nested graph updates, message start, UTF-8-safe BPE token
chunks, message end, pause, completion or error. **Tokens are played back after validation**, rather
than publishing an unverified draft while the provider generates. This trades initial latency for
integrity and is visibly disclosed in the UI. It is not presented as raw provider token streaming.

Each session has a UUID used as its `thread_id`. Logs persist topic, participants, configuration,
timestamps, messages, consulted sources, node metadata, generation/validation token usage and latency.
SQLite checkpoints are the default; PostgreSQL checkpoints are enabled by the portable quickstart.
Process restarts preserve checkpoints in both modes. Complete logs are replayable; paused/interrupted
sessions can continue from their checkpoint. Duplicate concurrent runs of a thread are rejected.
Live events have no replay IDs; after a disconnect, reload the saved log and resume. At-least-once node
execution can replay an unsaved streamed message after an interruption; message IDs deduplicate one stream.

Windows PostgreSQL async uses `app.services.loops:postgres_loop` with Uvicorn, because Psycopg requires
a selector event loop. Scripts set the same loop factory explicitly.

## Environment variables

| Variable | Purpose |
|---|---|
| OPENAI_API_KEY | Server-only generation/embedding credential; kept in ignored `.env` |
| LLM_PROVIDER | `openai` or explicit test `fixture`; provider protocol supports future adapters |
| LLM_MODEL | Generation and semantic validation model; default `gpt-4.1-mini` |
| EMBEDDING_PROVIDER | Independently configurable `openai` or test `fixture` |
| EMBEDDING_MODEL | Embedding space; default `text-embedding-3-small` |
| EMBEDDING_DIMENSIONS | Vector dimensions, default 1536; do not compare different spaces |
| DATABASE_URL | SQLAlchemy URL for SQLite or PostgreSQL source/vector/session storage |
| CHECKPOINT_BACKEND | `sqlite`, `memory` or `postgres`; memory is process-local only |
| CHECKPOINT_DATABASE_URL | Psycopg PostgreSQL URI for durable graph checkpoints |
| SEARCH_PROVIDER | `openai`, `tavily` or `none`; web discovery complements local RAG |
| SEARCH_MODEL | OpenAI model used for discovery when `SEARCH_PROVIDER=openai` |
| SEARCH_API_KEY | Tavily credential, only with `SEARCH_PROVIDER=tavily` |
| MAX_OUTPUT_TOKENS | Generation budget per structured response |
| MODEL_TIMEOUT_SECONDS | Timeout per model call; bounded provider retries |
| CORS_ORIGINS | Comma-separated allowed frontend origins |
| NEXT_PUBLIC_API_URL | Browser-visible API base URL; never put secrets in NEXT_PUBLIC variables |
| LANGSMITH_TRACING | Optional tracing; disabled by default |
| LANGSMITH_API_KEY | Optional Studio/tracing credential, unrelated to the OpenAI key |

Telemetry needs no paid service. LoggingObserver can be replaced by an Observer adapter for
OpenTelemetry; LangChain's optional LangSmith tracing works through its standard environment variables.
Usage reports generation/validation provider tokens; embedding usage is not included in session totals.

## Inspect visually with LangGraph Studio

The application already includes a free local graph inspector, source log and full state panel.
For the official Studio integration, `langgraph.json` exports the **same graph builder**:

```powershell
.venv/Scripts/langgraph.exe dev --no-browser --allow-blocking
```

Open [Studio connected to localhost](https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024).
The Studio UI is hosted by LangSmith and may require a free LangSmith account/key. It is optional and
does not replace the local interface. Consult [the official local-server guide](https://docs.langchain.com/oss/python/langgraph/local-server).
The Agent Server manages its own checkpoints; the REST server's session logs are separate.
Use the full state input in `docs/studio-input.json` (copy it from the repository, not a partial message schema).

## Docker alternative

```bash
docker compose up -d postgres
# Set DATABASE_URL and CHECKPOINT_DATABASE_URL to the localhost PostgreSQL URLs.
# Or run all three services:
docker compose --profile full up --build -d
docker compose exec backend python -m scripts.ingest_all data/sources.tse-2026.json
```

Docker is **not required for the Windows portable setup**. `.dockerignore` excludes `.env` from build
contexts. Runtime configuration is injected with `env_file`, never baked into images.
Container builds are provided; see `docs/TESTING.md` for what was actually validated locally.

## Tests, samples and engineering evaluation

```powershell
.venv/Scripts/python.exe -m pytest -q
$env:TEST_DATABASE_URL='postgresql+psycopg://debategraph:debategraph@127.0.0.1:5433/debategraph'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.sample_debate
.venv/Scripts/python.exe -m scripts.sample_debate --live
.venv/Scripts/python.exe -m scripts.political_sample
.venv/Scripts/python.exe -m scripts.evaluate --file docs/samples/political-debate.json
npm run build --prefix frontend
```

Tests cover phase routing/depth, source isolation, filters, exact citations, bounded retries,
structured outputs, environment configuration, deduplication, SSE UTF-8, full miniature debates,
SQLite restart/resume and real pgvector retrieval. Tests use fictional agents and never require an API key.
Examples and their evaluation reports live in `docs/samples/`. Live scripts require a key and incur API usage.
Evaluation reports citation coverage, unsupported final claims, rejected draft attempts, candidate
isolation, retrieval cosine relevance proxy, response latency, tokens and abstentions. Similarity is
not a substitute for human-labeled relevance; no metric compares candidate quality or electability.

## Screenshots

Screenshots from local execution are in `docs/screenshots/`:

![Desktop workspace](docs/screenshots/desktop.png)
![Debate with inspected sources](docs/screenshots/debate.png)
![Mobile layout](docs/screenshots/mobile.png)

## Repository guide

| Directory | Responsibility |
|---|---|
| backend/app/graph | Typed state, routing, controller and Studio export |
| backend/app/agents | Research/candidate subgraphs, questions and source validation |
| backend/app/rag | Fetching, extraction, normalization, chunks, embeddings and retrieval |
| backend/app/db | SQLAlchemy schema and session/source persistence |
| backend/app/services | Providers, profile construction, runtime and observability interfaces |
| backend/app/api | REST/SSE lifecycle |
| frontend | Next.js UI, graph drawing, transcript and inspector |
| data | Candidate/topic configuration and curated source manifests |
| scripts | Setup, ingestion, synthetic samples, evaluation and service management |
| tools | Portable PostgreSQL downloader/launcher and locked npm dependencies |
| docker | Optional containers |
| docs | Architecture decisions, testing evidence, examples and screenshots |

## Future improvements

Anthropic/Gemini/Ollama adapters; independent entailment model; labeled retrieval benchmarks and
reranking; source/version management; OCR; ANN indexes and migrations for larger corpora; authenticated
deployments; server-side cancellation; replayable SSE; OpenTelemetry export; real speech datasets for
evidence-derived rhetoric. All are explicit extensions, not claimed as implemented.

## Portfolio description

Built DebateGraph, an open-source AI engineering experiment using LangGraph subgraphs and durable
checkpoints to orchestrate evidence-grounded debate simulations. Implemented a candidate-isolated
RAG pipeline with PostgreSQL/pgvector, structured agent outputs, bounded source-validation retries,
FastAPI SSE, and a Next.js execution inspector, backed by automated tests and engineering evaluations.

MIT for application code. Public source documents retain their original rights and attribution;
the repository contains source URLs, not redistribution of full official PDFs.

Pesquisa web e contexto por fase: [documentação](docs/WEB_RESEARCH.md). Apresentação para portfólio: [português e inglês](docs/PORTFOLIO-PT-EN.md).


## Public AI configuration

For provider configuration, source ingestion and cost controls, read [`docs/AI_SETUP.md`](docs/AI_SETUP.md). The repository never requires a committed `.env` file.
