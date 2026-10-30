import html as htmllib
import os
import random
import re
import smtplib
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

import requests
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# Configuração (mesmos secrets de antes)
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")
GIPHY_API_KEY = os.environ.get("GIPHY_API_KEY")  # opcional: sem ela, vai sem GIF

# Mantive o modelo que você já usava; se der erro de "model not found",
# troque aqui ou defina a variável MODEL no workflow.
MODEL = os.environ.get("MODEL", "gemini-3.8-flash")
# Busca do Google no Gemini: desligada por padrão (a cota gratuita dela costuma estourar).
# Para ligar, defina USE_SEARCH=1 no env do workflow.
USE_SEARCH = os.environ.get("USE_SEARCH", "0") == "1"
# Limite de tempo de cada chamada ao Gemini (em milissegundos). Sem isso, uma chamada
# que trava pode deixar o workflow preso por horas.
TIMEOUT_GEMINI_MS = 300_000  # 5 minutos

AGORA = datetime.now(ZoneInfo("America/Sao_Paulo"))
DATA = AGORA.strftime("%d/%m/%Y")
JANELA = timedelta(hours=36)  # só notícias das últimas 36h
UA = "Mozilla/5.0 (compatible; NewsletterFutebol/1.0)"

# (nome, url, categoria)  categoria: "noticias" ou "memes"
FEEDS = [
    ("Google Notícias · Futebol",
     "https://news.google.com/rss/search?q=futebol+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419", "noticias"),
    ("Google Notícias · Brasileirão",
     "https://news.google.com/rss/search?q=Brasileir%C3%A3o+OR+Libertadores+OR+Copa+do+Brasil+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419", "noticias"),
    ("Google Notícias · Europa",
     "https://news.google.com/rss/search?q=Champions+League+OR+Premier+League+OR+La+Liga+OR+Serie+A+when:1d&hl=pt-BR&gl=BR&ceid=BR:pt-419", "noticias"),
    ("Google Notícias · Seleção",
     "https://news.google.com/rss/search?q=Sele%C3%A7%C3%A3o+Brasileira+when:2d&hl=pt-BR&gl=BR&ceid=BR:pt-419", "noticias"),
    ("ESPN Soccer", "https://www.espn.com/espn/rss/soccer/news", "noticias"),
    ("ge", "https://ge.globo.com/rss/ge/futebol/", "noticias"),
    # Reddit costuma bloquear IPs de datacenter; é "melhor esforço".
    ("Reddit r/futebol", "https://www.reddit.com/r/futebol/top/.rss?t=day", "memes"),
    ("Reddit r/soccercirclejerk", "https://www.reddit.com/r/soccercirclejerk/top/.rss?t=day", "memes"),
]


# ---------------------------------------------------------------------------
# Coleta de feeds (RSS e Atom)
# ---------------------------------------------------------------------------
def limpar(texto: str, limite: int = 220) -> str:
    texto = htmllib.unescape(texto or "")
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:limite]


def parse_data(texto):
    if not texto:
        return None
    try:
        dt = parsedate_to_datetime(texto)
    except Exception:
        try:
            dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def ler_feed(nome: str, url: str, max_itens: int = 12):
    r = requests.get(url, timeout=15, headers={"User-Agent": UA})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    itens = []

    # RSS 2.0
    for it in root.findall(".//item"):
        itens.append({
            "titulo": limpar(it.findtext("title"), 200),
            "resumo": limpar(it.findtext("description")),
            "link": (it.findtext("link") or "").strip(),
            "data": parse_data(it.findtext("pubDate")),
        })

    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for en in root.findall(f".//{ns}entry"):
        link_el = en.find(f"{ns}link")
        itens.append({
            "titulo": limpar(en.findtext(f"{ns}title"), 200),
            "resumo": limpar(en.findtext(f"{ns}content") or en.findtext(f"{ns}summary")),
            "link": link_el.get("href", "") if link_el is not None else "",
            "data": parse_data(en.findtext(f"{ns}updated") or en.findtext(f"{ns}published")),
        })

    limite = datetime.now(timezone.utc) - JANELA
    recentes = [i for i in itens if i["titulo"] and (i["data"] is None or i["data"] >= limite)]
    return recentes[:max_itens]


