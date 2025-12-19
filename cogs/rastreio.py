import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime
import aiohttp
from bs4 import BeautifulSoup

# Tentar importar bibliotecas de rastreamento (prioridade: pyrastreio primeiro por ser mais confiável)
import logging
logger_rastreio = logging.getLogger(__name__)

RASTREIO_AVAILABLE = False
USE_PYRASTREIO = False
USE_ASYNC = False

try:
    from pyrastreio import correios
    RASTREIO_AVAILABLE = True
    USE_PYRASTREIO = True
    logger_rastreio.info("Biblioteca pyrastreio importada com sucesso")
except ImportError as e:
    USE_PYRASTREIO = False
    logger_rastreio.warning(f"pyrastreio não disponível: {e}")
    try:
        from rastreio_correios_async import Rastreio
        RASTREIO_AVAILABLE = True
        USE_ASYNC = True
        logger_rastreio.info("Biblioteca rastreio_correios_async importada com sucesso")
    except ImportError as e2:
        logger_rastreio.warning(f"rastreio_correios_async não disponível: {e2}")
        try:
            from rastreio_correios import RastreioCorreios
            RASTREIO_AVAILABLE = True
            USE_ASYNC = False
            logger_rastreio.info("Biblioteca rastreio_correios importada com sucesso")
        except ImportError as e3:
            RASTREIO_AVAILABLE = False
            USE_ASYNC = False
            logger_rastreio.error(f"Nenhuma biblioteca de rastreamento disponível. Erros: pyrastreio={e}, async={e2}, sync={e3}")

