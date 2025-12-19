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
rastreio_client = None

def detectar_biblioteca():
    """Detectar e configurar biblioteca de rastreamento"""
    global RASTREIO_AVAILABLE, rastreio_func, rastreio_client
    
    # Prioridade: usar rastreio_correios que já está instalada e funcionando
    try:
        import rastreio_correios
        logger_rastreio.info(f"rastreio_correios importado, atributos: {dir(rastreio_correios)}")
        
        # Verificar se tem classe Rastreio
        if hasattr(rastreio_correios, 'Rastreio'):
            try:
                rastreio_client = rastreio_correios.Rastreio()
                # Verificar métodos disponíveis
                metodos = [m for m in dir(rastreio_client) if not m.startswith('_')]
                logger_rastreio.info(f"Rastreio instanciado, métodos: {metodos}")
                
                # Tentar métodos comuns
                if hasattr(rastreio_client, 'rastrear'):
                    RASTREIO_AVAILABLE = True
                    rastreio_func = rastreio_client.rastrear
                    logger_rastreio.info("✅ rastreio_correios importado (Rastreio.rastrear)")
                    return True
                elif hasattr(rastreio_client, 'rastreamento'):
                    RASTREIO_AVAILABLE = True
                    rastreio_func = rastreio_client.rastreamento
                    logger_rastreio.info("✅ rastreio_correios importado (Rastreio.rastreamento)")
                    return True
                elif hasattr(rastreio_client, 'buscar'):
                    RASTREIO_AVAILABLE = True
                    rastreio_func = rastreio_client.buscar
                    logger_rastreio.info("✅ rastreio_correios importado (Rastreio.buscar)")
                    return True
                elif hasattr(rastreio_client, 'track'):
                    RASTREIO_AVAILABLE = True
                    rastreio_func = rastreio_client.track
                    logger_rastreio.info("✅ rastreio_correios importado (Rastreio.track)")
                    return True
            except Exception as e:
                logger_rastreio.warning(f"Erro ao instanciar Rastreio: {e}")
        
        # Verificar se tem rastreador (pode ser função ou classe)
        if hasattr(rastreio_correios, 'rastreador'):
            rastreador = rastreio_correios.rastreador
            logger_rastreio.info(f"rastreador encontrado, tipo: {type(rastreador)}, callable: {callable(rastreador)}")
            
            if callable(rastreador):
                # Tentar usar como função diretamente
                try:
                    RASTREIO_AVAILABLE = True
                    rastreio_func = rastreador
                    logger_rastreio.info("✅ rastreio_correios importado (rastreador como função)")
                    return True
                except Exception as e:
                    logger_rastreio.warning(f"rastreador não funcionou como função: {e}")
                
                # Pode ser classe, tentar instanciar
                try:
                    rastreio_client = rastreador()
                    metodos_rastreador = [m for m in dir(rastreio_client) if not m.startswith('_')]
                    logger_rastreio.info(f"rastreador instanciado, métodos: {metodos_rastreador}")
                    
                    # Tentar métodos comuns
                    for metodo in ['rastrear', 'rastreamento', 'buscar', 'track', 'get']:
                        if hasattr(rastreio_client, metodo):
                            RASTREIO_AVAILABLE = True
                            rastreio_func = getattr(rastreio_client, metodo)
                            logger_rastreio.info(f"✅ rastreio_correios importado (rastreador().{metodo})")
                            return True
                except Exception as e:
                    logger_rastreio.warning(f"Erro ao instanciar rastreador: {e}")
        
        # Verificar se tem função rastrear diretamente
        if hasattr(rastreio_correios, 'rastrear') and callable(rastreio_correios.rastrear):
            RASTREIO_AVAILABLE = True
            rastreio_func = rastreio_correios.rastrear
            logger_rastreio.info("✅ rastreio_correios importado (função rastrear)")
            return True
            
        logger_rastreio.warning(f"rastreio_correios instalado mas formato desconhecido. Atributos: {dir(rastreio_correios)}")
    except Exception as e:
        logger_rastreio.warning(f"rastreio_correios não disponível: {e}")
    
    # Fallback: tentar pyrastreio
    try:
        import pyrastreio
        if callable(pyrastreio):
            RASTREIO_AVAILABLE = True
            rastreio_func = pyrastreio
            logger_rastreio.info("✅ pyrastreio importado (função direta)")
            return True
    except ImportError as e2:
        logger_rastreio.warning(f"pyrastreio não disponível: {e2}")
    
    return False