def coletar():
    noticias, memes, vistos = [], [], set()
    for nome, url, categoria in FEEDS:
        try:
            itens = ler_feed(nome, url)
            print(f"[ok]   {nome}: {len(itens)} itens")
        except Exception as e:
            print(f"[erro] {nome}: {e}", file=sys.stderr)
            continue
        for i in itens:
            chave = re.sub(r"\W+", "", i["titulo"].lower())[:60]
            if chave in vistos:
                continue
            vistos.add(chave)
            linha = f"- [{nome}] {i['titulo']}"
            if i["resumo"] and i["resumo"].lower() not in i["titulo"].lower():
                linha += f" — {i['resumo']}"
            if i["link"]:
                linha += f" ({i['link']})"
            (memes if categoria == "memes" else noticias).append(linha)
    return noticias, memes


# ---------------------------------------------------------------------------
# Geração com Gemini (+ busca do Google para completar estatísticas e memes)
# ---------------------------------------------------------------------------
def montar_prompt(noticias, memes):
    bloco_noticias = "\n".join(noticias[:45]) or "(nenhum item coletado dos feeds)"
    bloco_memes = "\n".join(memes[:15]) or "(nenhum item coletado)"
    return f"""Hoje é {DATA}. Você é o editor da newsletter diária "Bola do Dia": informado,
bem-humorado, em português do Brasil. Monte a edição de hoje de manhã.

MATERIAL COLETADO DOS FEEDS (últimas ~36h):
{bloco_noticias}

POSTS DE HUMOR/MEMES COLETADOS (Reddit, podem estar vazios):
{bloco_memes}

Você também tem busca na web: use-a para confirmar placares/fatos, achar estatísticas
recentes e encontrar memes e zoeiras que viralizaram nas últimas 24-48h.

ESTRUTURA OBRIGATÓRIA (HTML limpo, só o conteúdo do <body>, sem ```):
<h2>⚽ Principais acontecimentos</h2>
  5 a 8 itens: manchete em <b>negrito</b> + 1-2 frases. Priorize resultados de ontem e o que
  rola hoje.
<h2>📊 Dados pro papo de bar</h2>
  3 a 5 estatísticas curiosas e VERIFICÁVEIS ligadas aos fatos recentes (artilharia,
  sequências, recordes, desempenho). Diga de onde veio cada número. Não repita os mesmos
  fatos da seção de acontecimentos: traga números e ângulos diferentes.
<h2>😂 Memes e resenha do dia</h2>
  3 a 5 itens: descreva a piada/meme em 1-2 frases e cite onde bombou (perfil, comunidade).
  Não incorpore imagens. Notícia comum NÃO é meme: só vale piada, zoeira ou post de humor.
  Se não achar memes reais recentes, faça 2-3 comentários
  engraçados seus sobre os fatos do dia e deixe claro que são comentários seus.
<h2>📅 Agenda de hoje</h2>
  Principais jogos do dia, horário de Brasília e onde passa (se confirmar).

REGRAS: não invente placar, número, jogador ou link. Só use <a href> com links que aparecem
no material coletado acima. Se não confirmar algo, deixe de fora. Nada de introdução ou
despedida fora da estrutura.
FORMATO: responda SOMENTE em HTML (<h2>, <ul><li>, <b>, <a href>). NÃO use Markdown
(nada de **, #, * no início de linha ou [texto](url)).
ÚLTIMAS 5 LINHAS da resposta, depois do HTML: uma busca de GIF por linha, com 2 a 4 palavras
em inglês, exatamente nesta ordem:
GIF1: clima geral do dia (topo da newsletter)
GIF2: clima da notícia principal da seção de acontecimentos
GIF3: tema da seção de dados (números, análise)
GIF4: clima da seção de memes (risada, zoeira)
GIF5: clima da agenda (bola rolando, expectativa)
Exemplos de termos: coach fired shock / last minute goal celebration / nerd calculating /
laughing crying / ready to play football."""


