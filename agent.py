import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from google import genai
from google.genai import types

# 1. Configurar credenciais a partir das variáveis de ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_latest_football_news():
    """Puxa notícias e dados recentes de futebol de forma leve via RSS para evitar bloqueios de cota."""
    queries = [
        "futebol brasileiro resultados placar brasileirao copa do brasil",
        "futebol internacional champions league laliga premier league resultados placar",
        "estatisticas futebol xG opta placar jogos ontem hoje"
    ]
    raw_data = []
    
    for query in queries:
        try:
            url = f"https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-415"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                raw_data.append(response.text[:3500])
        except Exception as e:
            print(f"Aviso ao coletar notícias para '{query}': {e}")
            
    combined_content = "\n\n".join(raw_data)
    return combined_content if combined_content else "Foco nos principais jogos, análises táticas e métricas recentes da Europa."

def curate_and_verify_facts(raw_news):
    """
    AGENTE 1 (Curador / Fact-Checker):
    Saneia os dados brutos, exige a presença do placar numérico para ancorar o resultado real 
    e descarta artigos de opinião imprecisos ou ligas de base/juvenis.
    """
    curation_prompt = f"""
    És um curador rigoroso de dados desportivos e checador de factos de futebol.
    Analisa o seguinte conteúdo bruto de notícias das últimas 24 horas:
    ---
    {raw_news}
    ---

    A tua missão é extrair um relatório factual limpo e 100% verídico, seguindo estas regras estritas:
    1. **Ancoragem por Placar Numérico**: Para incluir qualquer jogo ou resultado na curadoria, deves identificar o placar numérico exato no texto (ex: 'Barcelona 1 x 2 PSG'). Se o texto for apenas uma crônica de opinião, especulação ou não contiver o placar numérico claro, DESCARTA O JOGO por completo.
    2. **Zero Inversão de Vencedores**: Com base no placar numérico verificado, declara com clareza absoluta quem venceu, quem perdeu ou se houve empate. NUNCA inverte o vencedor nem confunda merecimento com o resultado real.
    3. **Separação Categoria de Base vs. Profissional**: Descarta ou separa claramente torneios juvenis/sub-19 (ex: UEFA Youth League) da Liga dos Campeões / torneios profissionais principais.
    4. **Métricas Fatuais**: Mantém apenas dados e estatísticas reais confirmadas (gols marcados, destaques, xG, posse de bola, cartões, etc.).

    Retorna apenas um resumo factual com os jogos validados e os seus respetivos placares numéricos e fatos confirmados.
    """

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=curation_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.0,  # Zero criatividade para priorizar rigor factual
                ),
            )
            return response.text
        except Exception as e:
            print(f"Aviso no Agente Curador (tentativa {attempt + 1}): {e}")
            time.sleep(5)
    
    return raw_news  # Fallback caso a tentativa falhe

def generate_newsletter():
    """
    AGENTE 2 (Redator / Opta Analyst):
    Transforma os fatos numéricos e checados do Agente 1 em uma narrativa elegante e analítica estilo Opta.
    """
    print("A coletar notícias brutas das últimas 24 horas...")
    raw_news = fetch_latest_football_news()

    print("Agente 1 (Curador): A ancorar placares numéricos, filtrar ruído e validar vencedores...")
    clean_facts = curate_and_verify_facts(raw_news)

    print("Agente 2 (Opta Analyst): A redigir a newsletter tática...")
    writer_prompt = f"""
    És um jornalista desportivo especialista em futebol e analista de dados de desempenho (estilo Opta Analyst).
    Cria uma newsletter diária completa, elegante e altamente relevante com base estritamente nos FACTOS E PLACARES VALIDADOS abaixo:

    FACTOS E PLACARES CHECADOS (ÚLTIMAS 24 HORAS):
    ---
    {clean_facts}
    ---

    Regra de Ouro: Sê rigoroso. Se não houver informações ou estatísticas relevantes e verificáveis sobre um determinado tópico ou secção para o dia de hoje, OMITE essa secção por completo. Nunca inventes dados, números ou estatísticas.

    A newsletter deve conter as seguintes secções formatadas em HTML (apenas as que tiverem conteúdo real e de qualidade):
    1. ⚽ **Futebol Brasileiro**: Principais destaques, resultados de jogos recentes, polémicas e bastidores do Brasileirão / Copa do Brasil.
    2. 🌍 **Futebol Internacional**: Principais novidades da Europa (Champions League, LaLiga, Premier League) e o desempenho dos jogadores brasileiros no exterior.
    3. ⚡ **Raio-X Estatístico e Métricas Avançadas**: Se houver dados de tracking ou estatísticas de destaque disponíveis para os jogos recentes, inclui métricas impactantes (ex: velocidade de sprint, distância percorrida, xG, impulsão aérea, recordes quebrados, etc.). Se não houver dados notáveis hoje, salta esta secção.
    4. 📊 **O Jogo do Dia / Próximos Confrontos**: Destaque para as partidas mais importantes agendadas para hoje.

    A resposta deve ser formatada EXCLUSIVAMENTE em código HTML limpo (sem blocos de código markdown como ```html), pronto para ser inserido diretamente no corpo de um e-mail.
    Usa um design limpo, margens agradáveis, tipografia legível e emojis para estruturar visualmente o conteúdo.
    """

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=writer_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                ),
            )
            content = response.text
            if content.startswith("```html"):
                content = content.replace("```html", "", 1)
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()
        except Exception as e:
            print(f"Aviso no Agente Redator (tentativa {attempt + 1}): {e}")
            time.sleep(10)

def send_email(html_content):
    print("A enviar e-mail via SMTP...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚽ Newsletter Diária & Raio-X Estatístico'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("E-mail enviado com sucesso!")

if __name__ == "__main__":
    print("A iniciar pipeline de inteligência desportiva...")
    newsletter_html = generate_newsletter()
    send_email(newsletter_html)
    print("Processo concluído com sucesso!")
