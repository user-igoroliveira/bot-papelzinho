import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime

# Tentar importar bibliotecas de rastreamento (prioridade: pyrastreio primeiro por ser mais confiável)
try:
    from pyrastreio import correios
    RASTREIO_AVAILABLE = True
    USE_PYRASTREIO = True
except ImportError:
    USE_PYRASTREIO = False
    try:
        from rastreio_correios_async import Rastreio
        RASTREIO_AVAILABLE = True
        USE_ASYNC = True
    except ImportError:
        try:
            from rastreio_correios import RastreioCorreios
            RASTREIO_AVAILABLE = True
            USE_ASYNC = False
        except ImportError:
            RASTREIO_AVAILABLE = False
            USE_ASYNC = False

class Rastreio(commands.Cog):
    """Sistema de rastreamento de encomendas dos Correios"""
    
    def __init__(self, bot):
        self.bot = bot
        self.rastreio = None
        if RASTREIO_AVAILABLE:
            try:
                if 'USE_PYRASTREIO' in globals() and USE_PYRASTREIO:
                    # pyrastreio não precisa de instância
                    self.rastreio = True
                elif 'USE_ASYNC' in globals() and USE_ASYNC:
                    self.rastreio = Rastreio()
                elif not USE_ASYNC:
                    self.rastreio = RastreioCorreios()
            except:
                self.rastreio = None
    
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
            # Prioridade 1: usar pyrastreio (mais confiável e amplamente disponível)
            if 'USE_PYRASTREIO' in globals() and USE_PYRASTREIO:
                resultado = await asyncio.to_thread(correios.track, codigo)
                if resultado:
                    # pyrastreio retorna uma lista de eventos
                    if isinstance(resultado, list) and len(resultado) > 0:
                        return resultado, None
                    elif isinstance(resultado, dict):
                        return [resultado], None
                return None, "❌ Nenhuma informação encontrada para este código."
            
            # Prioridade 2: usar rastreio-correios-async (assíncrono)
            if hasattr(self, 'rastreio') and self.rastreio and self.rastreio is not True:
                if 'USE_ASYNC' in globals() and USE_ASYNC:
                    # Versão assíncrona
                    resultado = await self.rastreio.rastrear(codigo)
                    if resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                    elif resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                else:
                    # Versão síncrona (usar thread)
                    resultado = await asyncio.to_thread(self.rastreio.rastrear, codigo)
                    if resultado and hasattr(resultado, 'eventos'):
                        return resultado.eventos, None
                    elif resultado and isinstance(resultado, dict) and 'eventos' in resultado:
                        return resultado['eventos'], None
                
                return None, "❌ Nenhuma informação encontrada para este código."
            
            return None, "❌ Biblioteca de rastreamento não disponível."
            
        except Exception as e:
            return None, f"❌ Erro ao buscar rastreamento: {str(e)}"
    
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
        
        if not RASTREIO_AVAILABLE:
            await self.send_private_response(
                ctx,
                content="❌ **Biblioteca de rastreamento não instalada!**\n\n"
                       "Instale a biblioteca:\n"
                       "• `pip install pyrastreio`\n\n"
                       "A biblioteca está no requirements.txt e deve ser instalada automaticamente."
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
        
        # Enviar mensagem de carregamento
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Buscar informações de rastreamento
        eventos, erro = await self.buscar_rastreio(codigo)
        
        if erro:
            await self.send_private_response(ctx, content=erro)
            return
        
        if not eventos:
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
            # Formatar evento dependendo da biblioteca usada
            if isinstance(evento, dict):
                # pyrastreio ou outras bibliotecas que retornam dict
                # pyrastreio usa: data, status, local
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
            
            eventos_formatados.append(f"**{i}.** {data_formatada}\n{descricao}\n📍 {local_completo}")
        
        # Dividir eventos em campos (máximo 1024 caracteres por campo)
        campo_atual = ""
        campo_num = 1
        
        for evento_texto in eventos_formatados:
            if len(campo_atual) + len(evento_texto) + 2 > 1024:
                embed.add_field(
                    name=f"📋 Eventos {campo_num}",
                    value=campo_atual,
                    inline=False
                )
                campo_atual = evento_texto + "\n\n"
                campo_num += 1
            else:
                campo_atual += evento_texto + "\n\n"
        
        if campo_atual:
            embed.add_field(
                name=f"📋 Eventos {campo_num}" if campo_num > 1 else "📋 Histórico",
                value=campo_atual,
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Rastreio(bot))

