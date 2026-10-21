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
    Busca com garantia de retorno os últimos jogos terminados das principais ligas.
    Lida com transições de temporada (2026/2025) automaticamente.
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    
    # IDs das ligas:
    # 71: Brasileirão | 140: LaLiga | 39: Premier League | 2: Champions League
    # 307: Saudi Pro League (CR7) | 253: MLS (Messi)
    leagues = [
        {"id": 71, "name": "Brasileirão"},
        {"id": 140, "name": "LaLiga"},
        {"id": 39, "name": "Premier League"},
        {"id": 2, "name": "Champions League"},
        {"id": 307, "name": "Saudi Pro League"},
        {"id": 253, "name": "MLS"}
    ]
    
    current_year = datetime.now().year
    match_list = []
    
    for league in leagues:
        league_id = league["id"]
        found = False
        
        # Tenta a temporada atual e a anterior para garantir que encontra jogos mesmo em transição de ano
        for season in [current_year, current_year - 1]:
            params = {
                "league": league_id,
                "season": season,
                "status": "FT",  # Jogos concluídos
                "last": 3        # Últimos 3 confrontos
            }
            try:
                print(f"A consultar {league['name']} (ID {league_id}) para a temporada {season}...")
                response = requests.get(url, headers=headers, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    fixtures = data.get("response", [])
                    
                    if fixtures:
                        for fix in fixtures:
                            l_name = fix.get("league", {}).get("name", league["name"])
                            country = fix.get("league", {}).get("country", "")
                            home = fix.get("teams", {}).get("home", {}).get("name", "Casa")
                            away = fix.get("teams", {}).get("away", {}).get("name", "Fora")
                            
                            goals = fix.get("goals", {})
                            g_home = goals.get("home", 0)
                            g_away = goals.get("away", 0)
                            
                            f_date = fix.get("fixture", {}).get("date", "")[:10]
                            
                            match_list.append(f"• [{country} - {l_name} ({f_date})] {home} {g_home} x {g_away} {away}")
                        found = True
                        break # Se encontrou jogos nesta temporada, passa à próxima liga
            except Exception as e:
                print(f"Erro ao consultar a liga {league_id} na temporada {season}: {e}")
                
    if match_list:
        return "RESULTADOS REAIS E RECENTES DAS PRINCIPAIS COMPETIÇÕES:\n" + "\n".join(match_list)
        
    return "Nenhum resultado recente encontrado."

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
    1. Usa estritamente os placares e dados acima. NUNCA dizes que não há jogos se a lista contiver partidas.
    2. Dá destaque especial aos jogos de equipas brasileiras, principais ligas europeias e ao desempenho de estrelas globais (como Lionel Messi e Cristiano Ronaldo) com base nos jogos listados.
    3. Analisa os confrontos detalhadamente com foco tático e métrico.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise detalhada dos jogos mais recentes fornecidos na lista.
    2. 🌍 **Panorama Global (Brasil, Europa, MLS e Arábia Saudita)**: Contextualização dos resultados nas respetivas competições.
    3. 📊 **Leitura Tática**: Perspetiva analítica do desempenho das equipas e jogadores.

    Formata EXCLUSIVAMENTE em código HTML limpo (sem blocos ```html), pronto para e-mail.
    Usa um design moderno, legível e responsivo.
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
