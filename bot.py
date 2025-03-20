import os
import discord
from discord.ext import tasks, commands
import asyncio
from google.oauth2 import service_account
from googleapiclient.discovery import build
import logging
import random

# Configuração do logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

# Obter variáveis do GitHub Secrets
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GOOGLE_PRIVATE_KEY = os.getenv("GOOGLE_PRIVATE_KEY", "").replace("\\n", "\n")
GOOGLE_CLIENT_EMAIL = os.getenv("GOOGLE_CLIENT_EMAIL")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))
MENTION_CHANNEL_ID = int(os.getenv("MENTION_CHANNEL_ID", 0))
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")

# Configuração do Service Account para API do Google Sheets
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "private_key": GOOGLE_PRIVATE_KEY,
    "client_email": GOOGLE_CLIENT_EMAIL,
    "client_id": GOOGLE_CLIENT_ID,
    "token_uri": "https://oauth2.googleapis.com/token",
}

# Inicializa cliente Discord
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Inicializa credenciais do Google Sheets
try:
    creds = service_account.Credentials.from_service_account_info(SERVICE_ACCOUNT_INFO, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
except Exception as e:
    logger.error(f"❌ Erro ao configurar API do Google Sheets: {e}")
    service = None

# Armazena respostas já processadas
processed_responses = set()

# Função para buscar respostas do Google Sheets
async def get_form_responses():
    if service is None:
        logger.error("❌ Serviço da API do Google Sheets não foi inicializado corretamente.")
        return []

    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_name = sheet_metadata["sheets"][0]["properties"]["title"]
        range_name = f"{sheet_name}"

        result = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range=range_name).execute()
        values = result.get("values", [])

        if not values:
            logger.warning("⚠️ Nenhuma resposta encontrada na planilha.")
            return []

        headers = values[0]
        if "Carimbo de data/hora" not in headers:
            logger.error("❌ Nenhuma coluna 'Carimbo de data/hora' encontrada.")
            return []

        id_index = headers.index("Carimbo de data/hora")  # Posição do ID único
        responses = []

        for row in values[1:]:
            if len(row) > id_index:
                response_id = row[id_index]
                if response_id in processed_responses:
                    continue  # Pula respostas já enviadas
                response_data = dict(zip(headers, row))
                responses.append(response_data)
        
        return responses

    except Exception as e:
        logger.error(f"❌ Erro ao buscar respostas da planilha: {e}")
        return []

# Função para limpar o formulário após capturar os dados
async def clear_form_responses():
    if service is None:
        logger.error("❌ API do Google Sheets não está configurada corretamente.")
        return

    try:
        sheet_metadata = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
        sheet_name = sheet_metadata["sheets"][0]["properties"]["title"]

        # Mantém apenas a linha do cabeçalho
        clear_range = f"{sheet_name}!A2:Z"  
        request_body = {"range": clear_range}
        service.spreadsheets().values().clear(spreadsheetId=SPREADSHEET_ID, range=clear_range, body=request_body).execute()

        logger.info("✅ Respostas do formulário foram apagadas com sucesso!")

    except Exception as e:
        logger.error(f"❌ Erro ao limpar as respostas da planilha: {e}")

# Loop para verificar respostas
@tasks.loop(seconds=5)
async def check_form_responses():
    try:
        main_channel = bot.get_channel(CHANNEL_ID)
        mention_channel = bot.get_channel(MENTION_CHANNEL_ID)

        if main_channel is None or mention_channel is None:
            logger.error("❌ Um dos canais não foi encontrado.")
            return

        responses = await get_form_responses()

        if not responses:
            logger.info("🔍 Nenhuma nova resposta encontrada.")
            return  

        for response in responses:
            response_id = response["Carimbo de data/hora"]  

            if response_id in processed_responses:
                continue  

            message = "\n".join([f"**{key}**: {value}" for key, value in response.items()])
            embed = discord.Embed(title="📩 Nova Resposta Recebida!", description=message, color=discord.Color.blue())
            await main_channel.send(embed=embed)

            discord_id = response.get("ID do Discord", "").strip()
            nome_no_ic = response.get("Nome no IC", "").strip()
            user_to_message = 963524916987183134  # ID fixo para mencionar

            if discord_id.isdigit():
                mention_message = (
                    f"# <:PARASAR:{1132713845559922728}>  Paracomandos\n\n"
                    f"|| {nome_no_ic} // <@{discord_id}> || \n\n"
                    f"*Você está pré-aprovado para a Paracomandos!* \n"
                    f"*Envie uma mensagem para <@{user_to_message}> informando sua disponibilidade de data e horário para* "
                    f"*agendarmos na melhor opção para você*.\n\n"
                )

                try:
                    await mention_channel.send(mention_message)
                    logger.info(f"✅ Mensagem enviada para <@{discord_id}>!")
                except Exception as e:
                    logger.error(f"❌ Erro ao enviar mensagem: {e}")

            processed_responses.add(response_id)  

        # Após processar todas as respostas, limpar o formulário
        await clear_form_responses()

    except Exception as e:
        logger.error(f"❌ Erro no loop de verificação de respostas: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot conectado como {bot.user}")
    if not check_form_responses.is_running():
        check_form_responses.start()

if TOKEN:
    bot.run(TOKEN)
else:
    logger.error("❌ DISCORD_BOT_TOKEN não foi encontrado!")
