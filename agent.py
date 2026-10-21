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
    Busca partidas finalizadas de forma direta e sem estourar o limite da API.
    Procura nos últimos dias até encontrar jogos reais registados.
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    
    match_list = []
    
    # Procura retroativamente até 5 dias atrás para capturar partidas reais (Brasil, Europa, MLS, Arábia)
    for i in range(1, 6):
        target_date = (datetime.utcnow() - timedelta(hours=3) - timedelta(days=i)).strftime('%Y-%m-%d')
        params = {
            "date": target_date,
            "status": "FT"
        }
        
        try:
            print(f"A consultar API-Football para a data: {target_date}...")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                
                if fixtures:
                    for fix in fixtures:
                        league_info = fix.get("league", {})
                        l_name = league_info.get("name", "")
                        country = league_info.get("country", "")
                        
                        home = fix.get("teams", {}).get("home", {}).get("name", "")
                        away = fix.get("teams", {}).get("away", {}).get("name", "")
                        
                        goals = fix.get("goals", {})
                        g_home = goals.get("home", 0)
                        g_away = goals.get("away", 0)
                        
                        # Concatena a partida formatada
                        match_list.append(f"• [{country} - {l_name}] {home} {g_home} x {g_away} {away} ({target_date})")
                    
                    if len(match_list) >= 5:
                        print(f"Sucesso: {len(match_list)} partidas encontradas para {target_date}.")
                        break
        except Exception as e:
            print(f"Erro ao consultar a data {target_date}: {e}")
            
    if match_list:
        # Retorna até 35 partidas para alimentar o Gemini com dados fartos
        return "\n".join(match_list[:35])
        
    return "Nenhum resultado recente retornado pela API."

def generate_newsletter():
    official_results = fetch_official_matches()

    print("A estruturar a newsletter com o Gemini...")
    prompt = f"""
    És um analista de dados desportivos de elite (estilo Opta Analyst).
    Cria uma newsletter diária elegante focada nos resultados reais fornecidos abaixo:

    DADOS OFICIAIS DA API DE FUTEBOL:
    ---
    {official_results}
    ---

    Instruções Principais:
    1. Se a lista acima contiver jogos, analisa os placares e destaques com rigor estatístico e tático.
    2. Dá destaque às equipas brasileiras, aos grandes clubes europeus e a estrelas como Lionel Messi ou Cristiano Ronaldo caso os seus clubes/ligas apareçam na lista.
    3. Se por algum motivo a lista indicar ausência de jogos, elabora uma breve síntese sobre o momento das competições mundiais.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise dos principais confrontos disponíveis.
    2. 🌍 **Panorama Global (Brasil, Europa, MLS e Arábia Saudita)**: Contextualização dos resultados e momento dos clubes.
    3. 📊 **Leitura Tática**: Análise de desempenho das equipas.

    Formata EXCLUSIVAMENTE em código HTML limpo (sem blocos de código ```html), pronto para e-mail.
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
