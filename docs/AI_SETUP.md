# AI setup and source guide

DebateGraph combines local RAG over candidate-specific public documents with a small web search for the selected candidate and debate topic. Generated speech is never a source. Claims are transmitted only after candidate isolation, citation binding and semantic validation.

## Configure local secrets

Copy the public template and edit the copy:

```powershell
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` inside `.env`. This file is ignored by Git. Never place a key in `.env.example`, frontend code or a variable prefixed with `NEXT_PUBLIC_`.

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
SEARCH_PROVIDER=openai
SEARCH_MODEL=gpt-4.1-mini
SEARCH_MAX_SOURCES_PER_PHASE=3
```

Use `SEARCH_PROVIDER=none` for local RAG only. Tavily is supported with `SEARCH_PROVIDER=tavily` and `SEARCH_API_KEY`.

## Start and ingest sources

```powershell
./scripts/setup.ps1
.venv/Scripts/python.exe -m scripts.ingest_all data/sources.tse-2026.json
./scripts/start.ps1
```

To add a public source, create a metadata JSON without secrets or private data:

```json
{
  "candidate_id": "lula",
  "title": "Public policy document",
  "url": "https://example.org/public-document.pdf",
  "publisher": "Public institution",
  "source_type": "government_program",
  "publication_date": null,
  "election_year": 2026
}
```

```powershell
.venv/Scripts/python.exe -m scripts.ingest_candidate --metadata data/my-source.json
.venv/Scripts/python.exe -m scripts.ingest_candidate --metadata data/my-source.json --document C:/path/document.pdf
```

Prefer official election programs, institutional documents, official interviews and clearly attributed reputable journalism. Search snippets are not evidence: a page must be downloaded and extracted successfully before entering the RAG.

## How web research works

At session start the system searches for `candidate name + topic`, followed by a query focused on declarations, interviews and proposals. It tries to read three distinct pages. Failed links, paywalls, login pages and unsafe redirects are never used as evidence. The initial web result is reused throughout the session, while each response retrieves fresh candidate-isolated RAG context based on the latest argument.

## Cost and quality controls

- Candidate playbooks sample the full program at distributed points and are cached locally.
- Evidence passed to generation is size-limited.
- A response can be regenerated once after validation failure.
- Web research is not repeated for every response in the same session.
- The final conceptual fallback makes no additional model call and introduces no new factual claim.

The interface reports processed provider tokens, including input context and rejected attempts. Cached tokens may be billed differently by the provider.

## Public repository checklist

Before publishing, verify that `.env`, `runtime/`, `.venv/`, `node_modules/`, `.next/` and logs are absent from `git status`. Commit only `.env.example` with empty credential fields. Rotate a key immediately if it was ever committed.
