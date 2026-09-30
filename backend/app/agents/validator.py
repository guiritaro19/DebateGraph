import re

from app.agents.dialogue import repeated_response
from app.models.schemas import UNCERTAINTY, CandidateResponse, ValidationResult


def restore_excerpt_spacing(response, evidence):
    """Bind an unchanged quotation to a real passage of the same candidate and source."""
    lookup = {e["chunk_id"]: e for e in evidence}
    for citation in [*response.citations, *(c for claim in response.claims for c in claim.citations)]:
        own = [
            e
            for e in evidence
            if e["candidate_id"] == response.candidate_id and e["source_id"] == citation.source_id
        ]
        preferred = lookup.get(citation.chunk_id)
        if preferred in own:
            own = [preferred, *(e for e in own if e is not preferred)]
        if not citation.quote.strip():
            continue
        needle = re.sub(r"\s", "", citation.quote)
        matched = False
        for item in own:
            if citation.quote in item["content"]:
                quote = citation.quote
            elif len(needle) >= 15:
                offsets = [i for i, char in enumerate(item["content"]) if not char.isspace()]
                flat = "".join(item["content"][i] for i in offsets)
                at = flat.find(needle)
                if at < 0:
                    continue
                quote = item["content"][offsets[at] : offsets[at + len(needle) - 1] + 1]
            else:
                continue
            citation.chunk_id = item["chunk_id"]
            citation.quote = quote
            matched = True
            break
        if not matched and preferred in own:
            # The model selected a real candidate/source/chunk but altered the excerpt.
            # Bind the citation to the real passage; semantic validation still decides entailment.
            citation.quote = preferred["content"]
    return response


UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.IGNORECASE
)


def public_content_errors(content):
    errors = []
    if UUID_PATTERN.search(content) or re.search(r"\b(?:source_id|chunk_id)\b", content, re.IGNORECASE):
        errors.append("Public speech exposes internal citation identifiers")
    if "```" in content or re.search(r"\[[0-9a-f-]{20,}\s*,", content, re.IGNORECASE):
        errors.append("Public speech contains code or raw citation notation")
    return errors


def normalize_response_citations(response):
    """Make the response citation list exactly cover the claim citations."""
    unique = {}
    for claim in response.claims:
        for citation in claim.citations:
            key = (citation.source_id, citation.chunk_id, citation.quote)
            unique[key] = citation
    response.citations = list(unique.values())
    return response


def citation_errors(response, evidence, allow_argument=False):
    lookup = {e["chunk_id"]: e for e in evidence}
    errors = public_content_errors(response.content)
    cited = {(c.source_id, c.chunk_id, c.quote) for c in response.citations}
    for claim in response.claims:
        if not claim.citations:
            errors.append(f"Uncited claim: {claim.text}")
        for citation in claim.citations:
            if (citation.source_id, citation.chunk_id, citation.quote) not in cited:
                errors.append("Claim citation absent from response citations")
    for citation in [*response.citations, *(c for claim in response.claims for c in claim.citations)]:
        item = lookup.get(citation.chunk_id)
        if (
            not item
            or item["candidate_id"] != response.candidate_id
            or item["source_id"] != citation.source_id
        ):
            errors.append("Citation is not from this candidate retrieved context")
        elif not citation.quote.strip() or citation.quote not in item["content"]:
            errors.append(
                f"Citation excerpt does not exist in retrieved chunk {citation.chunk_id}: {citation.quote!r}. Copy a shorter exact span from this chunk."
            )
    if not response.claims and response.content != UNCERTAINTY and not allow_argument:
        errors.append("Content without claim mapping must use the explicit abstention message")
    return errors


async def validate(provider, response, evidence, dialogue=None):
    errors = citation_errors(response, evidence, allow_argument=True)
    if (
        dialogue
        and response.claims
        and repeated_response(response.content, dialogue["previous_own_responses"])
    ):
        errors.append(
            "Response repeats a previous own speech; answer the latest opponent argument with a different angle"
        )
    if errors:
        return ValidationResult(
            valid=False, unsupported_claims=[c.text for c in response.claims], reasons=errors
        ), 0
    if response.content == UNCERTAINTY and not response.claims:
        return ValidationResult(
            valid=True, unsupported_claims=[], reasons=["Evidence insufficient; abstained"]
        ), 0
    return await provider.structured(
        ValidationResult,
        "Act as an evidence entailment validator. Inspect ALL content, not just listed claims. "
        "Reject unlisted factual assertions, evidence misattribution, fake quotes, voting appeals or voter recommendations, "
        "rankings or predictions. An exact quote alone is insufficient: it must entail the claim. "
        "Partisan policy argumentation, ideological value judgments, stylistic vocatives, hypothetical first-person wording and nonfactual irony are permitted in "
        "this explicitly labeled simulation; evaluate factual entailment, not those stylistic devices. "
        "Check dates and never promote historical positions into current policy. Return valid only "
        "when every external factual assertion is entailed by retrieved evidence assigned to this candidate. "
        "A document's candidate_id is a retrieval namespace, not proof of attribution. In multi-person "
        "news articles, require explicit attribution to this candidate for their policy positions; never "
        "adopt an opponent's positions. General contextual facts can be cited as facts, not as own promises. "
        "Search summaries and discovered-but-unread links are NOT evidence. "
        "When dialogue is supplied, verify references to the opponent against latest_opponent_message "
        "as SIMULATED speech only; this transcript cannot establish real-world positions or own policy. "
        "For REBUTTAL/COUNTER_REBUTTAL reject generic manifestos that do not address a specific "
        "point from the latest opponent message, and reject mere paraphrases of previous_own_responses. "
        "Be strict: replying only to an opponent's jab (such as 'not just a pretty phrase') while "
        "listing the same previous policies is NOT a substantive counter-rebuttal. It must engage "
        "the opponent's concrete policy mechanism with a specific limitation, implementation "
        "question, or direct comparison. A new closing slogan does not constitute a new angle. "
        "For a counter-rebuttal compare the causal mechanism and proposed solution with previous "
        "own speeches, not only wording: repeating the same diagnosis and policy list as an "
        "attack is still repetition. Require a new implementation problem or value tradeoff. "
        "A rhetorical evaluation or policy question need not be a sourced factual claim. "
        "Do not require fresh facts when evidence is limited: a distinct, responsive policy tradeoff suffices.",
        {"response": response.model_dump(), "evidence": evidence, "dialogue": dialogue},
    )