def extrair_fontes(resp):
    """Pega os links reais usados pela busca do Google (grounding)."""
    fontes = []
    try:
        meta = resp.candidates[0].grounding_metadata
        for ch in (meta.grounding_chunks or []):
            if ch.web and ch.web.uri:
                fontes.append((ch.web.title or ch.web.uri, ch.web.uri))
    except Exception:
        pass
    vistos, unicas = set(), []
    for t, u in fontes:
        if u not in vistos:
            vistos.add(u)
            unicas.append((t, u))
    return unicas[:8]


def chamar_gemini(client, prompt, com_busca: bool, modelo: str):
    config = types.GenerateContentConfig(
        temperature=0.4,
        tools=[types.Tool(google_search=types.GoogleSearch())] if com_busca else None,
    )
    resp = client.models.generate_content(model=modelo, contents=prompt, config=config)
    texto = (resp.text or "").strip()  # resp.text pode vir None (bloqueio/filtro)
    texto = re.sub(r"^```(?:html)?\s*|\s*```$", "", texto).strip()
    return texto, resp


def validar(conteudo: str):
    sem_tags = re.sub(r"<[^>]+>", "", conteudo).strip()
    if len(sem_tags) < 700:
        raise ValueError(f"conteúdo curto demais ({len(sem_tags)} caracteres)")
    for secao in ("acontecimentos", "papo de bar", "memes", "agenda"):
        if secao not in conteudo.lower():
            raise ValueError(f"seção ausente: {secao}")


def md_para_html(t: str) -> str:
    """Rede de segurança: se o modelo devolver Markdown, converte para HTML."""

    def inline(s):
        s = htmllib.escape(s, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)
        return s

    saida, em_lista = [], False
    for linha in t.splitlines():
        l = linha.strip()
        m_item = re.match(r"^[\*\-•]\s+(.*)", l)
        if m_item:
            if not em_lista:
                saida.append("<ul>")
                em_lista = True
            saida.append(f"<li>{inline(m_item.group(1))}</li>")
            continue
        if em_lista:
            saida.append("</ul>")
            em_lista = False
        if not l:
            continue
        m_tit = re.match(r"^#{1,6}\s*(.*)", l)
        if m_tit:
            saida.append(f"<h2>{inline(m_tit.group(1))}</h2>")
        elif re.match(r"^(\*\*)?[⚽📊😂📅]", l):  # título com emoji, sem '#'
            saida.append(f"<h2>{inline(l)}</h2>")
        else:
            saida.append(f"<p>{inline(l)}</p>")
    if em_lista:
        saida.append("</ul>")
    return "\n".join(saida)


def gerar_newsletter(noticias, memes):
    try:
        client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=TIMEOUT_GEMINI_MS),
        )
    except Exception as e:  # biblioteca antiga sem esse parâmetro: segue sem limite
        print(f"Aviso: não foi possível definir timeout ({e}).", file=sys.stderr)
        client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = montar_prompt(noticias, memes)
    ultimo_erro = None

    fallback = os.environ.get("MODEL_FALLBACK")  # opcional; sem padrão
    sem_busca = ("\n\nATENÇÃO: hoje a busca na web está indisponível. Use APENAS o material "
                 "coletado acima. Em 'Dados' e 'Memes', use só o que está no material; se não "
                 "houver, faça comentários seus, deixando claro que são comentários seus.")
    # Sem busca por padrão. Com USE_SEARCH=1, a 1ª tentativa usa busca e as demais não.
    # 5 tentativas com esperas crescentes (30s, 60s, 90s, 120s) para aguentar picos de 503.
    if fallback and fallback != MODEL:
        # Alterna com o modelo reserva para não ficar só insistindo no que está sobrecarregado.
        plano = [(MODEL, USE_SEARCH), (MODEL, False), (fallback, False),
                 (MODEL, False), (fallback, False)]
    else:
        plano = [(MODEL, USE_SEARCH)] + [(MODEL, False)] * 4
    for tentativa, (modelo, com_busca) in enumerate(plano, start=1):
        try:
            print(f"Gemini: tentativa {tentativa} ({modelo}, {'com' if com_busca else 'sem'} busca)...")
            texto, resp = chamar_gemini(client, prompt if com_busca else prompt + sem_busca,
                                        com_busca, modelo)
            texto, termos_gif = extrair_gifs(texto)
            if "<h2" not in texto.lower():  # modelo devolveu Markdown: converte
                texto = md_para_html(texto)
            validar(texto)
            fontes = extrair_fontes(resp)
            if fontes:
                lis = "".join(f'<li><a href="{u}">{htmllib.escape(t)}</a></li>' for t, u in fontes)
                texto += f'<h3 style="color:#777;">🔎 Fontes consultadas na busca</h3><ul>{lis}</ul>'
            return texto, termos_gif
        except Exception as e:
            ultimo_erro = e
            print(f"  falhou: {e}", file=sys.stderr)
            if tentativa < len(plano):
                time.sleep(30 * tentativa)
    raise RuntimeError(f"Gemini não gerou conteúdo válido: {ultimo_erro}")


