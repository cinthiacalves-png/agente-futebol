import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai
from google.genai import types

# 1. Configurar credenciais a partir das variáveis de ambiente
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_APP_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD")
EMAIL_TO = os.environ.get("EMAIL_TO")

def generate_newsletter():
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = """
    És um jornalista desportivo especialista em futebol brasileiro e internacional.
    Cria uma newsletter diária completa, elegante e bem estruturada com as principais notícias das últimas 24 horas.

    A newsletter deve conter as seguintes secções formatadas em HTML:
    1. ⚽ **Futebol Brasileiro**: Principais destaques, resultados de jogos recentes, lesões e bastidores do Brasileirão / Copa do Brasil.
    2. 🌍 **Futebol Internacional**: Principais novidades da Europa (Champions League, LaLiga, Premier League, etc.) e destaques dos jogadores brasileiros no exterior.
    3. 📊 **O Jogo do Dia / Próximos Confrontos**: Destaque para as partidas mais importantes agendadas para hoje ou para os próximos dias.

    A resposta deve ser formatada EXCLUSIVAMENTE em código HTML limpo (sem tags ```html), pronto para ser enviado no corpo de um e-mail.
    Usa um design limpo, com boas margens, títulos legíveis e emojis para destacar as secções.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],  # Ativa a pesquisa em tempo real
        ),
    )
    
    return response.text

def send_email(html_content):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚽ Newsletter Diária de Futebol'
    msg['From'] = EMAIL_USER
    msg['To'] = EMAIL_TO

    # Anexa o conteúdo HTML
    html_part = MIMEText(html_content, 'html', 'utf-8')
    msg.attach(html_part)

    # Conecta ao servidor SMTP do Gmail
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(EMAIL_USER, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())
        print("E-mail enviado com sucesso!")

if __name__ == "__main__":
    print("A pesquisar notícias e a gerar newsletter...")
    newsletter_html = generate_newsletter()
    
    print("A enviar e-mail...")
    send_email(newsletter_html)
    print("Processo concluído!")
