import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
from google import genai
from google.genai import types

# Credenciais de ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_official_matches():
    """
    Busca os resultados mais recentes das principais competições mundiais,
    incluindo Brasil, Europa, Arábia Saudita (CR7) e EUA (Messi).
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    
    # IDs das ligas monitorizadas:
    # 71: Brasileirão | 140: LaLiga | 39: Premier League | 2: Champions League
    # 307: Saudi Pro League (Cristiano Ronaldo) | 253: MLS (Lionel Messi)
    league_ids = [71, 140, 39, 2, 307, 253]
    current_season = 2026
    
    match_list = []
    
    for league_id in league_ids:
        params = {
            "league": league_id,
            "season": current_season,
            "status": "FT",  # Apenas jogos terminados (Full Time)
            "last": 3        # Os últimos 3 jogos terminados de cada liga/competição
        }
        try:
            print(f"A consultar dados para a liga ID {league_id}...")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                
                for fix in fixtures:
                    league_name = fix.get("league", {}).get("name", "")
                    country = fix.get("league", {}).get("country", "")
                    home = fix.get("teams", {}).get("home", {}).get("name", "")
                    away = fix.get("teams", {}).get("away", {}).get("name", "")
                    
                    goals = fix.get("goals", {})
                    g_home = goals.get("home", 0)
                    g_away = goals.get("goals", {}).get("away", 0)
                    
                    fixture_date = fix.get("fixture", {}).get("date", "")[:10]
                    
                    match_list.append(f"• [{country} - {league_name} ({fixture_date})] {home} {g_home} x {g_away} {away}")
        except Exception as e:
            print(f"Erro ao consultar a liga {league_id}: {e}")
            
    if match_list:
        return "Últimos resultados oficiais registados nas principais competições globais:\n" + "\n".join(match_list)
        
    return "Nenhum resultado recente encontrado nas ligas monitorizadas."

def generate_newsletter():
    official_results = fetch_official_matches()

    print("A estruturar a newsletter com o Gemini...")
    prompt = f"""
    És um analista de dados desportivos de elite (estilo Opta Analyst).
    Cria uma newsletter diária elegante focada ESTRITAMENTE nos resultados oficiais fornecidos abaixo:

    DADOS OFICIAIS DA API DE FUTEBOL:
    ---
    {official_results}
    ---

    Regras Absolutas:
    1. Usa estritamente os placares e dados acima. Nunca inventes placares ou vencedores.
    2. Dá destaque especial aos jogos de equipas brasileiras, principais ligas europeias e ao desempenho de estrelas globais (como Lionel Messi e Cristiano Ronaldo) caso constem na lista.
    3. Analisa os confrontos detalhadamente com base métrica.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise rigorosa dos confrontos recentes.
    2. 🌍 **Panorama Global (Brasil, Europa, MLS e Arábia Saudita)**: Contextualização dos resultados nas respetivas tabelas e impacto das grandes figuras.
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
