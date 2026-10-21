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
    Varre os últimos dias de forma inteligente até encontrar 
    a jornada mais recente com resultados oficiais terminados.
    """
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {
        "x-apisports-key": FOOTBALL_API_KEY
    }
    
    match_list = []
    # Procura retroativamente nos últimos 4 dias para apanhar sempre o fim de semana ou jornadas recentes
    for i in range(1, 5):
        target_date = (datetime.utcnow() - timedelta(days=i)).strftime('%Y-%m-%d')
        params = {
            "date": target_date,
            "status": "FT"  # Jogos terminados (Full Time)
        }
        
        try:
            print(f"A verificar resultados oficiais para a data: {target_date}...")
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                fixtures = data.get("response", [])
                
                if fixtures:
                    for fix in fixtures:
                        league = fix.get("league", {}).get("name", "")
                        home = fix.get("teams", {}).get("home", {}).get("name", "")
                        away = fix.get("teams", {}).get("away", {}).get("name", "")
                        goals_home = fix.get("goals", {}).get("home", 0)
                        goals_away = fix.get("goals", {}).get("away", 0)
                        
                        match_list.append(f"• [{league}] {home} {goals_home} x {goals_away} {away}")
                    
                    if match_list:
                        print(f"Encontrados {len(fixtures)} jogos oficiais referentes a {target_date}.")
                        break
        except Exception as e:
            print(f"Aviso ao consultar a API de futebol para {target_date}: {e}")
            
    if match_list:
        return "\n".join(match_list)
        
    return "Nenhum resultado competitivo recente registado nas últimas jornadas."

def generate_newsletter():
    """
    Usa os resultados oficiais da API para alimentar o Agente Redator (Opta Analyst),
    garantindo zero alucinações de placares.
    """
    official_results = fetch_official_matches()

    print("Agente Redator (Opta Analyst): A estruturar a análise tática...")
    prompt = f"""
    És um jornalista desportivo especialista em futebol e analista de dados de desempenho (estilo Opta Analyst).
    Cria uma newsletter diária elegante e altamente relevante com base ESTRITAMENTE nos resultados oficiais abaixo:

    RESULTADOS OFICIAIS E PLACARES INQUESTIONÁVEIS:
    ---
    {official_results}
    ---

    Regra de Ouro Absoluta: Os placares e vencedores listados acima são a verdade matemática imutável. Nunca invertas quem ganhou ou perdeu. Nunca inventes placares ou dados que não constem na lista.

    A newsletter deve conter as seguintes secções formatadas em HTML limpo:
    1. ⚽ **Destaques da Jornada**: Análise dos principais confrontos com base estritamente nos resultados oficiais fornecidos.
    2. 🌍 **Panorama Internacional e Europeu**: Contextualização dos resultados nas respetivas competições.
    3. 📊 **Leitura Tática**: Uma reflexão profunda sobre o desempenho das equipas em destaque.

    A resposta deve ser formatada EXCLUSIVAMENTE em código HTML limpo (sem blocos de código markdown como ```html), pronto para ser inserido diretamente no corpo de um e-mail.
    Usa um design limpo, margens agradáveis, tipografia legível e emojis para estruturar visualmente o conteúdo.
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
            print(f"Aviso na geração (tentativa {attempt + 1}): {e}")
            time.sleep(10)

def send_email(html_content):
    print("A enviar e-mail via SMTP...")
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
    print("A iniciar pipeline de inteligência desportiva baseada em dados oficiais...")
    newsletter_html = generate_newsletter()
    send_email(newsletter_html)
    print("Processo concluído com sucesso!")
