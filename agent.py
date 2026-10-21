import os
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests
import xml.etree.ElementTree as ET
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

client = genai.Client(api_key=GEMINI_API_KEY)

def fetch_sports_rss():
    """
    Busca notícias e resultados recentes de fontes públicas oficiais via RSS.
    Não sofre de bloqueios de API, rate limits ou IPs banidos no GitHub Actions.
    """
    rss_urls = [
        "https://www.espn.com/espn/rss/soccer/news",
        "https://ge.globo.com/rss/futebol/"
    ]
    
    extracted_texts = []
    
    for url in rss_urls:
        try:
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                # Procura por itens de notícias/resultados no XML do RSS
                for item in root.findall(".//item")[:10]:
                    title = item.find("title")
                    description = item.find("description")
                    
                    t_text = title.text if title is not None and title.text else ""
                    d_text = description.text if description is not None and description.text else ""
                    
                    if t_text:
                        extracted_texts.append(f"• {t_text} - {d_text}")
        except Exception as e:
            print(f"Aviso ao ler RSS {url}: {e}")
            
    if extracted_texts:
        return "NOTÍCIAS E RESULTADOS REAIS RECENTES:\n" + "\n".join(extracted_texts[:20])
    
    return None

def generate_newsletter(content_data):
    prompt = f"""
    És um analista de dados desportivos de elite. 
    Cria uma newsletter diária elegante e objetiva baseada EXCLUSIVAMENTE nas notícias e resultados reais fornecidos abaixo:

    {content_data}

    REGRAS DE OURO:
    1. Usa apenas os factos, equipas e eventos presentes no texto acima. Proibido inventar dados.
    2. Estrutura a newsletter em HTML limpo pronto para e-mail com as secções:
       - ⚽ Destaques da Jornada
       - 🌍 Panorama Global (Europa, Brasil, MLS e Arábia Saudita, se aplicável aos dados)
       - 📊 Leitura Tática
    
    Formata EXCLUSIVAMENTE em código HTML limpo (sem blocos ```html).
    """

    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )
    content = response.text
    if content.startswith("```html"):
        content = content.replace("```html", "", 1)
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()

def send_email(html_content):
    print("A enviar e-mail...")
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚽ Newsletter Diária & Análise Tática'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO
    msg.attach(MIMEText(html_content, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("E-mail enviado com sucesso!")

if __name__ == "__main__":
    print("A recolher dados via RSS...")
    sports_data = fetch_sports_rss()
    
    if not sports_data:
        print("Erro: Não foi possível obter dados dos feeds RSS.")
        exit(1)
        
    newsletter_html = generate_newsletter(sports_data)
    send_email(newsletter_html)
