import html as htmllib
import os
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

# Mantive o modelo que você já usava; se der erro de "model not found",
# troque aqui ou defina a variável MODEL no workflow.
MODEL = os.environ.get("MODEL", "gemini-3.8-flash")

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
  sequências, recordes, desempenho). Diga de onde veio cada número.
<h2>😂 Memes e resenha do dia</h2>
  3 a 5 itens: descreva a piada/meme em 1-2 frases e cite onde bombou (perfil, comunidade).
  Não incorpore imagens. Se não achar memes reais recentes, faça 2-3 comentários
  engraçados seus sobre os fatos do dia e deixe claro que são comentários seus.
<h2>📅 Agenda de hoje</h2>
  Principais jogos do dia, horário de Brasília e onde passa (se confirmar).

REGRAS: não invente placar, número, jogador ou link. Só use <a href> com links que aparecem
no material coletado acima. Se não confirmar algo, deixe de fora. Nada de introdução ou
despedida fora da estrutura."""


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


def chamar_gemini(client, prompt, com_busca: bool):
    config = types.GenerateContentConfig(
        temperature=0.4,
        tools=[types.Tool(google_search=types.GoogleSearch())] if com_busca else None,
    )
    resp = client.models.generate_content(model=MODEL, contents=prompt, config=config)
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


def gerar_newsletter(noticias, memes):
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = montar_prompt(noticias, memes)
    ultimo_erro = None

    # 2 tentativas com busca; última sem busca (caso a ferramenta falhe)
    for tentativa, com_busca in enumerate([True, True, False], start=1):
        try:
            print(f"Gemini: tentativa {tentativa} ({'com' if com_busca else 'sem'} busca)...")
            texto, resp = chamar_gemini(client, prompt, com_busca)
            validar(texto)
            fontes = extrair_fontes(resp)
            if fontes:
                lis = "".join(f'<li><a href="{u}">{htmllib.escape(t)}</a></li>' for t, u in fontes)
                texto += f'<h3 style="color:#777;">🔎 Fontes consultadas na busca</h3><ul>{lis}</ul>'
            return texto
        except Exception as e:
            ultimo_erro = e
            print(f"  falhou: {e}", file=sys.stderr)
            time.sleep(8 * tentativa)
    raise RuntimeError(f"Gemini não gerou conteúdo válido: {ultimo_erro}")


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------
def montar_email(conteudo: str) -> str:
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#f4f4f4;">
<div style="max-width:640px;margin:0 auto;background:#fff;padding:24px;
font-family:Arial,Helvetica,sans-serif;color:#222;line-height:1.5;">
<h1 style="margin:0;">⚽ Bola do Dia</h1>
<p style="margin:0 0 20px;color:#777;">{DATA}</p>
{conteudo}
<hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
<p style="color:#999;font-size:12px;">Gerado automaticamente por IA. Confira as fontes antes de bater o martelo no bar.</p>
</div></body></html>"""


def send_email(html_content: str):
    print("Enviando e-mail...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"⚽ Bola do Dia — {DATA}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(html_content, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
    print("E-mail enviado com sucesso!")


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
        conteudo = gerar_newsletter(noticias, memes)
    except Exception as e:
        print(f"Erro fatal: {e}", file=sys.stderr)
        sys.exit(1)  # workflow fica vermelho em vez de mandar e-mail vazio

    send_email(montar_email(conteudo))
