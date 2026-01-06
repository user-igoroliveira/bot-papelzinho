import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime
import logging
import aiohttp
import json
import os
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

logger_rastreio = logging.getLogger(__name__)


class Rastreio(commands.Cog):
    """Sistema de rastreamento de encomendas dos Correios"""
    
    def __init__(self, bot):
        self.bot = bot
        # Token da API Linketrack
        self.linketrack_token = os.getenv('LINKETRACK_TOKEN', 'RZurnRHdoH-u_GwnOUSHdpjDOp-ip8cKOx_qhpUc07w')
        logger_rastreio.info("Cog Rastreio inicializado com API Linketrack")
    
    async def send_private_response(self, ctx, content=None, embed=None):
        """Enviar resposta privada (ephemeral para slash, DM para prefixo)"""
        if ctx.interaction:
            try:
                if ctx.interaction.response.is_done():
                    if embed:
                        await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        await ctx.interaction.followup.send(content=content, ephemeral=True)
                else:
                    if embed:
                        await ctx.interaction.response.send_message(embed=embed, ephemeral=True)
                    else:
                        await ctx.interaction.response.send_message(content=content, ephemeral=True)
            except discord.InteractionResponded:
                if embed:
                    await ctx.interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(content=content, ephemeral=True)
        else:
            try:
                if embed:
                    await ctx.author.send(embed=embed)
                else:
                    await ctx.author.send(content=content)
                await ctx.send("✅ Resposta enviada por mensagem privada!", delete_after=5)
            except discord.Forbidden:
                await ctx.send("❌ Não foi possível enviar mensagem privada. Verifique se você permite DMs de membros do servidor.")
    
    def validar_codigo(self, codigo: str) -> bool:
        """Validar formato do código de rastreamento"""
        if not codigo:
            return False
        codigo = codigo.upper().strip()
        # Formato padrão: 2 letras + 9 dígitos + 2 letras (ex: AN388458437BR)
        pattern = r'^[A-Z]{2}\d{9}[A-Z]{2}$|^[A-Z0-9]{13}$'
        return bool(re.match(pattern, codigo))
    
    async def buscar_linketrack(self, codigo: str, max_retries: int = 3):
        """Buscar rastreamento usando API Linketrack"""
        url = "https://api.linketrack.com/track/json"
        
        params = {
            'user': 'teste',
            'token': self.linketrack_token,
            'codigo': codigo
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }
        
        timeout = aiohttp.ClientTimeout(total=20)
        
        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, params=params, headers=headers) as response:
                        logger_rastreio.info(f"Linketrack status: {response.status} (tentativa {attempt + 1}/{max_retries})")
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            # Verificar se retornou dados válidos
                            if not data:
                                logger_rastreio.warning("Linketrack retornou dados vazios")
                                return None, "❌ Nenhuma informação encontrada."
                            
                            # Verificar se há eventos
                            if 'eventos' in data and data['eventos']:
                                eventos = []
                                
                                for ev in data['eventos']:
                                    # Extrair dados do evento
                                    data_str = ev.get('data', '')
                                    hora_str = ev.get('hora', '')
                                    
                                    # Combinar data e hora
                                    if data_str and hora_str:
                                        data_completa = f"{data_str} {hora_str}"
                                    elif data_str:
                                        data_completa = data_str
                                    else:
                                        data_completa = "Data não disponível"
                                    
                                    # Montar evento formatado
                                    evento = {
                                        'data': data_completa,
                                        'descricao': ev.get('status', ev.get('descricao', 'Informação não disponível')),
                                        'local': ev.get('local', ''),
                                        'uf': ev.get('uf', ''),
                                        'origem': ev.get('origem', ''),
                                        'destino': ev.get('destino', '')
                                    }
                                    eventos.append(evento)
                                
                                if eventos:
                                    logger_rastreio.info(f"✅ Linketrack retornou {len(eventos)} eventos")
                                    return eventos, None
                                else:
                                    logger_rastreio.warning("Linketrack retornou eventos vazios após formatação")
                            
                            # Verificar mensagem de erro
                            if 'mensagem' in data and data['mensagem']:
                                mensagem = data['mensagem']
                                logger_rastreio.info(f"Linketrack mensagem: {mensagem}")
                                return None, f"❌ {mensagem}"
                            
                            # Verificar erro específico
                            if 'erro' in data and data['erro']:
                                erro = data['erro']
                                logger_rastreio.warning(f"Linketrack erro: {erro}")
                                return None, f"❌ {erro}"
                            
                            return None, "❌ Código não encontrado ou sem informações disponíveis."
                        
                        elif response.status == 404:
                            return None, "❌ Código de rastreamento não encontrado."
                        
                        elif response.status == 401:
                            logger_rastreio.error("Token Linketrack inválido")
                            return None, "❌ Erro de autenticação na API. Entre em contato com o administrador."
                        
                        elif response.status == 429:
                            # Rate limit - aguardar antes de tentar novamente
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt) * 2
                                logger_rastreio.warning(f"Rate limit atingido, aguardando {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                return None, "❌ Limite de requisições atingido. Tente novamente em alguns minutos."
                        
                        elif response.status >= 500:
                            # Erro do servidor - tentar novamente
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt)
                                logger_rastreio.warning(f"Erro do servidor {response.status}, tentando novamente em {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                return None, "❌ Serviço temporariamente indisponível. Tente novamente mais tarde."
                        
                        else:
                            text = await response.text()
                            logger_rastreio.warning(f"Linketrack erro {response.status}: {text[:200]}")
                            
                            if attempt < max_retries - 1:
                                wait_time = 2 ** attempt
                                await asyncio.sleep(wait_time)
                                continue
                            
                            return None, f"❌ Erro ao consultar API (Status: {response.status})"
                        
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    logger_rastreio.warning(f"Timeout, tentando novamente... ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    logger_rastreio.error("Timeout após todas as tentativas")
                    return None, "❌ Timeout ao consultar API. Tente novamente."
            
            except aiohttp.ClientError as e:
                logger_rastreio.error(f"Erro de conexão: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                else:
                    return None, "❌ Erro de conexão. Verifique sua internet e tente novamente."
            
            except Exception as e:
                logger_rastreio.error(f"Erro inesperado: {e}", exc_info=True)
                return None, f"❌ Erro ao buscar rastreamento: {str(e)[:100]}"
        
        return None, "❌ Não foi possível consultar o rastreamento após várias tentativas."
    
    async def buscar_rastreio(self, codigo: str):
        """Buscar informações de rastreamento"""
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: AN388458437BR"
        
        codigo = codigo.upper().strip()
        logger_rastreio.info(f"Iniciando rastreamento para código: {codigo}")
        
        # Buscar usando Linketrack
        eventos, erro = await self.buscar_linketrack(codigo)
        
        if eventos:
            return eventos, None
        
        return None, erro if erro else "❌ Não foi possível buscar informações de rastreamento."
    
    @commands.hybrid_command(name='rastrear', aliases=['rastreio', 'track'])
    @app_commands.describe(codigo='Código de rastreamento dos Correios (ex: AN388458437BR)')
    async def rastrear(self, ctx, *, codigo: str = None):
        """Rastrear encomenda dos Correios pelo código"""
        
        if not codigo:
            await self.send_private_response(
                ctx,
                content="📦 **Rastreamento de Encomendas dos Correios**\n\n"
                       "Por favor, informe o código de rastreamento.\n\n"
                       "**Formato:** `AN388458437BR`\n"
                       "*(2 letras + 9 números + 2 letras)*\n\n"
                       "**Exemplos:**\n"
                       "`/rastrear AN388458437BR`\n"
                       "`!rastrear YO065460434BR`"
            )
            return
        
        # Enviar mensagem de carregamento
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        else:
            # Para comandos com prefixo, enviar mensagem temporária
            msg = await ctx.send("🔍 Buscando informações de rastreamento...")
        
        # Limpar código (remover espaços, hífens, etc)
        codigo_limpo = re.sub(r'[^A-Z0-9]', '', codigo.upper())
        
        # Validar código
        if not self.validar_codigo(codigo_limpo):
            if not ctx.interaction:
                await msg.delete()
            
            await self.send_private_response(
                ctx,
                content=f"❌ **Código de rastreamento inválido!**\n\n"
                       f"**Formato esperado:** `AN388458437BR`\n"
                       f"*(2 letras + 9 números + 2 letras)*\n\n"
                       f"**Você digitou:** `{codigo}`"
            )
            return
        
        # Buscar informações
        eventos, erro = await self.buscar_rastreio(codigo_limpo)
        
        # Deletar mensagem de carregamento se for comando com prefixo
        if not ctx.interaction:
            try:
                await msg.delete()
            except:
                pass
        
        if erro:
            await self.send_private_response(ctx, content=erro)
            return
        
        if not eventos:
            await self.send_private_response(
                ctx,
                content=f"❌ Nenhuma informação encontrada para o código: **{codigo_limpo}**"
            )
            return
        
        # Criar embed com resultados
        # Determinar cor baseada no status mais recente
        ultimo_status = eventos[0].get('descricao', '').lower()
        if 'entregue' in ultimo_status or 'entrega realizada' in ultimo_status:
            cor = discord.Color.green()
            emoji_status = "✅"
        elif 'saiu para entrega' in ultimo_status:
            cor = discord.Color.orange()
            emoji_status = "🚚"
        elif 'aguardando' in ultimo_status or 'postado' in ultimo_status:
            cor = discord.Color.blue()
            emoji_status = "📦"
        else:
            cor = discord.Color.blue()
            emoji_status = "📦"
        
        embed = discord.Embed(
            title=f"{emoji_status} Rastreamento - {codigo_limpo}",
            description=f"**Status:** {eventos[0].get('descricao', 'Informação não disponível')}\n"
                       f"**Total de eventos:** {len(eventos)}",
            color=cor,
            timestamp=datetime.utcnow()
        )
        
        # Formatar eventos (limitar a 10 mais recentes)
        eventos_texto = []
        
        for i, evento in enumerate(eventos[:10], 1):
            try:
                # Formatar data
                data_str = evento.get('data', 'Data não disponível')
                
                # Formatar descrição
                descricao = evento.get('descricao', 'Informação não disponível')
                if len(descricao) > 150:
                    descricao = descricao[:147] + "..."
                
                # Formatar local
                local = evento.get('local', '')
                uf = evento.get('uf', '')
                
                if local and uf:
                    local_completo = f"📍 {local}/{uf}"
                elif local:
                    local_completo = f"📍 {local}"
                elif uf:
                    local_completo = f"📍 {uf}"
                else:
                    local_completo = ""
                
                # Adicionar origem/destino se disponível
                origem = evento.get('origem', '')
                destino = evento.get('destino', '')
                rota = ""
                if origem and destino:
                    rota = f"\n🔄 {origem} → {destino}"
                elif origem:
                    rota = f"\n📤 {origem}"
                elif destino:
                    rota = f"\n📥 {destino}"
                
                # Montar texto do evento
                texto_evento = f"**{i}.** 🕐 {data_str}\n📝 {descricao}"
                if local_completo:
                    texto_evento += f"\n{local_completo}"
                if rota:
                    texto_evento += rota
                
                eventos_texto.append(texto_evento)
                
            except Exception as e:
                logger_rastreio.error(f"Erro ao formatar evento {i}: {e}", exc_info=True)
                continue
        
        if not eventos_texto:
            await self.send_private_response(
                ctx,
                content=f"❌ Erro ao processar eventos do código: **{codigo_limpo}**"
            )
            return
        
        # Adicionar eventos ao embed (dividir em campos se necessário)
        campo_atual = ""
        campo_num = 1
        
        for texto in eventos_texto:
            # Verificar se adicionar este evento ultrapassaria o limite de 1024 caracteres
            if len(campo_atual) + len(texto) + 2 > 1024:
                # Adicionar campo atual ao embed
                if campo_atual:
                    nome_campo = f"📋 Histórico {campo_num}" if campo_num > 1 else "📋 Histórico de Rastreamento"
                    embed.add_field(
                        name=nome_campo,
                        value=campo_atual.strip(),
                        inline=False
                    )
                # Iniciar novo campo
                campo_atual = texto + "\n\n"
                campo_num += 1
            else:
                campo_atual += texto + "\n\n"
        
        # Adicionar último campo se houver conteúdo
        if campo_atual:
            nome_campo = f"📋 Histórico {campo_num}" if campo_num > 1 else "📋 Histórico de Rastreamento"
            embed.add_field(
                name=nome_campo,
                value=campo_atual.strip(),
                inline=False
            )
        
        # Adicionar informações adicionais
        if len(eventos) > 10:
            embed.add_field(
                name="ℹ️ Informação",
                value=f"Mostrando os 10 eventos mais recentes de {len(eventos)} no total.",
                inline=False
            )
        
        embed.set_footer(
            text=f"Solicitado por {ctx.author.name} • Powered by Linketrack",
            icon_url=ctx.author.display_avatar.url
        )
        
        await self.send_private_response(ctx, embed=embed)
        
        logger_rastreio.info(f"Rastreamento concluído com sucesso para {codigo_limpo} - {len(eventos)} eventos retornados")


async def setup(bot):
    try:
        cog = Rastreio(bot)
        await bot.add_cog(cog)
        logger_rastreio.info("✅ Cog Rastreio carregado com sucesso")
        logger_rastreio.info("✅ Comando /rastrear registrado")
    except Exception as e:
        logger_rastreio.error(f"❌ Erro ao carregar cog Rastreio: {e}", exc_info=True)
        raise