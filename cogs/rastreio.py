import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime
import logging

logger_rastreio = logging.getLogger(__name__)

# Tentar importar biblioteca de rastreamento
RASTREIO_AVAILABLE = False
rastreio_func = None

# Prioridade: usar rastreio_correios que já está instalada e funcionando
try:
    import rastreio_correios
    # Verificar como usar a biblioteca
    if hasattr(rastreio_correios, 'rastrear'):
        RASTREIO_AVAILABLE = True
        rastreio_func = rastreio_correios.rastrear
        logger_rastreio.info("✅ rastreio_correios importado (função)")
    elif hasattr(rastreio_correios, 'RastreioCorreios'):
        RASTREIO_AVAILABLE = True
        rastreio_func = rastreio_correios.RastreioCorreios().rastrear
        logger_rastreio.info("✅ rastreio_correios importado (classe)")
    else:
        logger_rastreio.warning("rastreio_correios instalado mas formato desconhecido")
except Exception as e:
    logger_rastreio.warning(f"rastreio_correios não disponível: {e}")
    # Fallback: tentar pyrastreio (pode não funcionar corretamente)
    try:
        import pyrastreio
        # pyrastreio pode ser usado diretamente como função
        if callable(pyrastreio):
            RASTREIO_AVAILABLE = True
            rastreio_func = pyrastreio
            logger_rastreio.info("✅ pyrastreio importado (função direta)")
        else:
            logger_rastreio.warning("pyrastreio não é callable")
    except ImportError as e2:
        logger_rastreio.warning(f"pyrastreio não disponível: {e2}")


