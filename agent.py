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
    És um jornalista desportivo especialista em futebol e analista de dados de desempenho (estilo Opta Analyst).
    Cria uma newsletter diária completa, elegante e altamente relevante com base estritamente nas notícias e dados reais das últimas 24 horas encontrados via pesquisa na web.

    Regra de Ouro: Sê rigoroso. Se não houver informações ou estatísticas relevantes e verificáveis sobre um determinado tópico ou secção para o dia de hoje, OMITE essa secção por completo. Nunca inventes dados, números ou estatísticas.

    A newsletter deve conter as seguintes secções formatadas em HTML (apenas as que tiverem conteúdo real e de qualidade):
    1. ⚽ **Futebol Brasileiro**: Principais destaques, resultados de jogos recentes, polémicas e bastidores do Brasileirão / Copa do Brasil.
    2. 🌍 **Futebol Internacional**: Principais novidades da Europa (Champions League, LaLiga, Premier League) e o desempenho dos jogadores brasileiros no exterior.
    3. ⚡ **Raio-X Estatístico e Métricas Avançadas**: Se houver dados de tracking ou estatísticas de destaque disponíveis na web para os jogos recentes, inclui métricas impactantes (ex: velocidade de sprint, distância percorrida, xG, impulsão aérea, recordes quebrados, etc.). Se não houver dados notáveis hoje, salta esta secção.
    4. 📊 **O Jogo do Dia / Próximos Confrontos**: Destaque para as partidas mais importantes agendadas para hoje.

    A resposta deve ser formatada EXCLUSIVAMENTE em código HTML limpo (sem blocos de código markdown como ```html), pronto para ser inserido diretamente no corpo de um e-mail.
    Usa um design limpo, margens agradáveis, tipografia legível e emojis para estruturar visualmente o conteúdo.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],  # Ativa a pesquisa em tempo real
            temperature=0.2,                # Mantém a resposta bem fática e sem invenções
        ),
    )
    
    return response.text

def send_email(html_content):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚽ Newsletter Diária & Raio-X Estatístico'
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
    print("A pesquisar notícias e estatísticas...")
    newsletter_html = generate_newsletter()
    
    print("A enviar e-mail...")
    send_email(newsletter_html)
    print("Processo concluído!")
