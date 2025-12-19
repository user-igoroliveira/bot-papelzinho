import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime

# Tentar importar bibliotecas de rastreamento (prioridade: pyrastreio primeiro por ser mais confiável)
import logging
logger_rastreio = logging.getLogger(__name__)

RASTREIO_AVAILABLE = False
USE_PYRASTREIO = False
USE_ASYNC = False
USE_RASTREIO_CORREIOS = False
rastreio_correios_module = None

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
            # Tentar diferentes formas de importar rastreio_correios
            global rastreio_correios_module
            import rastreio_correios
            rastreio_correios_module = rastreio_correios
            # Verificar se tem função rastrear ou classe
            if hasattr(rastreio_correios, 'rastrear'):
                RASTREIO_AVAILABLE = True
                USE_ASYNC = False
                USE_RASTREIO_CORREIOS = True
                logger_rastreio.info("Biblioteca rastreio_correios importada com sucesso (função)")
            elif hasattr(rastreio_correios, 'RastreioCorreios'):
                from rastreio_correios import RastreioCorreios
                RASTREIO_AVAILABLE = True
                USE_ASYNC = False
                USE_RASTREIO_CORREIOS = True
                logger_rastreio.info("Biblioteca rastreio_correios importada com sucesso (classe)")
            else:
                # Tentar usar diretamente o módulo
                RASTREIO_AVAILABLE = True
                USE_ASYNC = False
                USE_RASTREIO_CORREIOS = True
                logger_rastreio.info("Biblioteca rastreio_correios importada (módulo direto)")
        except Exception as e3:
            RASTREIO_AVAILABLE = False
            USE_ASYNC = False
            USE_RASTREIO_CORREIOS = False
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
                elif USE_RASTREIO_CORREIOS:
                    # rastreio_correios pode ter diferentes formas de uso
                    global rastreio_correios_module
                    if rastreio_correios_module:
                        if hasattr(rastreio_correios_module, 'rastrear'):
                            # É uma função
                            self.rastreio_client = rastreio_correios_module
                            logger_rastreio.info("rastreio_correios configurado (função)")
                        elif hasattr(rastreio_correios_module, 'RastreioCorreios'):
                            # É uma classe
                            self.rastreio_client = rastreio_correios_module.RastreioCorreios()
                            logger_rastreio.info("rastreio_correios configurado (classe)")
                        else:
                            # Tentar usar o módulo diretamente
                            self.rastreio_client = rastreio_correios_module
                            logger_rastreio.info("rastreio_correios configurado (módulo)")
            except Exception as e:
                self.rastreio_client = None
                logger_rastreio.error(f"Erro ao configurar biblioteca de rastreamento: {e}", exc_info=True)
        else:
            logger_rastreio.warning("Nenhuma biblioteca de rastreamento disponível")
    
    def validar_codigo(self, codigo: str) -> bool:
        """Validar formato do código de rastreamento"""
        # Formato: 2 letras + 9 dígitos + 2 letras (ex: YO065460434BR)
        # Ou formato antigo: 13 caracteres alfanuméricos
        codigo = codigo.upper().strip()
        pattern = r'^[A-Z]{2}\d{9}[A-Z]{2}$|^[A-Z0-9]{13}$'
        return bool(re.match(pattern, codigo))
    
    async def buscar_rastreio(self, codigo: str):
        """Buscar informações de rastreamento"""
        codigo = codigo.upper().strip()
        
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
        
        try:
            # Prioridade 1: usar pyrastreio (biblioteca oficial que usa API dos Correios)
            if USE_PYRASTREIO:
                resultado = await asyncio.to_thread(correios.track, codigo)
                if resultado:
                    # pyrastreio retorna uma lista de eventos
                    if isinstance(resultado, list) and len(resultado) > 0:
                        return resultado, None
                    elif isinstance(resultado, dict):
                        return [resultado], None
                return None, "❌ Nenhuma informação encontrada para este código. Verifique se o código está correto."
            
            # Prioridade 2: usar rastreio-correios-async (assíncrono)
            if hasattr(self, 'rastreio_client') and self.rastreio_client and self.rastreio_client is not True:
                if USE_ASYNC:
                    # Versão assíncrona
                    resultado = await self.rastreio_client.rastrear(codigo)
                    if resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                    elif resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                elif USE_RASTREIO_CORREIOS:
                    # rastreio_correios pode ser função, classe ou módulo
                    try:
                        if callable(self.rastreio_client):
                            # É uma função
                            resultado = await asyncio.to_thread(self.rastreio_client, codigo)
                        elif hasattr(self.rastreio_client, 'rastrear'):
                            # É uma classe com método rastrear
                            resultado = await asyncio.to_thread(self.rastreio_client.rastrear, codigo)
                        else:
                            # Tentar usar diretamente
                            resultado = await asyncio.to_thread(self.rastreio_client.rastrear, codigo) if hasattr(self.rastreio_client, 'rastrear') else None
                        
                        if resultado:
                            if isinstance(resultado, list):
                                return resultado, None
                            elif isinstance(resultado, dict):
                                if 'eventos' in resultado:
                                    return resultado['eventos'], None
                                return [resultado], None
                            elif hasattr(resultado, 'eventos'):
                                return resultado.eventos, None
                    except Exception as e:
                        logger_rastreio.error(f"Erro ao usar rastreio_correios: {e}", exc_info=True)
                else:
                    # Versão síncrona (usar thread)
                    resultado = await asyncio.to_thread(self.rastreio_client.rastrear, codigo)
                    if resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                    elif resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                
                return None, "❌ Nenhuma informação encontrada para este código. Verifique se o código está correto."
            
            # Se nenhuma biblioteca está disponível
            return None, "❌ Biblioteca de rastreamento não instalada. Instale: pip install pyrastreio"
            
        except Exception as e:
            logger_rastreio.error(f"Erro ao buscar rastreamento: {e}", exc_info=True)
            return None, f"❌ Erro ao buscar rastreamento: {str(e)[:150]}"
    
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
                    logger_rastreio.warning("pyrastreio não disponível")
                    await self.send_private_response(
                        ctx,
                        content="❌ **Biblioteca de rastreamento não instalada!**\n\n"
                               "Para usar o comando `/rastrear`, instale a biblioteca:\n"
                               "• `pip install pyrastreio`\n\n"
                               "A biblioteca está no `requirements.txt` e deve ser instalada automaticamente.\n"
                               "Verifique os logs da Square Cloud se a instalação falhou."
                    )
                    return
            
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