class Rastreio(commands.Cog):
    """Sistema de rastreamento de encomendas dos Correios"""
    
    def __init__(self, bot):
        self.bot = bot
        logger_rastreio.info("Cog Rastreio inicializado")
    
    async def send_private_response(self, ctx, content=None, embed=None):
        """Enviar resposta privada (ephemeral para slash, DM para prefixo)"""
        if ctx.interaction:
            # Slash command - usar ephemeral
            try:
                if ctx.interaction.response.is_done():
                    # Usar followup se já foi respondido
                    if embed:
                        await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await ctx.interaction.followup.send(content=content, ephemeral=True)
                else:
                    # Responder diretamente
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
    
    def validar_codigo(self, codigo: str) -> bool:
        """Validar formato do código de rastreamento"""
        codigo = codigo.upper().strip()
        pattern = r'^[A-Z]{2}\d{9}[A-Z]{2}$|^[A-Z0-9]{13}$'
        return bool(re.match(pattern, codigo))
    
    async def buscar_rastreio(self, codigo: str):
        """Buscar informações de rastreamento"""
        if not RASTREIO_AVAILABLE or not rastreio_func:
            return None, "❌ Biblioteca de rastreamento não instalada. Instale: pip install pyrastreio"
        
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
        
        try:
            # Executar busca com timeout
            resultado = await asyncio.wait_for(
                asyncio.to_thread(rastreio_func, codigo),
                timeout=10.0
            )
            
            if not resultado:
                return None, "❌ Nenhuma informação encontrada para este código."
            
            # Normalizar resultado para lista
            if isinstance(resultado, list):
                eventos = resultado
            elif isinstance(resultado, dict):
                # Se for dict, pode ter 'eventos' ou ser um evento único
                if 'eventos' in resultado:
                    eventos = resultado['eventos']
                else:
                    eventos = [resultado]
            else:
                # Tentar acessar como objeto
                if hasattr(resultado, 'eventos'):
                    eventos = resultado.eventos
                elif hasattr(resultado, '__iter__'):
                    eventos = list(resultado)
                else:
                    eventos = [resultado]
            
            if not eventos or len(eventos) == 0:
                return None, "❌ Nenhuma informação encontrada para este código."
            
            return eventos, None
            
        except asyncio.TimeoutError:
            return None, "❌ Timeout ao buscar informações. Tente novamente."
        except Exception as e:
            logger_rastreio.error(f"Erro ao buscar rastreamento: {e}", exc_info=True)
            return None, f"❌ Erro ao buscar rastreamento: {str(e)[:100]}"
    
    @commands.hybrid_command(name='rastrear', aliases=['rastreio', 'track'])
    @app_commands.describe(codigo='Código de rastreamento dos Correios (ex: YO065460434BR)')
    async def rastrear(self, ctx, *, codigo: str = None):
        """Rastrear encomenda dos Correios pelo código"""
        
        if not codigo:
            await self.send_private_response(
                ctx,
                content="📦 **Rastreamento de Encomendas**\n\n"
                       "Por favor, informe o código de rastreamento.\n"
                       "Formato: `YO065460434BR`\n\n"
                       "Exemplo: `/rastrear YO065460434BR` ou `!rastrear YO065460434BR`"
            )
            return
        
        # Enviar mensagem de carregamento
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Validar código
        if not self.validar_codigo(codigo):
            await self.send_private_response(
                ctx,
                content="❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
            )
            return
        
        # Buscar informações
        eventos, erro = await self.buscar_rastreio(codigo)
        
        if erro:
            await self.send_private_response(ctx, content=erro)
            return
        
        if not eventos:
            await self.send_private_response(
                ctx,
                content=f"❌ Nenhuma informação encontrada para o código: **{codigo}**"
            )
            return
        
        # Criar embed com resultados
        embed = discord.Embed(
            title=f"📦 Rastreamento - {codigo}",
            description=f"**{len(eventos)}** evento(s) encontrado(s):",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Formatar eventos
        eventos_formatados = []
        for i, evento in enumerate(eventos[:10], 1):
            try:
                # Extrair dados do evento
                if isinstance(evento, dict):
                    data = evento.get('data', evento.get('dataHora', evento.get('timestamp', 'N/A')))
                    descricao = evento.get('status', evento.get('descricao', evento.get('evento', 'N/A')))
                    local = evento.get('local', evento.get('cidade', evento.get('origem', '')))
                    uf = evento.get('uf', evento.get('estado', ''))
                else:
                    data = getattr(evento, 'data', getattr(evento, 'dataHora', 'N/A'))
                    descricao = getattr(evento, 'descricao', getattr(evento, 'status', 'N/A'))
                    local = getattr(evento, 'local', getattr(evento, 'cidade', ''))
                    uf = getattr(evento, 'uf', '')
                
                # Formatar data
                if isinstance(data, str):
                    data_formatada = data
                else:
                    try:
                        data_formatada = data.strftime("%d/%m/%Y %H:%M")
                    except:
                        data_formatada = str(data)
                
                # Formatar local
                local_completo = f"{local}/{uf}" if local and uf else local or uf or "N/A"
                
                # Limitar tamanhos
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
        
        # Adicionar campos ao embed (dividir se necessário)
        campo_atual = ""
        campo_num = 1
        
        for evento_texto in eventos_formatados:
            if len(campo_atual) + len(evento_texto) + 2 > 1024:
                if campo_atual:
                    embed.add_field(
                        name=f"📋 Eventos {campo_num}",
                        value=campo_atual[:1024],
                        inline=False
                    )
                campo_atual = evento_texto + "\n\n"
                campo_num += 1
            else:
                campo_atual += evento_texto + "\n\n"
        
        if campo_atual:
            embed.add_field(
                name=f"📋 Eventos {campo_num}" if campo_num > 1 else "📋 Histórico",
                value=campo_atual[:1024],
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    try:
        cog = Rastreio(bot)
        await bot.add_cog(cog)
        logger_rastreio.info("✅ Cog Rastreio carregado com sucesso")
        logger_rastreio.info("✅ Comando /rastrear registrado")
    except Exception as e:
        logger_rastreio.error(f"❌ Erro ao carregar cog Rastreio: {e}", exc_info=True)
        raise