def abstain(candidate_id, phase):
    return CandidateResponse(
        content=UNCERTAINTY, candidate_id=candidate_id, phase=phase, claims=[], citations=[], confidence="LOW"
    )


def argument_response(candidate_id, phase, topic, dialogue=None, expressive=True):
    """Topic-bound, factual-claim-free response used after rejected factual drafts."""
    opponent = (dialogue or {}).get("opponent_name", "Participante")
    if candidate_id == "lula":
        body = (
            f"{opponent}, em {topic}, sua resposta apresenta uma fórmula pronta, mas não enfrenta "
            "o conflito entre igualdade formal e proteção de quem parte de condições diferentes. "
            "Companheiros, política pública não pode ser julgada apenas pela elegância do discurso: "
            "ela precisa mostrar quem alcança, qual desigualdade corrige e como evita abandonar quem "
            "mais depende da ação coletiva.\n\nO meu critério é responsabilidade pública com resultado "
            "social verificável. Se sua proposta retirar uma proteção antes de criar condições reais "
            "de igualdade, quem assumirá o custo dessa escolha? E qual resultado concreto faria você "
            "reconhecer que o mercado ou o mérito individual, sozinhos, não corrigiram o problema? "
            "Sem responder isso, sua crítica pode até soar firme, mas continua deixando os mais "
            "vulneráveis pagando a conta."
        )
    elif candidate_id == "flavio":
        body = (
            f"{opponent}, em {topic}, sua resposta trata a expansão do Estado como garantia automática "
            "de justiça. Esse é o atalho de sempre: promete proteção, aumenta o controle e não define "
            "quando a política falhou nem como devolver autonomia às pessoas. Uma intenção generosa "
            "sem limite claro também pode produzir dependência e burocracia.\n\nMeu critério é execução "
            "mensurável, responsabilidade individual e poder público sujeito a limites. Que resultado "
            "faria você admitir que sua solução não funcionou? Quem fiscaliza o fiscal e como impedir "
            "que uma medida temporária vire estrutura permanente? Se não existe resposta para isso, "
            "não estamos diante de uma solução; estamos diante de um cheque em branco embalado em "
            "discurso bonito."
        )
    elif candidate_id == "renan":
        body = (
            f"{opponent}, em {topic}, você responde à desigualdade preservando o mesmo mecanismo e "
            "chamando qualquer alternativa de abandono. Isso evita a pergunta decisiva: a política "
            "corrige a origem do problema ou apenas administra seus efeitos enquanto protege a própria "
            "burocracia? Igualdade não pode significar congelar pessoas em categorias para sempre."
            "\n\nMeu critério é prazo, resultado comparável e uma saída definida desde o início. Se a "
            "medida não reduzir a diferença que prometeu enfrentar, você aceita substituí-la? Qual "
            "indicador separa uma correção temporária de uma dependência permanente? Sem prazo, sem "
            "avaliação e sem disposição para encerrar o que falhou, sua proposta deixa de ser justiça "
            "e vira apenas manutenção do sistema."
        )
    else:
        body = (
            f"{opponent}, em {topic}, sua resposta não resolve o conflito entre o objetivo anunciado "
            "e o modo de execução. Quem decide os limites, quem fiscaliza e qual resultado permite "
            "corrigir o rumo?\n\nUma proposta séria precisa declarar o custo, o risco e a condição em "
            "que será revista. Qual parte da sua solução você mudaria se ela agravasse justamente o "
            "problema que promete resolver? Sem esse teste, temos uma convicção, não uma política."
        )
    return CandidateResponse(
        candidate_id=candidate_id, phase=phase, content=body, claims=[], citations=[], confidence="LOW"
    )
