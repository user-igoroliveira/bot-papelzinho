import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
from datetime import datetime
import logging
import aiohttp
import json

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
    
    async def buscar_api_correios(self, codigo: str):
        """Buscar rastreamento usando API JSON dos Correios (fallback)"""
        url = f"https://proxyapp.correios.com.br/v1/sro-rastro/{codigo}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger_rastreio.info(f"API JSON retornou: {json.dumps(data, indent=2)[:500]}")
                        
                        if data and 'objetos' in data and data['objetos']:
                            objeto = data['objetos'][0]
                            if 'eventos' in objeto and objeto['eventos']:
                                eventos = []
                                for ev in objeto['eventos']:
                                    evento_formatado = {
                                        'data': ev.get('dtHrCriado', ev.get('data', '')),
                                        'descricao': ev.get('descricao', ev.get('tipo', '')),
                                        'local': ev.get('unidade', {}).get('endereco', {}).get('cidade', ''),
                                        'uf': ev.get('unidade', {}).get('endereco', {}).get('uf', '')
                                    }
                                    eventos.append(evento_formatado)
                                
                                if eventos:
                                    logger_rastreio.info(f"API JSON retornou {len(eventos)} eventos")
                                    return eventos, None
                        
                        return None, "❌ Nenhuma informação encontrada na API dos Correios."
                    else:
                        logger_rastreio.warning(f"API JSON retornou status {response.status}")
                        return None, f"❌ Erro ao acessar API dos Correios (Status: {response.status})"
        except asyncio.TimeoutError:
            logger_rastreio.warning("Timeout ao acessar API JSON")
            return None, "❌ Timeout ao buscar informações."
        except Exception as e:
            logger_rastreio.error(f"Erro na API JSON: {e}", exc_info=True)
            return None, f"❌ Erro ao buscar na API: {str(e)[:100]}"
    
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
                    metodo = rastreio_client.rastrear
                    # Verificar se é assíncrono
                    if asyncio.iscoroutinefunction(metodo):
                        logger_rastreio.info("Método rastrear é assíncrono, usando await")
                        resultado = await asyncio.wait_for(metodo(codigo), timeout=10.0)
                    else:
                        logger_rastreio.info("Método rastrear é síncrono, usando thread")
                        resultado = await asyncio.wait_for(
                            asyncio.to_thread(metodo, codigo),
                            timeout=10.0
                        )
                elif hasattr(rastreio_client, 'rastreamento'):
                    logger_rastreio.info("Usando rastreio_client.rastreamento")
                    metodo = rastreio_client.rastreamento
                    if asyncio.iscoroutinefunction(metodo):
                        resultado = await asyncio.wait_for(metodo(codigo), timeout=10.0)
                    else:
                        resultado = await asyncio.wait_for(
                            asyncio.to_thread(metodo, codigo),
                            timeout=10.0
                        )
                elif hasattr(rastreio_client, 'buscar'):
                    logger_rastreio.info("Usando rastreio_client.buscar")
                    metodo = rastreio_client.buscar
                    if asyncio.iscoroutinefunction(metodo):
                        resultado = await asyncio.wait_for(metodo(codigo), timeout=10.0)
                    else:
                        resultado = await asyncio.wait_for(
                            asyncio.to_thread(metodo, codigo),
                            timeout=10.0
                        )
                elif hasattr(rastreio_client, 'track'):
                    logger_rastreio.info("Usando rastreio_client.track")
                    metodo = rastreio_client.track
                    if asyncio.iscoroutinefunction(metodo):
                        resultado = await asyncio.wait_for(metodo(codigo), timeout=10.0)
                    else:
                        resultado = await asyncio.wait_for(
                            asyncio.to_thread(metodo, codigo),
                            timeout=10.0
                        )
                else:
                    logger_rastreio.warning("rastreio_client não tem método conhecido, tentando rastreio_func")
                    if rastreio_func:
                        if asyncio.iscoroutinefunction(rastreio_func):
                            resultado = await asyncio.wait_for(rastreio_func(codigo), timeout=10.0)
                        else:
                            resultado = await asyncio.wait_for(
                                asyncio.to_thread(rastreio_func, codigo),
                                timeout=10.0
                            )
                    else:
                        return None, "❌ Método de rastreamento não encontrado"
            elif rastreio_func:
                # Usar função diretamente
                logger_rastreio.info("Usando rastreio_func diretamente")
                if asyncio.iscoroutinefunction(rastreio_func):
                    logger_rastreio.info("rastreio_func é assíncrono, usando await")
                    resultado = await asyncio.wait_for(rastreio_func(codigo), timeout=10.0)
                else:
                    logger_rastreio.info("rastreio_func é síncrono, usando thread")
                    resultado = await asyncio.wait_for(
                        asyncio.to_thread(rastreio_func, codigo),
                        timeout=10.0
                    )
            else:
                return None, "❌ Biblioteca de rastreamento não configurada corretamente"
            
            if not resultado:
                return None, "❌ Nenhuma informação encontrada para este código."
            
            # Normalizar resultado para lista
            logger_rastreio.info(f"Resultado bruto: tipo={type(resultado)}")
            if isinstance(resultado, str):
                logger_rastreio.info(f"Conteúdo completo da string (primeiros 1000 chars): {resultado[:1000]}")
            else:
                logger_rastreio.info(f"Valor (primeiros 500 chars): {str(resultado)[:500]}")
            
            if isinstance(resultado, list):
                eventos = resultado
            elif isinstance(resultado, dict):
                # Se for dict, pode ter 'eventos' ou ser um evento único
                if 'eventos' in resultado:
                    eventos = resultado['eventos']
                elif 'evento' in resultado:
                    eventos = resultado['evento'] if isinstance(resultado['evento'], list) else [resultado['evento']]
                else:
                    eventos = [resultado]
            elif isinstance(resultado, str):
                # Se for string, verificar se é mensagem de erro
                resultado_lower = resultado.lower().strip()
                
                # Verificar mensagens de erro comuns
                mensagens_erro = [
                    'objeto não encontrado',
                    'não encontrado',
                    'código inválido',
                    'objeto não localizado',
                    'não localizado',
                    'erro',
                    'error'
                ]
                
                if any(msg in resultado_lower for msg in mensagens_erro):
                    logger_rastreio.warning(f"Biblioteca retornou mensagem de erro: {resultado}")
                    return None, f"❌ {resultado}"
                
                # Se for string, pode ser JSON que precisa ser parseado
                logger_rastreio.info(f"Biblioteca retornou string, tentando parsear como JSON: {resultado[:500]}")
                try:
                    import json
                    resultado_parsed = json.loads(resultado)
                    logger_rastreio.info(f"String parseada com sucesso: tipo={type(resultado_parsed)}")
                    # Recursivamente processar o resultado parseado
                    if isinstance(resultado_parsed, list):
                        eventos = resultado_parsed
                    elif isinstance(resultado_parsed, dict):
                        if 'eventos' in resultado_parsed:
                            eventos = resultado_parsed['eventos']
                        elif 'evento' in resultado_parsed:
                            eventos = resultado_parsed['evento'] if isinstance(resultado_parsed['evento'], list) else [resultado_parsed['evento']]
                        else:
                            eventos = [resultado_parsed]
                    else:
                        eventos = [resultado_parsed]
                except json.JSONDecodeError:
                    # Não é JSON, pode ser HTML ou texto
                    logger_rastreio.warning(f"String não é JSON válido: {resultado[:200]}")
                    if '<' in resultado and '>' in resultado:
                        return None, "❌ A biblioteca retornou HTML. Isso pode indicar um problema na biblioteca ou que o código não foi encontrado."
                    else:
                        # Se não é JSON nem HTML, pode ser mensagem de erro
                        # Tentar API JSON dos Correios como fallback
                        logger_rastreio.info(f"Biblioteca retornou mensagem de erro, tentando API JSON como fallback")
                        eventos_api, erro_api = await self.buscar_api_correios(codigo)
                        if eventos_api:
                            return eventos_api, None
                        return None, f"❌ {resultado}"
                except Exception as e:
                    logger_rastreio.error(f"Erro ao parsear string: {e}")
                    return None, f"❌ Erro ao processar resposta da biblioteca: {str(e)[:100]}"
            else:
                # Tentar acessar como objeto
                if hasattr(resultado, 'eventos'):
                    eventos = resultado.eventos
                elif hasattr(resultado, 'evento'):
                    eventos = resultado.evento if isinstance(resultado.evento, list) else [resultado.evento]
                elif hasattr(resultado, '__iter__') and not isinstance(resultado, (str, bytes)):
                    # Não iterar sobre strings
                    eventos = list(resultado)
                else:
                    eventos = [resultado]
            
            if not eventos or len(eventos) == 0:
                return None, "❌ Nenhuma informação encontrada para este código."
            
            # Log do resultado para diagnóstico
            logger_rastreio.info(f"Resultado recebido: tipo={type(resultado)}, tipo eventos={type(eventos)}, quantidade={len(eventos)}")
            if eventos and len(eventos) > 0:
                logger_rastreio.info(f"Primeiro evento: tipo={type(eventos[0])}, conteúdo completo={eventos[0]}")
                if isinstance(eventos[0], dict):
                    logger_rastreio.info(f"Chaves do primeiro evento: {list(eventos[0].keys())}")
                    # Logar todos os valores para diagnóstico
                    for key, value in eventos[0].items():
                        logger_rastreio.info(f"  {key}: {value} (tipo: {type(value)})")
                else:
                    # Se for objeto, logar atributos
                    attrs = [attr for attr in dir(eventos[0]) if not attr.startswith('_')]
                    logger_rastreio.info(f"Atributos do primeiro evento: {attrs}")
                    for attr in attrs[:10]:  # Primeiros 10 atributos
                        try:
                            value = getattr(eventos[0], attr)
                            if not callable(value):
                                logger_rastreio.info(f"  {attr}: {value} (tipo: {type(value)})")
                        except:
                            pass
            
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
                
                # Extrair dados do evento - tentar todas as formas possíveis
                data = None
                descricao = None
                local = None
                uf = None
                
                if isinstance(evento, dict):
                    # Tentar todas as chaves possíveis para data
                    for key in ['data', 'dataHora', 'timestamp', 'dtHrCriado', 'data_evento', 'date', 
                               'dataHoraCriado', 'criado_em', 'data_criacao', 'hora', 'time']:
                        if key in evento and evento[key]:
                            data = evento[key]
                            break
                    
                    # Tentar todas as chaves possíveis para descrição
                    for key in ['status', 'descricao', 'evento', 'tipo', 'mensagem', 'texto', 
                               'observacao', 'detalhes', 'situacao', 'status_descricao']:
                        if key in evento and evento[key]:
                            descricao = evento[key]
                            break
                    
                    # Tentar extrair local e UF
                    # Primeiro tentar direto
                    for key in ['local', 'cidade', 'origem', 'destino']:
                        if key in evento and evento[key]:
                            local = evento[key]
                            break
                    
                    for key in ['uf', 'estado', 'estado_uf']:
                        if key in evento and evento[key]:
                            uf = evento[key]
                            break
                    
                    # Tentar estrutura aninhada
                    if not local and 'unidade' in evento:
                        unidade = evento['unidade']
                        if isinstance(unidade, dict):
                            if 'endereco' in unidade:
                                endereco = unidade['endereco']
                                if isinstance(endereco, dict):
                                    local = endereco.get('cidade', '') or endereco.get('local', '')
                                    uf = endereco.get('uf', '') or endereco.get('estado', '')
                            else:
                                local = unidade.get('cidade', '') or unidade.get('local', '')
                                uf = unidade.get('uf', '') or unidade.get('estado', '')
                    
                    # Tentar estrutura com nome
                    if not local and 'nome' in evento:
                        nome = evento['nome']
                        if isinstance(nome, str) and ' - ' in nome:
                            partes = nome.split(' - ')
                            if len(partes) >= 2:
                                local = partes[0].strip()
                                uf = partes[1].strip() if len(partes) > 1 else ''
                else:
                    # Tentar múltiplos atributos possíveis
                    for attr in ['data', 'dataHora', 'timestamp', 'dtHrCriado', 'data_evento', 'date']:
                        if hasattr(evento, attr):
                            value = getattr(evento, attr)
                            if value:
                                data = value
                                break
                    
                    for attr in ['descricao', 'status', 'evento', 'tipo', 'mensagem', 'texto']:
                        if hasattr(evento, attr):
                            value = getattr(evento, attr)
                            if value:
                                descricao = value
                                break
                    
                    for attr in ['local', 'cidade', 'origem']:
                        if hasattr(evento, attr):
                            value = getattr(evento, attr)
                            if value:
                                local = value
                                break
                    
                    for attr in ['uf', 'estado']:
                        if hasattr(evento, attr):
                            value = getattr(evento, attr)
                            if value:
                                uf = value
                                break
                
                # Se ainda não encontrou, tentar converter objeto para dict
                if not data and not isinstance(evento, dict):
                    try:
                        evento_dict = dict(evento.__dict__) if hasattr(evento, '__dict__') else {}
                        if evento_dict:
                            for key in ['data', 'dataHora', 'timestamp', 'dtHrCriado']:
                                if key in evento_dict and evento_dict[key]:
                                    data = evento_dict[key]
                                    break
                            for key in ['descricao', 'status', 'evento', 'tipo']:
                                if key in evento_dict and evento_dict[key]:
                                    descricao = evento_dict[key]
                                    break
                    except:
                        pass
                
                # Log dos valores extraídos
                logger_rastreio.info(f"Evento {i} extraído: data={data} (tipo: {type(data)}), descricao={descricao} (tipo: {type(descricao)}), local={local}, uf={uf}")
                
                # Formatar data
                if data and data != 'N/A' and data is not None:
                    if isinstance(data, str):
                        # Se for string, tentar formatar se necessário
                        data_formatada = data
                    elif hasattr(data, 'strftime'):
                        # Se for datetime
                        try:
                            data_formatada = data.strftime("%d/%m/%Y %H:%M")
                        except:
                            data_formatada = str(data)
                    else:
                        # Tentar converter para string
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
                if not descricao or descricao == 'N/A' or descricao is None:
                    # Se não encontrou descrição, tentar usar o evento inteiro como string
                    if isinstance(evento, dict):
                        # Tentar criar descrição a partir de todas as chaves
                        desc_parts = []
                        for key, value in evento.items():
                            if key not in ['data', 'dataHora', 'timestamp', 'local', 'cidade', 'uf', 'estado']:
                                if value and str(value).strip():
                                    desc_parts.append(f"{key}: {value}")
                        if desc_parts:
                            descricao = " | ".join(desc_parts[:3])  # Limitar a 3 partes
                        else:
                            descricao = "Informação não disponível"
                    else:
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
