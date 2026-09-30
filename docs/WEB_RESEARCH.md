# Pesquisa web por fase

O modo público usa somente Lula, Flávio Bolsonaro, Augusto Cury, Ronaldo Caiado e Renan Santos. Documentos sintéticos e provedores fictícios permanecem exclusivamente como infraestrutura de testes automatizados.

Com `SEARCH_PROVIDER=openai`, a pesquisa usa a chave OpenAI já configurada e `SEARCH_MODEL=gpt-4.1-mini`. Não requer uma chave adicional. Cada pergunta pesquisa os participantes, e cada resposta, réplica e tréplica pesquisa a partir do argumento mais recente do adversário. Novas rodadas repetem a pesquisa. O nó `search_web_per_phase` aparece no subgrafo do candidato.

A busca retorna URLs. Somente páginas públicas de domínios permitidos, baixadas e extraídas com sucesso, entram no RAG. Resumos do buscador não são evidências. Fontes novas relevantes são recuperadas explicitamente junto ao acervo local, com isolamento por participante. Artigos sobre várias pessoas não estabelecem posições próprias: o validador exige atribuição explícita. Fatos gerais podem contextualizar o debate sem se tornarem promessas dos candidatos.

Título, publicador, URL e data observada são armazenados. Não inventamos datas ausentes. Cada fase registra consulta, fontes descobertas, situação de ingestão, erros e tokens no estado e nos eventos exportados. A interface atualiza as fontes durante o debate.

A busca começa por nome do candidato + tema (por exemplo, Renan Santos cotas raciais) e uma consulta complementar por declarações e entrevistas. Procura ler três resultados relevantes por fase, tentando os próximos links quando um falha. Se menos de três páginas puderem ser lidas, registra a pesquisa como parcial, sem inventar fontes. A ordem é de relevância retornada pelo buscador, não uma medição dos links mais acessados. O limite padrão é três fontes por pesquisa, com recortes de até 16 mil caracteres por página. Configuração: `SEARCH_MAX_SOURCES_PER_PHASE` e `SEARCH_DOMAINS`. Pesquisa e embeddings acrescentam custo de API e tempo de execução. `SEARCH_PROVIDER=none` mantém apenas o RAG local; `tavily` requer `SEARCH_API_KEY`. Em falha de busca ou leitura, o debate continua com evidências locais e registra a indisponibilidade.

A geração identifica o adversário e a última fala, evita repetir respostas próprias e prefere trechos ainda não usados. O validador verifica fontes e confronto substantivo: responder apenas à ironia repetindo as propostas iniciais não basta. Quando um fato novo não passa pela validação, a fala continua como argumento conceitual ou pergunta incisiva, sem criar estatísticas, promessas ou acusações. A frase de recusa por falta de evidências é bloqueada antes da transmissão. O repertório amplo é abstraído dos programas completos e armazenado em cache local; mudanças nos documentos invalidam o cache.

Para executar uma verificação real de descoberta, leitura, indexação e recuperação: `python -m scripts.check_web_research`. Para repetir apenas uma tréplica de uma sessão existente: `python -m scripts.check_counter_context SESSION_ID`. Esses testes fazem chamadas reais à API. Os testes em `backend/tests` usam provedores controlados e não acessam a internet.

O nó `plan_argument` antecede cada resposta: resume o ponto do adversário, explicita o conflito ideológico, desenvolve consequências e escolhe um ângulo novo. A direção solicitada para Lula enfatiza proteção coletiva e atuação estatal; para Flávio, autonomia, liberdade econômica e responsabilidade fiscal. Esses enquadramentos orientam a simulação, sem substituir evidências para promessas ou fatos atribuídos aos participantes. Os programas completos alimentam um repertório por área, com citações anexadas dos trechos reais e validação semântica antes do cache.


Perfis amplos têm limites estruturais de oito posições curtas e duas referências por posição. Uma resposta truncada ou indisponível nessa etapa não encerra o debate: a geração segue com RAG temático e pesquisa web.