# Tentar detectar na inicialização
detectar_biblioteca()


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
        global RASTREIO_AVAILABLE, rastreio_func, rastreio_client
        
        # Tentar detectar biblioteca novamente se não estiver disponível
        if not RASTREIO_AVAILABLE or not rastreio_func:
            logger_rastreio.info("Biblioteca não detectada, tentando detectar novamente...")
            detectar_biblioteca()
        
        if not RASTREIO_AVAILABLE or not rastreio_func:
            return None, "❌ Biblioteca de rastreamento não instalada. Instale: pip install rastreio-correios"
        
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
        
        try:
            # Executar busca com timeout
            logger_rastreio.info(f"Buscando rastreamento para código: {codigo}")
            logger_rastreio.info(f"rastreio_client: {rastreio_client}, rastreio_func: {rastreio_func}")
            
            # Se temos um cliente instanciado, usar o método dele
            if rastreio_client:
                # Tentar diferentes métodos
                if hasattr(rastreio_client, 'rastrear'):
                    logger_rastreio.info("Usando rastreio_client.rastrear")
                    resultado = await asyncio.wait_for(
                        asyncio.to_thread(rastreio_client.rastrear, codigo),
                        timeout=10.0
                    )
                elif hasattr(rastreio_client, 'rastreamento'):
                    logger_rastreio.info("Usando rastreio_client.rastreamento")
                    resultado = await asyncio.wait_for(
                        asyncio.to_thread(rastreio_client.rastreamento, codigo),
                        timeout=10.0
                    )
                elif hasattr(rastreio_client, 'buscar'):
                    logger_rastreio.info("Usando rastreio_client.buscar")
                    resultado = await asyncio.wait_for(
                        asyncio.to_thread(rastreio_client.buscar, codigo),
                        timeout=10.0
                    )
                elif hasattr(rastreio_client, 'track'):
                    logger_rastreio.info("Usando rastreio_client.track")
                    resultado = await asyncio.wait_for(
                        asyncio.to_thread(rastreio_client.track, codigo),
                        timeout=10.0
                    )
                else:
                    logger_rastreio.warning("rastreio_client não tem método conhecido, tentando rastreio_func")
                    if rastreio_func:
                        resultado = await asyncio.wait_for(
                            asyncio.to_thread(rastreio_func, codigo),
                            timeout=10.0
                        )
                    else:
                        return None, "❌ Método de rastreamento não encontrado"
            elif rastreio_func:
                # Usar função diretamente
                logger_rastreio.info("Usando rastreio_func diretamente")
                resultado = await asyncio.wait_for(
                    asyncio.to_thread(rastreio_func, codigo),
                    timeout=10.0
                )
            else:
                return None, "❌ Biblioteca de rastreamento não configurada corretamente"
            
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
            
            # Log do resultado para diagnóstico
            logger_rastreio.info(f"Resultado recebido: tipo={type(eventos)}, quantidade={len(eventos)}")
            if eventos and len(eventos) > 0:
                logger_rastreio.info(f"Primeiro evento: tipo={type(eventos[0])}, conteúdo={eventos[0]}")
                if isinstance(eventos[0], dict):
                    logger_rastreio.info(f"Chaves do primeiro evento: {list(eventos[0].keys())}")
            
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
                # Log do evento para diagnóstico
                logger_rastreio.info(f"Processando evento {i}: tipo={type(evento)}, conteúdo={evento}")
                
                # Extrair dados do evento
                if isinstance(evento, dict):
                    # Tentar múltiplas chaves possíveis
                    data = (evento.get('data') or evento.get('dataHora') or evento.get('timestamp') or 
                           evento.get('dtHrCriado') or evento.get('data_evento') or evento.get('date') or 'N/A')
                    descricao = (evento.get('status') or evento.get('descricao') or evento.get('evento') or 
                                evento.get('tipo') or evento.get('mensagem') or evento.get('texto') or 'N/A')
                    local = (evento.get('local') or evento.get('cidade') or evento.get('origem') or 
                            evento.get('unidade', {}).get('endereco', {}).get('cidade', '') if isinstance(evento.get('unidade'), dict) else '')
                    uf = (evento.get('uf') or evento.get('estado') or 
                         evento.get('unidade', {}).get('endereco', {}).get('uf', '') if isinstance(evento.get('unidade'), dict) else '')
                else:
                    # Tentar múltiplos atributos possíveis
                    data = (getattr(evento, 'data', None) or getattr(evento, 'dataHora', None) or 
                           getattr(evento, 'timestamp', None) or getattr(evento, 'dtHrCriado', None) or 'N/A')
                    descricao = (getattr(evento, 'descricao', None) or getattr(evento, 'status', None) or 
                               getattr(evento, 'evento', None) or getattr(evento, 'tipo', None) or 'N/A')
                    local = (getattr(evento, 'local', None) or getattr(evento, 'cidade', None) or 
                            getattr(evento, 'origem', None) or '')
                    uf = (getattr(evento, 'uf', None) or getattr(evento, 'estado', None) or '')
                
                # Log dos valores extraídos
                logger_rastreio.info(f"Evento {i} extraído: data={data}, descricao={descricao}, local={local}, uf={uf}")
                
                # Formatar data
                if data and data != 'N/A':
                    if isinstance(data, str):
                        data_formatada = data
                    else:
                        try:
                            data_formatada = data.strftime("%d/%m/%Y %H:%M")
                        except:
                            data_formatada = str(data)
                else:
                    data_formatada = "Data não disponível"
                
                # Formatar local
                if local and uf:
                    local_completo = f"{local}/{uf}"
                elif local:
                    local_completo = local
                elif uf:
                    local_completo = uf
                else:
                    local_completo = "Local não informado"
                
                # Garantir que descrição não seja vazia
                if not descricao or descricao == 'N/A':
                    descricao = "Informação não disponível"
                
                # Limitar tamanhos
                descricao = descricao[:200] if len(descricao) > 200 else descricao
                local_completo = local_completo[:100] if len(local_completo) > 100 else local_completo
                
                # Montar texto do evento
                evento_texto = f"**{i}.** {data_formatada}\n{descricao}\n📍 {local_completo}"
                eventos_formatados.append(evento_texto)
                logger_rastreio.info(f"Evento {i} formatado: {evento_texto[:100]}")
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
