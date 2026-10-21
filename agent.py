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
FOOTBALL_API_KEY = os.environ.get("FOOTBALL_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_official_matches():
    """
    Procura os jogos de ontem. Se não houver jogos emontem, 
    recua inteligentemente até aos últimos 3 dias para apanhar a jornada mais recente.
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    
    # Tenta ontem primeiro (i=1). Se vier vazio, tenta os dias anteriores (i=2, i=3).
    for i in range(1, 4):
        target_date = (datetime.utcnow() - timedelta(hours=3) - timedelta(days=i)).strftime('%Y-%m-%d')
        params = {
            "date": target_date
        }
        
        try:
            print(f"A verificar resultados oficiais para a data: {target_date}...")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                
                if fixtures:
                    match_list = []
                    for fix in fixtures:
                        league_data = fix.get("league", {})
                        league_name = league_data.get("name", "")
                        country = league_data.get("country", "")
                        
                        home = fix.get("teams", {}).get("home", {}).get("name", "")
                        away = fix.get("teams", {}).get("away", {}).get("name", "")
                        
                        goals = fix.get("goals", {})
                        g_home = goals.get("home")
                        g_away = goals.get("away")
                        
                        status_short = fix.get("fixture", {}).get("status", {}).get("short", "")
                        
                        score_str = f"{g_home} x {g_away}" if g_home is not None else "Não iniciado"
                        match_list.append(f"• [{country} - {league_name}] {home} {score_str} {away} [Estado: {status_short}]")
                    
                    if match_list:
                        print(f"Encontrados jogos oficiais para a data: {target_date}")
                        return f"Data de referência dos jogos: {target_date}\n" + "\n".join(match_list)
        except Exception as e:
            print(f"Erro ao consultar a API para a data {target_date}: {e}")
            
    return "Nenhum jogo competitivo recente registado nas últimas jornadas."

def generate_newsletter():
    official_results = fetch_official_matches()

    print("A estruturar a newsletter com o Gemini...")
    prompt = f"""
    És um analista de dados desportivos de elite (estilo Opta Analyst).
    Cria uma newsletter diária elegante focada ESTRITAMENTE nos resultados recentes fornecidos abaixo:

    DADOS OFICIAIS DA API DE FUTEBOL:
    ---
    {official_results}
    ---

    Regras Absolutas:
    1. Usa estritamente os placares e dados acima. Nunca inventes placares ou vencedores.
    2. Dá destaque especial aos jogos de equipas brasileiras ou principais ligas europeias caso constem na lista.
    3. Se houver jogos do Brasil ou principais campeonatos, analisa-os em detalhe.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise rigorosa dos confrontos recentes.
    2. 🌍 **Panorama Global (Brasil e Europa)**: Contextualização dos resultados nas respetivas tabelas.
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
