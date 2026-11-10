# ⚽ Bola do Dia — newsletter diária de futebol

Agente automático que, todo dia de manhã, monta e envia por e-mail uma newsletter com o resumo do futebol: principais acontecimentos, estatísticas curiosas, memes e a agenda do dia.

Roda no **GitHub Actions**, usa o **Gemini** para escrever o texto e o **Giphy** para os GIFs.

## O que chega no e-mail

| Seção | Conteúdo |
|---|---|
| ⚽ Principais acontecimentos | 5 a 8 notícias do dia, cada uma com link para a fonte |
| 📊 Dados pro papo de bar | Estatísticas e curiosidades ligadas aos fatos recentes |
| 😂 Memes e resenha do dia | Zoeiras e comentários sobre os acontecimentos |
| 📅 Agenda de hoje | Principais jogos do dia |

- **5 GIFs por edição:** 1 no topo e 1 em cada seção, escolhidos de acordo com o clima das notícias.
- **Visual de arcade anos 90:** cores neon, "fases" no lugar de títulos e fonte monoespaçada.
- Cada destinatário recebe um **e-mail separado** (ninguém vê o endereço dos outros).

## Como funciona

1. O GitHub Actions dispara o workflow (agendado ou manual).
2. `agent.py` coleta notícias das últimas ~36h por RSS (Google Notícias, ge, ESPN e Reddit).
3. O Gemini escreve a newsletter em HTML e sugere 5 termos de busca para os GIFs.
4. O script valida o resultado. Se estiver vazio ou incompleto, tenta de novo; se todas as tentativas falharem, o workflow **falha de propósito** (nunca envia e-mail vazio).
5. O Giphy devolve os GIFs. Se faltar algum, a edição sai sem ele.
6. O e-mail é montado e enviado pelo Gmail (SMTP).

## Estrutura do repositório

```
agent.py                                # o agente
.github/workflows/daily_research.yml    # agendamento e execução
README.md
```

## Configuração

### Secrets (obrigatórios)

Em **Settings → Secrets and variables → Actions → Repository secrets**:

| Secret | Para que serve |
|---|---|
| `GEMINI_API_KEY` | Chave da API do Gemini ([Google AI Studio](https://aistudio.google.com/apikey)) |
| `EMAIL_USER` | Endereço do Gmail que envia a newsletter |
| `EMAIL_APP_PASSWORD` | **Senha de app** do Gmail (exige verificação em duas etapas; não é a senha normal) |
| `EMAIL_TO` | Destinatário(s). Vários endereços separados por `;`, vírgula ou espaço |
| `GIPHY_API_KEY` | Chave da API do Giphy (opcional: sem ela, o e-mail sai sem GIFs) |

Os secrets precisam ser repassados no `env:` do passo que roda o script (já está assim no workflow).

### Variáveis opcionais (no `env:` do workflow)

| Variável | Padrão | O que faz |
|---|---|---|
| `MODEL` | `gemini-3.8-flash` | Modelo principal do Gemini |
| `MODEL_FALLBACK` | _(nenhum)_ | Modelo reserva; se definido, o script alterna com ele nas tentativas |
| `USE_SEARCH` | `0` | `1` liga a busca do Google no Gemini (usa uma cota separada, que costuma estourar no plano gratuito) |

## Uso

- **Automático:** o workflow roda todo dia no horário do `cron`. O padrão `0 8 * * *` é 8h UTC, ou seja, **5h em Brasília**. Para 7h, use `'0 10 * * *'`.
- **Manual:** aba **Actions → Daily Football Research Agent → Run workflow**.
- **Mais destinatários:** edite o secret `EMAIL_TO`, por exemplo `voce@gmail.com; amiga@gmail.com`.

## Tentativas e limites de tempo

- Até **5 tentativas** com o Gemini, com esperas de 30, 60, 90 e 120 segundos.
- Cada chamada tem limite de **5 minutos**.
- O workflow é cancelado sozinho se passar do `timeout-minutes` (45).

## Problemas comuns

| O que aparece no log | O que significa | O que fazer |
|---|---|---|
| `503 UNAVAILABLE` | Modelo do Gemini sobrecarregado | O script tenta de novo. Se persistir, rode mais tarde ou defina `MODEL_FALLBACK` |
| `504 DEADLINE_EXCEEDED` | O Gemini demorou mais que o limite | Mesmo caminho do 503 |
| `429 RESOURCE_EXHAUSTED` | Cota do plano gratuito estourada | Aguardar; usar uma chave de um projeto próprio no Google AI Studio |
| `404 NOT_FOUND` (modelo) | O nome do modelo não existe para a sua conta | Conferir o nome no Google AI Studio |
| `GIPHY_API_KEY ausente` | O workflow não repassou a chave | Conferir o `env:` do workflow e o nome do secret |
| `ESPN ... no element found` ou `Reddit ... 429` | Fontes opcionais indisponíveis | Podem ser ignorados; as outras fontes seguem |
| `Erro fatal: Gemini não gerou conteúdo válido` | Todas as tentativas falharam | Rodar de novo mais tarde |

## Limitações conhecidas

- O agente usa só as notícias coletadas nos feeds (12 itens por feed, últimas ~36h). Eventos grandes que saíram da janela ou ficaram fora dos primeiros itens podem não aparecer.
- Sem a busca do Google, estatísticas e memes ficam limitados ao que veio dos feeds; quando falta meme, o agente escreve comentários próprios e avisa.
- O texto é gerado por IA e pode conter erros. Confira as fontes antes de repassar.
- No Outlook de computador, os GIFs aparecem parados.

## Manutenção

- Em repositórios públicos, o GitHub desativa workflows agendados após 60 dias sem atividade. Se o e-mail parar de chegar sem erro, confira a aba Actions.
- Nunca coloque chaves ou senhas no código. Use sempre os Secrets.
- Em repositório público, o log do Actions é visível; por isso o script não imprime endereços de e-mail.# agente-futebol
