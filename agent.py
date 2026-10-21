import os
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from google import genai
from google.genai import types

# Credenciais de ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")  # Nova chave da football-data.org
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_official_matches():
    """
    Busca partidas recentes utilizando a API da football-data.org
    Competições suportadas no plano gratuito: Premier League (PL), LaLiga (PD), Champions League (CL), etc.
    """
    url = "https://api.football-data.org/v4/matches"
    headers = {
        "X-Auth-Token": FOOTBALL_API_KEY
    }
    
    # Período de busca: dos últimos 4 dias até hoje
    date_from = (datetime.utcnow() - timedelta(days=4)).strftime('%Y-%m-%d')
    date_to = datetime.utcnow().strftime('%Y-%m-%d')
    
    params = {
        "dateFrom": date_from,
        "dateTo": date_to
    }
    
    match_list = []
    
    try:
        print(f"A consultar football-data.org de {date_from} até {date_to}...")
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
            
            for m in matches:
                status = m.get("status")
                if status == "FINISHED":
                    competition = m.get("competition", {}).get("name", "")
                    home_team = m.get("homeTeam", {}).get("name", "")
                    away_team = m.get("awayTeam", {}).get("name", "")
                    score = m.get("score", {}).get("fullTime", {})
                    g_home = score.get("home", 0)
                    g_away = score.get("away", 0)
                    m_date = m.get("utcDate", "")[:10]
                    
                    match_list.append(f"• [{competition} ({m_date})] {home_team} {g_home} x {g_away} {away_team}")
        else:
            print(f"Erro na resposta da API: Código {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Erro ao ligar à football-data.org: {e}")
        
    if match_list:
        return "RESULTADOS REAIS RECENTES:\n" + "\n".join(match_list)
        
    return "Nenhum resultado recente encontrado nas competições monitorizadas neste intervalo."

def generate_newsletter():
    official_results = fetch_official_matches()

    print("A estruturar a newsletter com o Gemini...")
    prompt = f"""
    És um analista de dados desportivos de elite (estilo Opta Analyst).
    Cria uma newsletter diária elegante focada ESTRITAMENTE nos resultados oficiais fornecidos abaixo:

    DADOS REAIS DA API:
    ---
    {official_results}
    ---

    Regras Absolutas:
    1. Usa estritamente os placares e dados acima. Nunca inventes placares ou vencedores.
    2. Analisa os confrontos detalhadamente com base métrica (tendências de resultado, impacto na tabela e desempenho coletivo).
    3. Mantém um tom profissional, analítico e limpo.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise rigorosa dos confrontos recentes listados.
    2. 🌍 **Panorama Global nas Ligas**: Contextualização dos resultados nas respetivas tabelas.
    3. 📊 **Leitura Tática**: Perspetiva analítica de desempenho.

    Formata EXCLUSIVAMENTE em código HTML limpo (sem blocos ```html), pronto para e-mail.
    """

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.8-flash',
                contents=prompt,
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
            print(f"Tentativa {attempt + 1} falhou: {e}")
            time.sleep(5)

def send_email(html_content):
    print("A enviar e-mail...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚽ Newsletter Diária & Análise Tática'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("E-mail enviado com sucesso!")

if __name__ == "__main__":
    newsletter_html = generate_newsletter()
    send_email(newsletter_html)
