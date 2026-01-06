import discord
from discord.ext import commands
from discord import app_commands
import re
import asyncio
import random
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
        # Credenciais da API Linketrack
        self.linketrack_api_key = "RZurnRHdoH-u_GwnOUSHdpjDOp-ip8cKOx_qhpUc07w"
        self.linketrack_url = "https://api.linketrack.com/track/json"
        # Credenciais da API CWS dos Correios
        self.usuario = "30351099000137"
        self.chave_acesso = "gqVdGY2caLooqdqpuDMXh3Mclmw6jYGL5FiErWGN"
        self.numero_contrato = "9912708847"
        self.numero_cartao_postagem = "0079422250"
        # Endpoints da API CWS
        self.token_url = "https://api.correios.com.br/token/v1/autentica/contrato"
        # Endpoint de rastreamento CWS (pode variar, tentaremos diferentes formatos)
        self.rastreio_url_base = "https://api.correios.com.br"
        # Cache de token (válido por 1 hora)
        self.token_cache = None
        self.token_expires_at = None
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
        if not codigo:
            return False
        codigo = codigo.upper().strip()
        # Formato padrão: 2 letras + 9 dígitos + 2 letras (ex: YO065460434BR)
        # Ou 13 caracteres alfanuméricos
        pattern = r'^[A-Z]{2}\d{9}[A-Z]{2}$|^[A-Z0-9]{13}$'
        return bool(re.match(pattern, codigo))
    
    async def obter_token_cws(self):
        """Obter token de autenticação da API CWS dos Correios"""
        import time
        
        # Verificar se o token ainda é válido (cache de 1 hora)
        if self.token_cache and self.token_expires_at:
            if time.time() < self.token_expires_at:
                logger_rastreio.debug("Token CWS em cache ainda válido, reutilizando")
                return self.token_cache
        
        logger_rastreio.info(f"Obtendo novo token CWS - URL: {self.token_url}")
        logger_rastreio.info(f"Contrato: {self.numero_contrato}")
        
        # Usar Basic Authentication conforme especificado pela API CWS
        import base64
        credentials = f"{self.usuario}:{self.chave_acesso}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        
        timeout = aiohttp.ClientTimeout(total=20)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # A API CWS espera apenas 'numero' no body, a senha vai no Basic Auth
            payload = {
                "numero": self.numero_contrato
            }
            
            try:
                logger_rastreio.debug(f"Payload de autenticação CWS: {{'numero': '{self.numero_contrato}'}}")
                
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Basic {encoded_credentials}"
                }
                
                async with session.post(
                    self.token_url,
                    json=payload,
                    headers=headers
                ) as response:
                    logger_rastreio.info(f"Resposta da API de token CWS - Status: {response.status}")
                    
                    # A API CWS retorna 201 (Created) quando o token é gerado com sucesso
                    if response.status in [200, 201]:
                        try:
                            data = await response.json()
                            logger_rastreio.debug(f"JSON recebido: {json.dumps(data, indent=2)}")
                            token = data.get("token")
                            if token:
                                # Usar expiraEm da resposta se disponível, senão cache por 1 hora
                                if "expiraEm" in data:
                                    try:
                                        # Converter expiraEm para timestamp
                                        expira_str = data["expiraEm"]
                                        expira_dt = datetime.fromisoformat(expira_str.replace('Z', '+00:00'))
                                        self.token_expires_at = expira_dt.timestamp()
                                    except Exception as e:
                                        logger_rastreio.warning(f"Erro ao converter expiraEm: {e}, usando cache padrão de 1 hora")
                                        # Se falhar, usar 1 hora padrão
                                        self.token_expires_at = time.time() + 3600
                                else:
                                    # Cache do token por 1 hora (3600 segundos) se não tiver expiraEm
                                    self.token_expires_at = time.time() + 3600
                                
                                self.token_cache = token
                                logger_rastreio.info("Token CWS obtido com sucesso e armazenado em cache")
                                return token
                            else:
                                logger_rastreio.error(f"Token não encontrado na resposta CWS: {data}")
                                return None
                        except json.JSONDecodeError as e:
                            response_text = await response.text()
                            logger_rastreio.error(f"Erro ao decodificar JSON da resposta CWS: {e} - Resposta: {response_text[:500]}")
                            return None
                    else:
                        response_text = await response.text()
                        logger_rastreio.error(f"Erro HTTP ao obter token CWS: {response.status} - {response_text[:500]}")
                        return None
            except aiohttp.ClientError as e:
                logger_rastreio.error(f"Erro de conexão ao obter token CWS: {e}")
                return None
            except Exception as e:
                logger_rastreio.error(f"Exceção ao obter token CWS: {e}", exc_info=True)
                return None
    
    async def buscar_api_correios_cws(self, codigo: str):
        """Buscar rastreamento usando API CWS autenticada dos Correios"""
        # Obter token de autenticação
        token = await self.obter_token_cws()
        if not token:
            logger_rastreio.warning("Não foi possível obter token CWS, tentando método alternativo")
            return None, None  # Retornar None para tentar método alternativo
        
        # URLs da API CWS de rastreamento - tentar diferentes formatos
        # A API CWS pode não ter endpoint específico de rastreamento, usar endpoint público com autenticação
        urls_tentativas = [
            f"https://proxyapp.correios.com.br/v1/sro-rastro/{codigo}",  # Endpoint público com autenticação Bearer
            f"{self.rastreio_url_base}/sro/v1/rastro/{codigo}",  # Formato padrão CWS (pode não existir)
            f"{self.rastreio_url_base}/v1/sro-rastro/{codigo}",  # Formato alternativo
            f"{self.rastreio_url_base}/sro-rastro/v1/{codigo}",  # Outro formato possível
        ]
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        timeout = aiohttp.ClientTimeout(total=20)
        
        # Tentar cada URL até encontrar uma que funcione
        for url in urls_tentativas:
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url, headers=headers) as response:
                        logger_rastreio.debug(f"API CWS status: {response.status} para código {codigo} (URL: {url})")
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            # Verificar estrutura de resposta
                            if not data:
                                logger_rastreio.warning(f"API CWS retornou dados vazios para URL: {url}")
                                break  # Sair do async with e tentar próxima URL
                            
                            # Processar resposta da API CWS
                            # A estrutura pode variar, vamos tentar diferentes formatos
                            eventos = []
                            
                            # Tentar formato com 'objetos'
                            if 'objetos' in data and data['objetos']:
                                objeto = data['objetos'][0]
                                
                                # Verificar mensagem de erro
                                if 'mensagem' in objeto:
                                    mensagem = objeto['mensagem']
                                    if mensagem and mensagem.strip():
                                        logger_rastreio.info(f"API CWS retornou mensagem: {mensagem}")
                                        if any(palavra in mensagem.lower() for palavra in 
                                              ['não encontrado', 'não localizado', 'inexistente', 'objeto não encontrado']):
                                            return None, f"❌ {mensagem}"
                                
                                # Processar eventos
                                if 'eventos' in objeto and objeto['eventos']:
                                    for ev in objeto['eventos']:
                                        evento_formatado = self._extrair_dados_evento(ev)
                                        if evento_formatado:
                                            eventos.append(evento_formatado)
                            
                            # Tentar formato direto com eventos
                            elif 'eventos' in data and data['eventos']:
                                for ev in data['eventos']:
                                    evento_formatado = self._extrair_dados_evento(ev)
                                    if evento_formatado:
                                        eventos.append(evento_formatado)
                            
                            if eventos:
                                logger_rastreio.info(f"✅ API CWS retornou {len(eventos)} eventos (URL: {url})")
                                return eventos, None
                            else:
                                logger_rastreio.warning(f"API CWS retornou resposta mas sem eventos para URL: {url}")
                                break  # Sair do async with e tentar próxima URL
                        
                        elif response.status == 401:
                            # Token inválido ou expirado, limpar cache
                            logger_rastreio.warning(f"Token CWS inválido ou expirado para URL: {url}, limpando cache")
                            self.token_cache = None
                            self.token_expires_at = None
                            # Tentar obter novo token
                            token = await self.obter_token_cws()
                            if not token:
                                return None, None  # Se não conseguir token, tentar método alternativo
                            headers['Authorization'] = f'Bearer {token}'
                            break  # Sair e tentar novamente com novo token
                        
                        elif response.status == 403:
                            logger_rastreio.warning(f"API CWS retornou 403 para URL: {url}, tentando próxima URL...")
                            break  # Sair do async with e tentar próxima URL
                        
                        elif response.status == 404:
                            logger_rastreio.debug(f"API CWS retornou 404 para URL: {url}, tentando próxima URL...")
                            break  # Sair do async with e tentar próxima URL
                        
                        elif response.status == 503:
                            # Serviço inexistente - endpoint pode não estar disponível
                            try:
                                text = await response.text()
                                logger_rastreio.warning(f"API CWS retornou 503 (Serviço inexistente) para URL: {url}")
                                logger_rastreio.debug(f"Resposta: {text[:300]}")
                            except:
                                pass
                            break  # Sair do async with e tentar próxima URL
                        
                        else:
                            try:
                                text = await response.text()
                                logger_rastreio.warning(f"API CWS retornou status {response.status} para URL {url}: {text[:200]}")
                            except:
                                pass
                            break  # Sair do async with e tentar próxima URL
                            
            except asyncio.TimeoutError:
                logger_rastreio.warning(f"Timeout ao acessar API CWS URL: {url}")
                continue  # Tentar próxima URL
            except aiohttp.ClientError as e:
                logger_rastreio.warning(f"Erro de conexão na API CWS URL {url}: {e}")
                continue  # Tentar próxima URL
            except Exception as e:
                logger_rastreio.warning(f"Erro inesperado na API CWS URL {url}: {e}")
                continue  # Tentar próxima URL
        
        # Se chegou aqui, todas as URLs falharam
        logger_rastreio.warning("Todas as URLs da API CWS falharam, tentando método alternativo")
        return None, None  # Tentar método alternativo
    
    async def buscar_api_correios(self, codigo: str, max_retries: int = 3):
        """Buscar rastreamento usando API oficial dos Correios com retry automático"""
        # URL da API oficial dos Correios (endpoint público)
        url = f"https://proxyapp.correios.com.br/v1/sro-rastro/{codigo}"
        
        # Headers mais completos para simular navegador real
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': 'https://www.correios.com.br/',
            'Origin': 'https://www.correios.com.br',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        }
        
        # Configurar timeout
        timeout = aiohttp.ClientTimeout(total=20)
        
        for attempt in range(max_retries):
            try:
                # Criar uma nova sessão a cada tentativa para evitar "Session is closed"
                # Deixar o aiohttp gerenciar o connector automaticamente
                async with aiohttp.ClientSession(
                    timeout=timeout,
                    cookie_jar=aiohttp.CookieJar()
                ) as session:
                    # Primeira tentativa: fazer requisição prévia para obter cookies (apenas na primeira tentativa)
                    if attempt == 0:
                        try:
                            async with session.get(
                                'https://www.correios.com.br/',
                                headers=headers,
                                timeout=timeout
                            ) as pre_req:
                                await pre_req.read()  # Consumir resposta para obter cookies
                                logger_rastreio.debug("Cookies obtidos do site dos Correios")
                        except Exception as e:
                            logger_rastreio.debug(f"Não foi possível obter cookies prévios: {e}")
                            # Continuar mesmo sem cookies prévios
                    
                    # Fazer requisição principal
                    async with session.get(url, headers=headers, timeout=timeout) as response:
                        logger_rastreio.debug(f"API status: {response.status} para código {codigo} (tentativa {attempt + 1}/{max_retries})")
                        
                        if response.status == 200:
                            data = await response.json()
                            
                            # Verificar estrutura de resposta
                            if not data:
                                logger_rastreio.warning("API retornou dados vazios")
                                return None, "❌ Nenhuma informação encontrada na API dos Correios."
                            
                            if 'objetos' in data and data['objetos']:
                                objeto = data['objetos'][0]
                                
                                # Verificar mensagem de erro
                                if 'mensagem' in objeto:
                                    mensagem = objeto['mensagem']
                                    if mensagem and mensagem.strip():
                                        logger_rastreio.info(f"API retornou mensagem: {mensagem}")
                                        # Verificar se é um erro conhecido
                                        if any(palavra in mensagem.lower() for palavra in 
                                              ['não encontrado', 'não localizado', 'inexistente', 'objeto não encontrado']):
                                            return None, f"❌ {mensagem}"
                                
                                # Processar eventos
                                if 'eventos' in objeto and objeto['eventos']:
                                    eventos = []
                                    for ev in objeto['eventos']:
                                        # Extrair dados do evento de forma mais robusta
                                        evento_formatado = self._extrair_dados_evento(ev)
                                        if evento_formatado:
                                            eventos.append(evento_formatado)
                                    
                                    if eventos:
                                        logger_rastreio.info(f"✅ API retornou {len(eventos)} eventos")
                                        return eventos, None
                                    else:
                                        logger_rastreio.warning("API retornou lista de eventos vazia após formatação")
                                else:
                                    logger_rastreio.warning("API retornou objeto mas sem eventos")
                            
                            return None, "❌ Nenhum evento encontrado para este código de rastreamento."
                        
                        elif response.status == 403:
                            # Erro 403 - tentar novamente com backoff exponencial
                            # Consumir resposta antes de continuar
                            try:
                                await response.read()
                            except:
                                pass
                            
                            if attempt < max_retries - 1:
                                wait_time = (2 ** attempt) + random.uniform(0, 1)
                                logger_rastreio.warning(f"403 recebido, tentando novamente em {wait_time:.2f}s... (tentativa {attempt + 1}/{max_retries})")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                return None, "❌ Erro 403: Acesso negado pela API dos Correios. A API pode estar bloqueando requisições. Tente novamente mais tarde."
                        
                        else:
                            # Outros erros HTTP
                            try:
                                text = await response.text()
                                logger_rastreio.warning(f"API retornou status {response.status}: {text[:200]}")
                            except:
                                pass
                            
                            # Tentar novamente apenas para erros 5xx (erro do servidor)
                            if response.status >= 500 and attempt < max_retries - 1:
                                wait_time = (2 ** attempt) + random.uniform(0, 1)
                                logger_rastreio.warning(f"Erro {response.status} do servidor, tentando novamente em {wait_time:.2f}s...")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            return None, f"❌ Erro ao acessar API dos Correios (Status: {response.status})"
                            
            except asyncio.TimeoutError:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger_rastreio.warning(f"Timeout ao acessar API, tentando novamente em {wait_time:.2f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger_rastreio.warning("Timeout ao acessar API após todas as tentativas")
                    return None, "❌ Timeout ao buscar informações. Tente novamente."
            
            except aiohttp.ClientError as e:
                error_msg = str(e).lower()
                # Tratar especificamente o erro "Session is closed"
                if "session is closed" in error_msg or "connector is closed" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger_rastreio.warning(f"Sessão fechada, criando nova sessão em {wait_time:.2f}s... (tentativa {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger_rastreio.error(f"Erro de sessão após todas as tentativas: {e}", exc_info=True)
                        return None, "❌ Erro ao manter conexão com a API. Tente novamente."
                
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) + random.uniform(0, 1)
                    logger_rastreio.warning(f"Erro de conexão: {e}, tentando novamente em {wait_time:.2f}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger_rastreio.error(f"Erro de conexão após todas as tentativas: {e}", exc_info=True)
                    return None, "❌ Erro de conexão ao buscar informações."
            
            except Exception as e:
                error_msg = str(e).lower()
                # Tratar especificamente o erro "Session is closed" mesmo em exceções genéricas
                if "session is closed" in error_msg or "connector is closed" in error_msg:
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logger_rastreio.warning(f"Sessão fechada, criando nova sessão em {wait_time:.2f}s... (tentativa {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger_rastreio.error(f"Erro de sessão após todas as tentativas: {e}", exc_info=True)
                        return None, "❌ Erro ao manter conexão com a API. Tente novamente."
                
                logger_rastreio.error(f"Erro inesperado: {e}", exc_info=True)
                return None, f"❌ Erro ao buscar na API: {str(e)[:100]}"
        
        # Se chegou aqui, todas as tentativas falharam
        return None, "❌ Não foi possível acessar a API dos Correios após várias tentativas."
    
    async def buscar_api_linketrack(self, codigo: str):
        """Buscar rastreamento usando API do Linketrack"""
        try:
            logger_rastreio.info(f"Tentando buscar com Linketrack para código: {codigo}")
            
            # URL da API Linketrack - tentar diferentes formatos
            # Formato 1: GET com código na URL e token no header
            url_get = f"{self.linketrack_url}?user={self.linketrack_api_key}&codigo={codigo}"
            # Formato 2: POST com JSON
            url_post = f"{self.linketrack_url}"
            
            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'token': self.linketrack_api_key
            }
            
            payload = {
                'codigo': codigo,
                'user': self.linketrack_api_key
            }
            
            timeout = aiohttp.ClientTimeout(total=20)
            
            # Tentar primeiro com GET
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url_get, headers=headers) as response:
                    logger_rastreio.debug(f"Linketrack GET status: {response.status} para código {codigo}")
                    
                    if response.status == 200:
                        data = await response.json()
                        eventos = self._processar_resposta_linketrack(data)
                        if eventos:
                            logger_rastreio.info(f"✅ Linketrack retornou {len(eventos)} eventos (GET)")
                            return eventos, None
                
                # Se GET não funcionou, tentar POST
                async with session.post(url_post, json=payload, headers=headers) as response:
                    logger_rastreio.debug(f"Linketrack POST status: {response.status} para código {codigo}")
                    
                    if response.status == 200:
                        data = await response.json()
                        eventos = self._processar_resposta_linketrack(data)
                        if eventos:
                            logger_rastreio.info(f"✅ Linketrack retornou {len(eventos)} eventos (POST)")
                            return eventos, None
                        else:
                            logger_rastreio.warning("Linketrack retornou resposta mas sem eventos")
                            return None, "❌ Nenhum evento encontrado para este código de rastreamento."
                    
                    elif response.status == 401 or response.status == 403:
                        logger_rastreio.warning(f"Linketrack retornou {response.status} - Chave de API inválida ou sem permissão")
                        return None, None  # Tentar método alternativo
                    
                    else:
                        try:
                            text = await response.text()
                            logger_rastreio.warning(f"Linketrack retornou status {response.status}: {text[:200]}")
                        except:
                            pass
                        return None, None  # Tentar método alternativo
                        
        except asyncio.TimeoutError:
            logger_rastreio.warning("Timeout ao acessar API Linketrack")
            return None, None  # Tentar método alternativo
        except aiohttp.ClientError as e:
            logger_rastreio.error(f"Erro de conexão na API Linketrack: {e}", exc_info=True)
            return None, None  # Tentar método alternativo
        except Exception as e:
            logger_rastreio.error(f"Erro inesperado na API Linketrack: {e}", exc_info=True)
            return None, None  # Tentar método alternativo
    
    def _processar_resposta_linketrack(self, data) -> list:
        """Processar resposta da API Linketrack e extrair eventos"""
        if not data:
            logger_rastreio.warning("Linketrack retornou dados vazios")
            return []
        
        eventos = []
        
        # Linketrack geralmente retorna eventos em formato de lista
        if isinstance(data, list):
            for ev in data:
                evento_formatado = self._extrair_dados_evento_linketrack(ev)
                if evento_formatado:
                    eventos.append(evento_formatado)
        elif isinstance(data, dict):
            # Tentar diferentes estruturas possíveis
            if 'eventos' in data:
                for ev in data['eventos']:
                    evento_formatado = self._extrair_dados_evento_linketrack(ev)
                    if evento_formatado:
                        eventos.append(evento_formatado)
            elif 'tracking' in data and isinstance(data['tracking'], list):
                for ev in data['tracking']:
                    evento_formatado = self._extrair_dados_evento_linketrack(ev)
                    if evento_formatado:
                        eventos.append(evento_formatado)
            elif 'data' in data and isinstance(data['data'], list):
                for ev in data['data']:
                    evento_formatado = self._extrair_dados_evento_linketrack(ev)
                    if evento_formatado:
                        eventos.append(evento_formatado)
            elif 'events' in data and isinstance(data['events'], list):
                for ev in data['events']:
                    evento_formatado = self._extrair_dados_evento_linketrack(ev)
                    if evento_formatado:
                        eventos.append(evento_formatado)
            else:
                # Tentar processar como evento único
                evento_formatado = self._extrair_dados_evento_linketrack(data)
                if evento_formatado:
                    eventos.append(evento_formatado)
        
        return eventos
    
    def _extrair_dados_evento_linketrack(self, ev: dict) -> dict:
        """Extrair dados de um evento do Linketrack"""
        # Linketrack pode ter diferentes formatos, tentar extrair de forma flexível
        data = ev.get('data') or ev.get('date') or ev.get('dtHrCriado') or ev.get('dataHora') or ''
        descricao = ev.get('descricao') or ev.get('status') or ev.get('mensagem') or ev.get('evento') or 'Informação não disponível'
        local = ev.get('local') or ev.get('cidade') or ev.get('unidade') or ''
        uf = ev.get('uf') or ev.get('estado') or ''
        
        # Se local está em um objeto aninhado
        if isinstance(local, dict):
            local = local.get('nome', '') or local.get('cidade', '')
        
        return {
            'data': data,
            'descricao': descricao,
            'local': local if isinstance(local, str) else '',
            'uf': uf if isinstance(uf, str) else ''
        }
    
    async def buscar_api_correios_pyrastreio(self, codigo: str):
        """Buscar rastreamento usando biblioteca pyrastreio"""
        try:
            from pyrastreio import correios
            
            logger_rastreio.info(f"Tentando buscar com pyrastreio para código: {codigo}")
            
            # Executar em thread separada pois pode não ser totalmente async
            loop = asyncio.get_event_loop()
            resultado = await loop.run_in_executor(
                None, 
                lambda: correios(codigo)
            )
            
            if resultado and isinstance(resultado, list) and len(resultado) > 0:
                eventos = []
                for ev in resultado:
                    # pyrastreio retorna dicts com: data, hora, local, mensagem
                    if isinstance(ev, dict):
                        # Formatar data e hora
                        data_str = ev.get('data', '')
                        hora_str = ev.get('hora', '')
                        if data_str and hora_str:
                            data_completa = f"{data_str} {hora_str}"
                        elif data_str:
                            data_completa = data_str
                        else:
                            data_completa = ''
                        
                        evento_formatado = {
                            'data': data_completa,
                            'descricao': ev.get('mensagem', ev.get('descricao', 'Informação não disponível')),
                            'local': ev.get('local', ''),
                            'uf': ev.get('uf', '')
                        }
                        eventos.append(evento_formatado)
                
                if eventos:
                    logger_rastreio.info(f"✅ pyrastreio retornou {len(eventos)} eventos")
                    return eventos, None
                else:
                    logger_rastreio.warning("pyrastreio retornou lista vazia após formatação")
                    return None, "❌ Nenhum evento encontrado para este código de rastreamento."
            else:
                logger_rastreio.warning("pyrastreio retornou resultado vazio")
                return None, "❌ Nenhum evento encontrado para este código de rastreamento."
                
        except ImportError:
            logger_rastreio.warning("pyrastreio não está instalado ou não pôde ser importado")
            return None, None  # Retornar None para tentar método alternativo
        except Exception as e:
            logger_rastreio.error(f"Erro ao buscar com pyrastreio: {e}", exc_info=True)
            return None, None  # Retornar None para tentar método alternativo
    
    def _extrair_dados_evento(self, ev: dict) -> dict:
        """Extrair dados de um evento de forma padronizada"""
        # Extrair data (prioridade: dtHrCriado > data > dataHora)
        data = ev.get('dtHrCriado') or ev.get('data') or ev.get('dataHora') or ''
        
        # Extrair descrição (prioridade: descricao > tipo > status)
        descricao = ev.get('descricao') or ev.get('tipo') or ev.get('status') or 'Informação não disponível'
        
        # Extrair local e UF
        cidade = ''
        uf = ''
        
        # Tentar extrair de unidade.endereco
        unidade = ev.get('unidade', {})
        if isinstance(unidade, dict):
            endereco = unidade.get('endereco', {})
            if isinstance(endereco, dict):
                cidade = endereco.get('cidade', '')
                uf = endereco.get('uf', '') or endereco.get('estado', '')
            # Se não tem endereco, tentar direto na unidade
            if not cidade:
                cidade = unidade.get('cidade', '')
                uf = unidade.get('uf', '') or unidade.get('estado', '')
        
        return {
            'data': data,
            'descricao': descricao,
            'local': cidade,
            'uf': uf
        }
    
    async def buscar_rastreio(self, codigo: str):
        """Buscar informações de rastreamento"""
        if not self.validar_codigo(codigo):
            return None, "❌ Código de rastreamento inválido! Use o formato: YO065460434BR"
        
        # Normalizar código (maiúsculas, sem espaços)
        codigo = codigo.upper().strip()
        
        logger_rastreio.info(f"Buscando rastreamento para código: {codigo}")
        
        # Método 1: Tentar primeiro com API Linketrack (método principal e mais confiável)
        eventos, erro = await self.buscar_api_linketrack(codigo)
        if eventos:
            logger_rastreio.info(f"✅ Encontrados {len(eventos)} eventos via Linketrack")
            return eventos, None
        
        # Método 2: Se Linketrack falhar, tentar pyrastreio
        if erro is None:  # erro None significa que Linketrack não está disponível ou falhou silenciosamente
            logger_rastreio.info("Linketrack não disponível ou falhou, tentando pyrastreio...")
            eventos, erro = await self.buscar_api_correios_pyrastreio(codigo)
            if eventos:
                logger_rastreio.info(f"✅ Encontrados {len(eventos)} eventos via pyrastreio")
                return eventos, None
        
        # Método 3: Se pyrastreio falhar, tentar API pública direta
        if erro is None:
            logger_rastreio.info("pyrastreio não disponível ou falhou, tentando API pública direta...")
            eventos, erro = await self.buscar_api_correios(codigo)
            if eventos:
                logger_rastreio.info(f"✅ Encontrados {len(eventos)} eventos via API pública direta")
                return eventos, None
        
        # Método 4: Como último recurso, tentar API CWS (pode não estar disponível)
        if erro is None:
            logger_rastreio.info("Tentando API CWS como último recurso...")
            eventos, erro = await self.buscar_api_correios_cws(codigo)
            if eventos:
                logger_rastreio.info(f"✅ Encontrados {len(eventos)} eventos via API CWS")
                return eventos, None
        
        return None, erro if erro else "❌ Não foi possível buscar informações de rastreamento."
    
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
        
        # Limpar código (remover espaços, hífens, etc)
        codigo_limpo = re.sub(r'[^A-Z0-9]', '', codigo.upper())
        
        # Validar código
        if not self.validar_codigo(codigo_limpo):
            await self.send_private_response(
                ctx,
                content=f"❌ Código de rastreamento inválido!\n\n"
                       f"Formato esperado: `YO065460434BR` (2 letras + 9 dígitos + 2 letras)\n"
                       f"Código informado: `{codigo}`"
            )
            return
        
        # Buscar informações
        eventos, erro = await self.buscar_rastreio(codigo_limpo)
        
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
        embed = discord.Embed(
            title=f"📦 Rastreamento - {codigo_limpo}",
            description=f"**{len(eventos)}** evento(s) encontrado(s):",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Formatar eventos (limitar a 10 mais recentes)
        eventos_formatados = []
        for i, evento in enumerate(eventos[:10], 1):
            try:
                # Formatar data
                data_str = evento.get('data', '')
                if data_str:
                    # Tentar formatar data se for ISO format
                    try:
                        if 'T' in data_str:
                            dt = datetime.fromisoformat(data_str.replace('Z', '+00:00'))
                            data_formatada = dt.strftime("%d/%m/%Y %H:%M")
                        else:
                            data_formatada = data_str
                    except:
                        data_formatada = data_str
                else:
                    data_formatada = "Data não disponível"
                
                # Formatar descrição
                descricao = evento.get('descricao', 'Informação não disponível')
                if len(descricao) > 200:
                    descricao = descricao[:197] + "..."
                
                # Formatar local
                local = evento.get('local', '')
                uf = evento.get('uf', '')
                if local and uf:
                    local_completo = f"{local}/{uf}"
                elif local:
                    local_completo = local
                elif uf:
                    local_completo = uf
                else:
                    local_completo = "Local não informado"
                
                # Montar texto do evento
                evento_texto = f"**{i}.** {data_formatada}\n{descricao}\n📍 {local_completo}"
                eventos_formatados.append(evento_texto)
                
            except Exception as e:
                logger_rastreio.error(f"Erro ao formatar evento {i}: {e}", exc_info=True)
                continue
        
        if not eventos_formatados:
            await self.send_private_response(
                ctx,
                content=f"❌ Erro ao processar eventos do código: **{codigo_limpo}**"
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