class Rastreio(commands.Cog):
    """Sistema de rastreamento de encomendas dos Correios"""
    
    def __init__(self, bot):
        self.bot = bot
        self.rastreio_client = None
        if RASTREIO_AVAILABLE:
            try:
                if USE_PYRASTREIO:
                    # pyrastreio não precisa de instância
                    self.rastreio_client = True
                    logger_rastreio.info("pyrastreio configurado e pronto para uso")
                elif USE_ASYNC:
                    # Importar Rastreio da biblioteca (não confundir com a classe do cog)
                    from rastreio_correios_async import Rastreio as RastreioAsync
                    self.rastreio_client = RastreioAsync()
                    logger_rastreio.info("rastreio_correios_async configurado")
                else:
                    from rastreio_correios import RastreioCorreios
                    self.rastreio_client = RastreioCorreios()
                    logger_rastreio.info("rastreio_correios configurado")
            except Exception as e:
                self.rastreio_client = None
                logger_rastreio.error(f"Erro ao configurar biblioteca de rastreamento: {e}")
        else:
            logger_rastreio.warning("Nenhuma biblioteca de rastreamento disponível, usando web scraping como fallback")
    
    def validar_codigo(self, codigo: str) -> bool:
        """Validar formato do código de rastreamento"""
        # Formato: 2 letras + 9 dígitos + 2 letras (ex: YO065460434BR)
        # Ou formato antigo: 13 caracteres alfanuméricos
        codigo = codigo.upper().strip()
        pattern = r'^[A-Z]{2}\d{9}[A-Z]{2}$|^[A-Z0-9]{13}$'
        return bool(re.match(pattern, codigo))
    
    async def buscar_rastreio_web(self, codigo: str):
        """Fallback: buscar rastreamento via API dos Correios"""
        # API pública dos Correios para rastreamento
        url = "https://www.correios.com.br/enviar/precisa-de-ajuda/rastreamento-de-objetos"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Content-Type': 'application/json',
            'Origin': 'https://www.correios.com.br',
            'Referer': 'https://www.correios.com.br/enviar/precisa-de-ajuda/rastreamento-de-objetos'
        }
        
        # Tentar método 1: API JSON
        try:
            async with aiohttp.ClientSession() as session:
                # Primeiro, tentar buscar via endpoint de API
                api_url = f"https://www.correios.com.br/enviar/precisa-de-ajuda/rastreamento-de-objetos/objetos/{codigo}"
                
                async with session.get(api_url, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            if data and 'eventos' in data:
                                eventos = []
                                for evento in data['eventos']:
                                    eventos.append({
                                        'data': evento.get('data', evento.get('dtHrCriado', 'N/A')),
                                        'status': evento.get('descricao', evento.get('tipo', 'N/A')),
                                        'descricao': evento.get('descricao', evento.get('tipo', 'N/A')),
                                        'local': evento.get('unidade', {}).get('endereco', {}).get('cidade', ''),
                                        'uf': evento.get('unidade', {}).get('endereco', {}).get('uf', '')
                                    })
                                if eventos:
                                    return eventos, None
                        except:
                            pass  # Se não for JSON, tentar HTML
                    
                    # Método 2: Web scraping da página HTML
                    html_url = f"https://www.correios.com.br/enviar/precisa-de-ajuda/rastreamento-de-objetos?objeto={codigo}"
                    async with session.get(html_url, headers=headers, timeout=15) as html_response:
                        if html_response.status == 200:
                            html = await html_response.text()
                            soup = BeautifulSoup(html, 'html.parser')
                            
                            eventos = []
                            
                            # Tentar encontrar eventos em diferentes estruturas
                            # Estrutura 1: divs com classe de evento
                            eventos_divs = soup.find_all('div', class_=re.compile(r'evento|rastreamento|historico', re.I))
                            
                            # Estrutura 2: listas
                            if not eventos_divs:
                                eventos_divs = soup.find_all('li', class_=re.compile(r'evento|rastreamento|historico', re.I))
                            
                            # Estrutura 3: tabelas
                            if not eventos_divs:
                                eventos_divs = soup.find_all('tr', class_=re.compile(r'evento|rastreamento', re.I))
                            
                            # Estrutura 4: Buscar por texto que contenha datas
                            if not eventos_divs:
                                # Buscar por padrões de data (dd/mm/yyyy ou dd-mm-yyyy)
                                texto_completo = soup.get_text()
                                linhas = texto_completo.split('\n')
                                for linha in linhas:
                                    linha = linha.strip()
                                    # Procurar por padrão de data seguido de descrição
                                    match = re.search(r'(\d{2}[/-]\d{2}[/-]\d{4}.*?)(?:\n|$)', linha)
                                    if match and len(linha) > 20:
                                        partes = linha.split(' - ', 1) if ' - ' in linha else linha.split(' | ', 1)
                                        if len(partes) >= 1:
                                            data = partes[0].strip()[:20]
                                            descricao = partes[1].strip() if len(partes) > 1 else linha[20:].strip()
                                            if descricao and len(descricao) > 5:
                                                eventos.append({
                                                    'data': data,
                                                    'status': descricao[:200],
                                                    'descricao': descricao[:200],
                                                    'local': '',
                                                    'uf': ''
                                                })
                            
                            # Processar eventos encontrados
                            for div in eventos_divs[:10]:
                                texto = div.get_text(strip=True)
                                if texto and len(texto) > 10:
                                    # Tentar extrair data e descrição
                                    partes = texto.split(' - ', 1) if ' - ' in texto else texto.split(' | ', 1)
                                    if len(partes) >= 1:
                                        data = partes[0].strip()[:20]
                                        descricao = partes[1].strip() if len(partes) > 1 else texto[20:].strip()
                                        if descricao and len(descricao) > 5:
                                            eventos.append({
                                                'data': data,
                                                'status': descricao[:200],
                                                'descricao': descricao[:200],
                                                'local': '',
                                                'uf': ''
                                            })
                            
                            if eventos:
                                # Remover duplicatas
                                eventos_unicos = []
                                vistos = set()
                                for evento in eventos:
                                    chave = f"{evento['data']}-{evento['descricao'][:50]}"
                                    if chave not in vistos:
                                        vistos.add(chave)
                                        eventos_unicos.append(evento)
                                
                                return eventos_unicos[:10], None
                            
                            return None, "❌ Nenhuma informação encontrada para este código."
                        else:
                            return None, f"❌ Erro ao acessar site dos Correios (Status: {html_response.status})"
                            
        except asyncio.TimeoutError:
            return None, "❌ Timeout ao buscar informações dos Correios. Tente novamente."
        except aiohttp.ClientError as e:
            logger_rastreio.error(f"Erro de conexão: {e}")
            return None, "❌ Erro de conexão com os Correios. Verifique sua internet."
        except Exception as e:
            logger_rastreio.error(f"Erro no web scraping: {e}", exc_info=True)
            return None, f"❌ Erro ao buscar rastreamento: {str(e)[:100]}"
    
    async def buscar_rastreio(self, codigo: str):
        """Buscar informações de rastreamento"""
        codigo = codigo.upper().strip()
        
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
        
        try:
            # Prioridade 1: usar pyrastreio (mais confiável e amplamente disponível)
            if USE_PYRASTREIO:
                resultado = await asyncio.to_thread(correios.track, codigo)
                if resultado:
                    # pyrastreio retorna uma lista de eventos
                    if isinstance(resultado, list) and len(resultado) > 0:
                        return resultado, None
                    elif isinstance(resultado, dict):
                        return [resultado], None
                # Se pyrastreio não retornou nada, tentar web scraping
                logger_rastreio.warning("pyrastreio não retornou resultados, tentando web scraping")
                return await self.buscar_rastreio_web(codigo)
            
            # Prioridade 2: usar rastreio-correios-async (assíncrono)
            if hasattr(self, 'rastreio_client') and self.rastreio_client and self.rastreio_client is not True:
                if USE_ASYNC:
                    # Versão assíncrona
                    resultado = await self.rastreio_client.rastrear(codigo)
                    if resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                    elif resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                else:
                    # Versão síncrona (usar thread)
                    resultado = await asyncio.to_thread(self.rastreio_client.rastrear, codigo)
                    if resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                    elif resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                
                # Se não retornou nada, tentar web scraping
                return await self.buscar_rastreio_web(codigo)
            
            # Fallback: usar web scraping direto (sempre disponível)
            logger_rastreio.info("Usando web scraping como fallback")
            return await self.buscar_rastreio_web(codigo)
            
        except Exception as e:
            logger_rastreio.error(f"Erro ao buscar rastreamento: {e}")
            # Tentar web scraping como último recurso
            return await self.buscar_rastreio_web(codigo)
    
    async def send_private_response(self, ctx, content=None, embed=None):
        """Enviar resposta privada (ephemeral para slash, DM para prefixo)"""
        if ctx.interaction:
            # Slash command - usar ephemeral
            try:
                if embed:
                    await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    await ctx.interaction.response.send_message(content=content, ephemeral=True)
            except discord.InteractionResponded:
                # Se já foi respondido, usar followup
                if embed:
                    await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(content=content, ephemeral=True)
        else:
            # Prefix command - enviar via DM
            try:
                if embed:
                    await ctx.author.send(embed=embed)
                else:
                    await ctx.author.send(content=content)
                # Confirmar no canal que a resposta foi enviada por DM
                await ctx.send("✅ Resposta enviada por mensagem privada!", delete_after=5)
            except discord.Forbidden:
                await ctx.send("❌ Não foi possível enviar mensagem privada. Verifique se você permite DMs de membros do servidor.")
    
    @commands.hybrid_command(name='rastrear', aliases=['rastreio', 'track'])
    @app_commands.describe(codigo='Código de rastreamento dos Correios (ex: YO065460434BR)')
    async def rastrear(self, ctx, codigo: str = None):
        """Rastrear encomenda dos Correios pelo código"""
        try:
            # Não bloquear o comando - sempre tentar usar web scraping como fallback
            # Tentar importar novamente se não estiver disponível (pode ter sido instalado após o bot iniciar)
            global RASTREIO_AVAILABLE, USE_PYRASTREIO
            if not RASTREIO_AVAILABLE:
                try:
                    from pyrastreio import correios
                    RASTREIO_AVAILABLE = True
                    USE_PYRASTREIO = True
                    self.rastreio_client = True
                    logger_rastreio.info("pyrastreio importado com sucesso após tentativa de uso")
                except ImportError:
                    logger_rastreio.warning("pyrastreio não disponível, usando web scraping como fallback")
                    # Continuar - o web scraping sempre funciona
            
            # Se não forneceu código, perguntar e esperar resposta
            if not codigo:
                await self.send_private_response(
                    ctx,
                    content="📦 **Rastreamento de Encomendas**\n\n"
                           "Por favor, informe o código de rastreamento.\n"
                           "Formato: `YO065460434BR`\n\n"
                           "Você tem 60 segundos para responder..."
                )
                
                # Esperar resposta do usuário (apenas para prefix commands)
                if not ctx.interaction:
                    def check(message):
                        return message.author == ctx.author and message.channel == ctx.channel
                    
                    try:
                        resposta = await self.bot.wait_for('message', check=check, timeout=60.0)
                        codigo = resposta.content.strip()
                    except asyncio.TimeoutError:
                        await ctx.send("⏰ Tempo esgotado! Use o comando novamente.", delete_after=10)
                        return
                else:
                    # Para slash commands, informar que precisa fornecer o código
                    return
            
            # Enviar mensagem de carregamento (importante fazer antes de operações longas)
            if ctx.interaction:
                try:
                    await ctx.interaction.response.defer(ephemeral=True)
                except discord.InteractionResponded:
                    pass  # Já foi respondido
            
            # Buscar informações de rastreamento
            eventos, erro = await self.buscar_rastreio(codigo)
            
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            
            if not eventos or len(eventos) == 0:
                await self.send_private_response(
                    ctx,
                    content=f"❌ Nenhuma informação encontrada para o código: **{codigo}**\n\n"
                           "Verifique se o código está correto ou tente novamente mais tarde."
                )
                return
            
            # Criar embed com os resultados
            embed = discord.Embed(
                title=f"📦 Rastreamento - {codigo}",
                description=f"**{len(eventos)}** evento(s) encontrado(s):",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )
            
            # Adicionar eventos (mais recentes primeiro)
            eventos_formatados = []
            for i, evento in enumerate(eventos[:10], 1):  # Limitar a 10 eventos
                try:
                    # Formatar evento dependendo da biblioteca usada
                    if isinstance(evento, dict):
                        # pyrastreio ou outras bibliotecas que retornam dict
                        data = evento.get('data', evento.get('dataHora', evento.get('timestamp', 'N/A')))
                        descricao = evento.get('status', evento.get('descricao', evento.get('evento', 'N/A')))
                        local = evento.get('local', evento.get('cidade', evento.get('origem', '')))
                        uf = evento.get('uf', evento.get('estado', ''))
                        local_completo = f"{local}/{uf}" if local and uf else local or uf or "N/A"
                    else:
                        # rastreio-correios retorna objeto
                        data = getattr(evento, 'data', getattr(evento, 'dataHora', 'N/A'))
                        descricao = getattr(evento, 'descricao', getattr(evento, 'status', 'N/A'))
                        local = getattr(evento, 'local', getattr(evento, 'cidade', ''))
                        uf = getattr(evento, 'uf', '')
                        local_completo = f"{local}/{uf}" if local and uf else local or uf or "N/A"
                    
                    # Formatar data
                    if isinstance(data, str):
                        data_formatada = data
                    else:
                        try:
                            data_formatada = data.strftime("%d/%m/%Y %H:%M")
                        except:
                            data_formatada = str(data)
                    
                    # Limitar tamanho dos campos para evitar erros
                    descricao = descricao[:200] if len(descricao) > 200 else descricao
                    local_completo = local_completo[:100] if len(local_completo) > 100 else local_completo
                    
                    eventos_formatados.append(f"**{i}.** {data_formatada}\n{descricao}\n📍 {local_completo}")
                except Exception as e:
                    logger_rastreio.error(f"Erro ao formatar evento {i}: {e}")
                    continue
            
            if not eventos_formatados:
                await self.send_private_response(
                    ctx,
                    content=f"❌ Erro ao processar eventos do código: **{codigo}**"
                )
                return
            
            # Dividir eventos em campos (máximo 1024 caracteres por campo)
            campo_atual = ""
            campo_num = 1
            
            for evento_texto in eventos_formatados:
                if len(campo_atual) + len(evento_texto) + 2 > 1024:
                    if campo_atual:  # Só adicionar se tiver conteúdo
                        embed.add_field(
                            name=f"📋 Eventos {campo_num}",
                            value=campo_atual[:1024],  # Garantir limite
                            inline=False
                        )
                    campo_atual = evento_texto + "\n\n"
                    campo_num += 1
                else:
                    campo_atual += evento_texto + "\n\n"
            
            if campo_atual:
                embed.add_field(
                    name=f"📋 Eventos {campo_num}" if campo_num > 1 else "📋 Histórico",
                    value=campo_atual[:1024],  # Garantir limite
                    inline=False
                )
            
            embed.set_footer(text=f"Solicitado por {ctx.author.name}")
            
            await self.send_private_response(ctx, embed=embed)
            
        except Exception as e:
            logger_rastreio.error(f"Erro no comando rastrear: {e}", exc_info=True)
            try:
                await self.send_private_response(
                    ctx,
                    content=f"❌ Ocorreu um erro ao processar o rastreamento: {str(e)[:200]}"
                )
            except:
                # Se não conseguir enviar resposta privada, tentar no canal
                if ctx.interaction:
                    try:
                        await ctx.interaction.followup.send(
                            f"❌ Erro ao processar rastreamento. Verifique os logs.",
                            ephemeral=True
                        )
                    except:
                        pass
                else:
                    await ctx.send("❌ Erro ao processar rastreamento. Verifique os logs.", delete_after=10)
    
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handler de erros para slash commands"""
        logger_rastreio.error(f"Erro no comando slash: {error}", exc_info=True)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Ocorreu um erro ao executar o comando. Tente novamente.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Ocorreu um erro ao executar o comando. Tente novamente.",
                    ephemeral=True
                )
        except Exception as e:
            logger_rastreio.error(f"Erro ao enviar mensagem de erro: {e}")


async def setup(bot):
    try:
        cog = Rastreio(bot)
        await bot.add_cog(cog)
        logger_rastreio.info("✅ Cog Rastreio carregado com sucesso")
        logger_rastreio.info(f"Comando /rastrear registrado e pronto para uso")
    except Exception as e:
        logger_rastreio.error(f"❌ Erro ao carregar cog Rastreio: {e}", exc_info=True)
        raise