# ---------------------------------------------------------------------------
# GIFs do dia (Giphy): 1 no topo + 1 em cada seção
# ---------------------------------------------------------------------------
N_GIFS = 5
# Termos de reserva por posição (topo, acontecimentos, dados, memes, agenda),
# usados se o modelo não mandar o termo ou se a busca não achar nada.
GIF_RESERVA = [
    "football celebration",
    "soccer goal",
    "nerd calculating",
    "laughing soccer fans",
    "ready to play football",
]


def extrair_gifs(texto: str):
    """Tira do texto as linhas 'GIF1: termo' ... 'GIF5: termo' pedidas ao modelo."""
    termos = [None] * N_GIFS
    padrao = re.compile(r"^[ \t]*\**GIF[ \t]*([1-5])?[ \t]*:\**[ \t]*(.+?)[ \t]*$",
                        re.MULTILINE | re.IGNORECASE)

    def coleta(m):
        pos = int(m.group(1)) - 1 if m.group(1) else 0
        termo = re.sub(r"[^\w\s'-]", "", m.group(2)).strip()[:60]
        if termo and termos[pos] is None:
            termos[pos] = termo
        return ""

    return padrao.sub(coleta, texto).strip(), termos


def buscar_gif(termo, usados: set):
    """Busca no Giphy e devolve a URL de um GIF ainda não usado. Nunca levanta erro."""
    if not termo:
        return None
    try:
        r = requests.get(
            "https://api.giphy.com/v1/gifs/search",
            timeout=15,
            params={"api_key": GIPHY_API_KEY, "q": termo, "limit": 15,
                    "rating": "pg", "lang": "en"},
        )
        r.raise_for_status()
        dados = r.json().get("data", [])
    except Exception as e:
        print(f"Aviso: Giphy falhou para '{termo}' ({e}).", file=sys.stderr)
        return None
    random.shuffle(dados)
    for g in dados:
        imgs = g.get("images", {})
        for tam in ("downsized", "downsized_medium", "fixed_height", "original"):
            url = (imgs.get(tam) or {}).get("url")
            if url and url not in usados:
                return url
    return None


def buscar_gifs(termos):
    """Devolve N_GIFS URLs (None onde não deu para achar). Nunca derruba o envio."""
    if not GIPHY_API_KEY:
        print("GIPHY_API_KEY ausente: seguindo sem GIFs.")
        return [None] * N_GIFS
    usados, urls = set(), []
    for i in range(N_GIFS):
        termo = termos[i] if i < len(termos) else None
        url = buscar_gif(termo, usados) or buscar_gif(GIF_RESERVA[i], usados)
        if url:
            usados.add(url)
        print(f"GIF {i + 1} (busca '{termo}'): {url}")
        urls.append(url)
        time.sleep(0.5)
    return urls


# ---------------------------------------------------------------------------
# Visual do e-mail: estilo arcade anos 90, cores atuais (estilos inline p/ Gmail)
# ---------------------------------------------------------------------------
DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
CORES = ["#a3ff12", "#22d3ee", "#ff2e93", "#fde047"]  # lima, ciano, rosa, amarelo
ROTULOS = ["FASE 1", "FASE 2", "BÔNUS", "PRÓXIMA FASE"]
MONO = "'Courier New',Courier,monospace"


