# Marvel Multiverse — Quiz Generator

Projeto Python independente que coleta contexto Marvel, pede perguntas estruturadas a uma IA,
valida cada resposta contra as fontes, elimina duplicatas e insere somente perguntas verificadas
na coleção `quiz`. Ele nunca ativa o Quiz Diário; esse papel pertence ao `quiz-updater-daily`.

## Arquitetura

```text
CLI -> configuração -> Comic Vine -> web opcional -> Groq/LangChain + Pydantic
    -> validação factual -> duplicidade -> Firestore batch
```

O `Projeto de IA` foi usado somente como referência arquitetural. Foram mantidos os padrões
úteis já adotados ali: configuração por `.env`, LangChain, `ChatGroq`, Pydantic, prompts
separados e retry limitado. Nenhum módulo é importado daquele projeto. O provider padrão é
Groq, com `openai/gpt-oss-120b`, que oferece structured outputs; o resultado ainda passa por
validação determinística local.

## Fontes e proteção contra hallucination

Comic Vine é a fonte primária. O cliente busca recursos em lote, respeita intervalo entre
páginas, aplica retries limitados e só aceita registros ligados ao publisher Marvel. Para
`POWERS`, os poderes são coletados por personagens Marvel, evitando poderes sem vínculo de
editora. Cada contexto recebe referência curta, por exemplo `comicvine:character:1443`.

O prompt proíbe conhecimento externo e exige que resposta correta, `supportingFact` e
`sourceReferences` estejam no contexto. O código confirma que:

- existem ao menos quatro alternativas distintas e apenas um índice selecionado;
- dificuldade e categoria pertencem ao contrato Android e respeitam o filtro CLI;
- a resposta correta e a evidência aparecem na fonte referenciada;
- referências foram realmente fornecidas ao modelo;
- recompensa é normalizada para EASY=25, MEDIUM=50 e HARD=100;
- a pergunta não é duplicata exata nem uma paráfrase simples de pergunta existente/gerada.

Perguntas aprovadas recebem `generatedByAi=true`, `verified=true`, fontes, timestamps do
servidor, `isDailyQuiz=false` e `dailyQuizDate=null`. `supportingFact` é usado durante a
verificação, mas não é persistido para evitar duplicar conteúdo de fonte.

### Web opcional

O projeto anterior não possuía busca web. Por isso esta ferramenta usa uma abstração pequena e
desativada por padrão. Se `WEB_SEARCH_PROVIDER=tavily`, uma única busca em lote complementa o
contexto e os resultados são aceitos apenas de `WEB_TRUSTED_DOMAINS` (padrão `marvel.com`).
Falha na web gera warning e o pipeline continua com Comic Vine. Use `--source mixed` para
habilitar esse enriquecimento; `--no-web` o desliga explicitamente.

## Configuração local

Requer Python 3.11+.

```bash
python -m venv .venv
.venv/Scripts/activate
python -m pip install -r requirements.txt
copy .env.example .env
```

Preencha `COMIC_VINE_API_KEY`, `GROQ_API_KEY` e a credencial Firebase local. `GROQ_API_KEY`
aceita uma chave ou várias chaves na ordem de fallback, separadas por `|`; quando uma chave
atinge cota/rate limit, a próxima é usada sem expor valores nos logs. O arquivo esperado
é `firebase-service-account.json`, ou outro caminho em `FIREBASE_CREDENTIALS_PATH`. Ambos `.env`
e credenciais são ignorados pelo Git. O banco deste workspace usa ID `default`.

Comic Vine documenta limite e uso não comercial; confira os termos antes de produção:
<https://comicvine.gamespot.com/api/>.

## CLI

```bash
python -m src.main --count 10
python -m src.main --count 50 --difficulty MIXED
python -m src.main --count 20 --category CHARACTERS
python -m src.main --count 15 --category POWERS --difficulty HARD
python -m src.main --count 10 --dry-run
python -m src.main --count 10 --source mixed
python -m src.main --count 10 --source mixed --no-web
python -m src.main --count 10 --model openai/gpt-oss-20b
```

`--count` aceita 1–200, permitindo que todos os inserts de uma execução permaneçam em um único
batch. O dry-run ainda consulta Comic Vine, IA e Firestore (para duplicidade), mas não insere.
Se o pipeline não alcançar a quantidade pedida após chamadas limitadas, falha antes do insert.

Se Groq responder que a cota, créditos ou limite de tokens/requisições foi atingido, a execução
é interrompida antes do batch, registra um warning explicando a indisponibilidade e termina com
sucesso (`exit code 0`). O mesmo comportamento é aplicado aos limites HTTP 420/429 da Comic
Vine. Assim, falta temporária de cota não aparece como defeito do código nem gera inserts
parciais; erros reais de configuração, autenticação ou implementação continuam falhando.

## GitHub Actions e Secrets

`.github/workflows/generate-quiz.yml` possui `workflow_dispatch` com `count`, `difficulty`,
`category`, `source` e `dry_run`. Há um cron semanal comentado, pronto para ativação. Secrets:

- `FIREBASE_SERVICE_ACCOUNT_JSON` — JSON completo da Service Account;
- `COMIC_VINE_API_KEY`;
- `GROQ_API_KEY` — uma chave ou uma lista ordenada separada por `|`;
- `WEB_SEARCH_API_KEY` — opcional, somente para Tavily.

Para web, configure também a variável do repositório `WEB_SEARCH_PROVIDER=tavily` e, se quiser,
`WEB_TRUSTED_DOMAINS`. Nenhuma chave é registrada nos logs ou gravada no checkout.

## Testes

```bash
python -m unittest discover -s tests -v
```

Os testes usam mocks para Comic Vine, LLM, Firebase e web. Cobrem schema, alternativas,
índice, dificuldade, categoria, recompensa, normalização, duplicidade, validação factual,
filtragem Marvel/domínios confiáveis, payload Firestore e dry-run sem insert.
