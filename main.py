import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
import logging

# Carregar variáveis de ambiente
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Intents necessários
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

# Configuração do bot
TOKEN = os.getenv('DISCORD_TOKEN')
PREFIX = os.getenv('PREFIX', '!')

if not TOKEN:
    raise ValueError("DISCORD_TOKEN não encontrado nas variáveis de ambiente!")

# Criar instância do bot
bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=commands.DefaultHelpCommand(),
    case_insensitive=True
)


@bot.event
async def on_ready():
    """Evento quando o bot está pronto"""
    logger.info(f'{bot.user} está online!')
    logger.info(f'Bot ID: {bot.user.id}')
    logger.info(f'Conectado em {len(bot.guilds)} servidor(es)')
    
    # Sincronizar comandos slash
    try:
        synced = await bot.tree.sync()
        logger.info(f'Sincronizados {len(synced)} comando(s) slash')
    except Exception as e:
        logger.error(f'Erro ao sincronizar comandos: {e}')
    
    # Definir status do bot
    await bot.change_presence(
        activity=discord.Game(name=f"{PREFIX}help | Papelzinho"),
        status=discord.Status.online
    )


@bot.event
async def on_command_error(ctx, error):
    """Handler global de erros de comandos"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignorar comandos não encontrados
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Faltam argumentos! Use `{PREFIX}help {ctx.command.name}` para ver a sintaxe.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Você não tem permissão para usar este comando!")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ Eu não tenho permissão para executar este comando!")
    else:
        logger.error(f'Erro no comando {ctx.command}: {error}')
        await ctx.send("❌ Ocorreu um erro ao executar o comando.")


async def load_extensions():
    """Carregar todas as extensões (cogs)"""
    extensions = [
        'cogs.custom_commands',
        'cogs.utils',
        'cogs.caixas',
        'cogs.site',
    ]
    
    for extension in extensions:
        try:
            await bot.load_extension(extension)
            logger.info(f'Extensão {extension} carregada com sucesso')
        except Exception as e:
            logger.error(f'Erro ao carregar extensão {extension}: {e}')


async def main():
    """Função principal"""
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Bot encerrado pelo usuário')
    except Exception as e:
        logger.error(f'Erro fatal: {e}')