def estilizar(html: str, cor_link: str = "#22d3ee") -> str:
    html = re.sub(r"<ul(?:\s[^>]*)?>",
                  '<ul style="margin:12px 0 0 0;padding-left:22px;list-style-type:square;">', html)
    html = re.sub(r"<li(?:\s[^>]*)?>", '<li style="margin:0 0 12px 0;">', html)
    html = re.sub(
        r"<a\s+",
        f'<a style="color:{cor_link};font-weight:700;text-decoration:none;'
        f'border-bottom:2px solid {cor_link};" ',
        html,
    )
    return html


def montar_email(conteudo: str, gifs=None) -> str:
    gifs = list(gifs or []) + [None] * N_GIFS  # posição 0 = topo; 1..4 = seções
    corpo, sep, fontes = conteudo.partition("<h3")
    fontes = ((sep + fontes) if sep else "").replace("color:#777;", "color:#a78bfa;")
    partes = re.split(r"(?i)(<h2[^>]*>.*?</h2>)", corpo, flags=re.DOTALL)

    def img(url, cor, largura):
        if not url:
            return ""
        return (f'<img src="{url}" alt="GIF" style="display:block;width:100%;'
                f'max-width:{largura}px;height:auto;margin:14px auto 6px auto;'
                f'border:3px solid {cor};">')

    def caixa(cor):  # moldura com "sombra dura" feita com bordas (funciona em qualquer cliente)
        return (f"background:#160b3a;color:#f5f3ff;border:3px solid #f5f3ff;"
                f"border-right:8px solid {cor};border-bottom:8px solid {cor};"
                f"padding:18px 20px;margin:0 0 22px 0;")

    cards = []
    for i in range(1, len(partes) - 1, 2):
        n = i // 2
        titulo = re.sub(r"(?i)</?h2[^>]*>", "", partes[i]).strip()
        texto = estilizar(partes[i + 1].strip(), CORES[1])
        cor = CORES[n % len(CORES)]
        rotulo = ROTULOS[n % len(ROTULOS)]
        gif = gifs[n + 1]
        etiqueta = (f'<span style="display:inline-block;background:{cor};color:#0b0620;'
                    f"font-family:{MONO};font-weight:700;font-size:12px;letter-spacing:2px;"
                    f'padding:3px 10px;margin:0 0 8px 0;">{rotulo}</span>')
        h2 = (f'<h2 style="margin:0;font-family:{MONO};font-size:20px;line-height:1.3;'
              f'color:#ffffff;text-transform:uppercase;letter-spacing:1px;">{titulo}</h2>')
        if gif:  # GIF pequeno à esquerda do título
            cabecalho = (
                '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                'border="0"><tr>'
                '<td width="110" valign="middle" style="padding:0 14px 0 0;">'
                f'<img src="{gif}" alt="GIF" width="96" style="display:block;width:96px;'
                f'height:auto;border:3px solid {cor};"></td>'
                f'<td valign="middle">{etiqueta}{h2}</td></tr></table>'
            )
        else:
            cabecalho = etiqueta + h2
        cards.append(f'<div style="{caixa(cor)}">{cabecalho}{texto}</div>')
    if not cards:  # rede de segurança: sem <h2>, vira um cartão só
        cards.append(f'<div style="{caixa(CORES[0])}">{estilizar(corpo, CORES[1])}</div>')

    data_ext = (f"{DIAS[AGORA.weekday()]}, {AGORA.day} de "
                f"{MESES[AGORA.month - 1]} de {AGORA.year}")
    bloco_fontes = (f'<div style="font-size:12px;color:#a78bfa;margin:0 0 22px 0;">'
                    f"{estilizar(fontes, '#a78bfa')}</div>") if fontes else ""
    credito = "<br>GIFs via GIPHY" if any(gifs[:N_GIFS]) else ""

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;background:#0b0620;">
<div style="max-width:640px;margin:0 auto;padding:16px;font-family:Arial,Helvetica,sans-serif;
font-size:15px;line-height:1.55;color:#f5f3ff;">
<div style="{caixa(CORES[0])}text-align:center;">
<div style="font-family:{MONO};font-size:12px;letter-spacing:3px;color:#fde047;font-weight:700;">1UP ● PLAYER 1 ● PRESS START</div>
<h1 style="margin:10px 0 4px 0;font-family:{MONO};font-size:38px;line-height:1.05;letter-spacing:3px;color:#a3ff12;text-transform:uppercase;text-shadow:3px 3px 0 #ff2e93;">⚽ Bola do Dia</h1>
<div style="font-family:{MONO};font-size:13px;letter-spacing:1px;color:#cbd5e1;text-transform:uppercase;">{data_ext}</div>
{img(gifs[0], CORES[1], 300)}
</div>
{''.join(cards)}
{bloco_fontes}
<div style="text-align:center;font-family:{MONO};color:#a78bfa;font-size:12px;letter-spacing:1px;padding:4px 12px 20px 12px;">
<div style="color:#fde047;font-weight:700;font-size:14px;margin:0 0 8px 0;">GAME OVER? NUNCA. TEM EDIÇÃO NOVA AMANHÃ ⚽</div>
Gerado automaticamente por IA. Confira as fontes antes de bater o martelo no bar.{credito}
</div>
</div></body></html>"""


def lista_destinatarios(bruto) -> list:
    """Aceita vários e-mails em EMAIL_TO, separados por ; , espaço ou quebra de linha."""
    return [e.strip() for e in re.split(r"[;,\s]+", bruto or "") if e.strip()]


def send_email(html_content: str):
    destinatarios = lista_destinatarios(EMAIL_TO)
    if not destinatarios:
        raise ValueError("EMAIL_TO está vazio.")

    # Os endereços não vão para o log (em repositório público o log é visível).
    print(f"Enviando e-mail para {len(destinatarios)} destinatário(s)...")
    enviados, falhas = 0, []
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        for i, destino in enumerate(destinatarios, start=1):
            msg = MIMEMultipart("alternative")  # um e-mail separado para cada pessoa
            msg["Subject"] = f"⚽ Bola do Dia — {DATA}"
            msg["From"] = EMAIL_USER
            msg["To"] = destino
            msg.attach(MIMEText(html_content, "html", "utf-8"))
            try:
                server.sendmail(EMAIL_USER, [destino], msg.as_string())
                enviados += 1
            except Exception as e:  # uma falha não impede os outros envios
                falhas.append(i)
                print(f"Falha ao enviar para o destinatário #{i}: {e}", file=sys.stderr)
            time.sleep(1)

    print(f"E-mails enviados: {enviados}/{len(destinatarios)}")
    if enviados == 0:
        raise RuntimeError("Nenhum e-mail foi enviado.")
    if falhas:
        print(f"Aviso: falharam os destinatários #{falhas}.", file=sys.stderr)


if __name__ == "__main__":
    faltando = [n for n in ("GEMINI_API_KEY", "EMAIL_USER", "EMAIL_APP_PASSWORD", "EMAIL_TO")
                if not os.environ.get(n)]
    if faltando:
        print(f"Erro: variáveis ausentes: {', '.join(faltando)}", file=sys.stderr)
        sys.exit(1)

    print("Coletando feeds...")
    noticias, memes = coletar()
    print(f"Total: {len(noticias)} notícias, {len(memes)} posts de humor")

    if len(noticias) < 5:
        print("Aviso: poucas notícias nos feeds; a busca do Gemini vai compensar.", file=sys.stderr)

    try:
        conteudo, termos_gif = gerar_newsletter(noticias, memes)
    except Exception as e:
        print(f"Erro fatal: {e}", file=sys.stderr)
        sys.exit(1)  # workflow fica vermelho em vez de mandar e-mail vazio

    print(f"Termos de GIF: {termos_gif}")
    gifs = buscar_gifs(termos_gif)
    send_email(montar_email(conteudo, gifs))
