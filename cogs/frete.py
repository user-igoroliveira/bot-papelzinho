import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import re
import json

class Frete(commands.Cog):
    """Sistema de cálculo de frete dos Correios"""
    
    def __init__(self, bot):
        self.bot = bot
        # Dados do contrato
        self.usuario = "30351099000137"
        self.chave_acesso = "ynZh7glyZwJPjcowBWFKMM9jV8eD14BSrRjsTcHn"
        self.numero_contrato = "9912708847"
        self.numero_cartao_postagem = "0079422250"
        # Códigos dos serviços
        self.servicos = {
            "03050": "SEDEX CONTRATO AG CC",
            "03085": "PAC CONTRATO AG CC"
        }
        # Endpoints da API
        self.token_url = "https://api.correios.com.br/token/v1/autentica/contrato"
        self.calculo_url = "https://api.correios.com.br/calculador/v1/precoprazo"
        # Cache de token (válido por 1 hora)
        self.token_cache = None
        self.token_expires_at = None
    
    def validar_cep(self, cep):
        """Validar formato do CEP (apenas números, 8 dígitos)"""
        cep_limpo = re.sub(r'[^0-9]', '', cep)
        if len(cep_limpo) == 8:
            return cep_limpo
        return None
    
    async def obter_token(self):
        """Obter token de autenticação da API dos Correios"""
        # Verificar se o token ainda é válido (cache de 1 hora)
        if self.token_cache and self.token_expires_at:
            import time
            if time.time() < self.token_expires_at:
                return self.token_cache
        
        async with aiohttp.ClientSession() as session:
            payload = {
                "numero": self.numero_contrato,
                "senha": self.chave_acesso
            }
            
            try:
                async with session.post(
                    self.token_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        token = data.get("token")
                        if token:
                            # Cache do token por 1 hora (3600 segundos)
                            import time
                            self.token_cache = token
                            self.token_expires_at = time.time() + 3600
                            return token
                    else:
                        error_text = await response.text()
                        print(f"Erro ao obter token: {response.status} - {error_text}")
                        return None
            except Exception as e:
                print(f"Exceção ao obter token: {e}")
                return None
    
    async def calcular_frete(self, cep_origem, cep_destino, comprimento, largura, altura, peso=1.0):
        """Calcular frete usando a API dos Correios"""
        token = await self.obter_token()
        if not token:
            return None, "❌ Erro ao autenticar na API dos Correios. Tente novamente mais tarde."
        
        async with aiohttp.ClientSession() as session:
            payload = {
                "codigoServico": list(self.servicos.keys()),
                "cepOrigem": cep_origem,
                "cepDestino": cep_destino,
                "peso": str(peso),
                "comprimento": str(comprimento),
                "altura": str(altura),
                "largura": str(largura),
                "codigoEmpresa": self.usuario,
                "numeroContrato": self.numero_contrato,
                "numeroCartaoPostagem": self.numero_cartao_postagem
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
            
            try:
                async with session.post(
                    self.calculo_url,
                    json=payload,
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data, None
                    else:
                        error_text = await response.text()
                        try:
                            error_json = await response.json()
                            error_msg = error_json.get("mensagem", error_text)
                        except:
                            error_msg = error_text
                        return None, f"❌ Erro na API dos Correios: {error_msg}"
            except Exception as e:
                return None, f"❌ Erro ao calcular frete: {str(e)}"
    
    def parsear_medida(self, texto):
        """Extrair medida numérica de um texto (em cm)"""
        # Remover espaços e converter para minúsculas
        texto = texto.strip().lower()
        
        # Remover unidades comuns (cm, m, etc)
        texto = re.sub(r'\s*(cm|centimetros?|metros?|m)\s*', '', texto)
        
        # Extrair apenas números
        numeros = re.findall(r'\d+\.?\d*', texto)
        if numeros:
            try:
                valor = float(numeros[0])
                # Se o texto contém "m" ou "metro", converter para cm
                if 'm' in texto and 'cm' not in texto and 'centimetro' not in texto:
                    valor = valor * 100
                return int(valor)
            except:
                return None
        return None
    
    def parsear_peso(self, texto):
        """Extrair peso numérico de um texto (em kg)"""
        # Remover espaços e converter para minúsculas
        texto = texto.strip().lower()
        
        # Remover unidades comuns (kg, g, etc)
        texto_original = texto
        texto = re.sub(r'\s*(kg|quilogramas?|quilos?|g|gramas?)\s*', '', texto)
        
        # Extrair apenas números
        numeros = re.findall(r'\d+\.?\d*', texto)
        if numeros:
            try:
                valor = float(numeros[0])
                # Se o texto contém "g" ou "grama", converter para kg
                if 'g' in texto_original and 'kg' not in texto_original and 'quilo' not in texto_original:
                    valor = valor / 1000
                return valor
            except:
                return None
        return None
    
    async def perguntar_valor(self, ctx, pergunta, obrigatorio=False, valor_padrao=None):
        """Fazer uma pergunta ao usuário e esperar resposta"""
        if ctx.interaction:
            # Para slash commands, usar followup
            await ctx.interaction.followup.send(pergunta, ephemeral=True)
        else:
            # Para prefix commands, enviar no canal
            await ctx.send(pergunta)
        
        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel
        
        try:
            resposta = await self.bot.wait_for('message', check=check, timeout=120.0)
            texto = resposta.content.strip()
            
            if not texto and obrigatorio:
                return None, "❌ Este campo é obrigatório!"
            
            if not texto and valor_padrao is not None:
                return valor_padrao, None
            
            return texto, None
        except asyncio.TimeoutError:
            return None, "⏰ Tempo esgotado! Use o comando novamente."
    
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
    
    @commands.hybrid_command(name='frete', aliases=['calcularfrete'])
    @app_commands.describe(
        comprimento='Comprimento do item em cm (padrão: 50cm)',
        largura='Largura do item em cm (padrão: 40cm)',
        altura='Altura do item em cm (padrão: 30cm)',
        peso='Peso do item em kg (padrão: 1kg)',
        cep_origem='CEP de origem (obrigatório)',
        cep_destino='CEP de destino (obrigatório)'
    )
    async def frete(
        self,
        ctx,
        comprimento: str = None,
        largura: str = None,
        altura: str = None,
        peso: str = None,
        cep_origem: str = None,
        cep_destino: str = None
    ):
        """Calcular o custo do frete dos Correios (SEDEX e PAC)"""
        
        # Iniciar resposta
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Valores padrão
        comprimento_val = 50
        largura_val = 40
        altura_val = 30
        peso_val = 1.0
        
        # Pergunta 1: Comprimento
        if not comprimento:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "📏 **Qual o comprimento do item em centímetros?**\n"
                "Digite apenas o número (ex: 50) ou pressione Enter para usar 50cm como padrão.\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=False,
                valor_padrao="50"
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            comprimento = resposta
        
        # Parsear comprimento
        if comprimento:
            comprimento_parseado = self.parsear_medida(comprimento)
            if comprimento_parseado:
                comprimento_val = comprimento_parseado
        
        # Pergunta 2: Largura
        if not largura:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "📏 **Qual a largura do item em centímetros?**\n"
                "Digite apenas o número (ex: 40) ou pressione Enter para usar 40cm como padrão.\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=False,
                valor_padrao="40"
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            largura = resposta
        
        # Parsear largura
        if largura:
            largura_parseado = self.parsear_medida(largura)
            if largura_parseado:
                largura_val = largura_parseado
        
        # Pergunta 3: Altura
        if not altura:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "📏 **Qual a altura do item em centímetros?**\n"
                "Digite apenas o número (ex: 30) ou pressione Enter para usar 30cm como padrão.\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=False,
                valor_padrao="30"
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            altura = resposta
        
        # Parsear altura
        if altura:
            altura_parseado = self.parsear_medida(altura)
            if altura_parseado:
                altura_val = altura_parseado
        
        # Pergunta 4: Peso
        if not peso:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "⚖️ **Qual o peso do item em quilogramas?**\n"
                "Digite apenas o número (ex: 1.5) ou pressione Enter para usar 1kg como padrão.\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=False,
                valor_padrao="1"
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            peso = resposta
        
        # Parsear peso
        if peso:
            peso_parseado = self.parsear_peso(peso)
            if peso_parseado:
                peso_val = peso_parseado
        
        # Pergunta 5: CEP de Origem (obrigatório)
        if not cep_origem:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "📍 **Qual o CEP de origem?**\n"
                "Digite o CEP com ou sem hífen (ex: 01310-100 ou 01310100).\n"
                "Este campo é obrigatório!\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=True
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            cep_origem = resposta
        
        # Validar CEP de origem
        cep_origem_limpo = self.validar_cep(cep_origem)
        if not cep_origem_limpo:
            await self.send_private_response(
                ctx,
                content="❌ CEP de origem inválido! Digite um CEP válido com 8 dígitos."
            )
            return
        
        # Pergunta 6: CEP de Destino (obrigatório)
        if not cep_destino:
            resposta, erro = await self.perguntar_valor(
                ctx,
                "📍 **Qual o CEP de destino?**\n"
                "Digite o CEP com ou sem hífen (ex: 01310-100 ou 01310100).\n"
                "Este campo é obrigatório!\n"
                "Você tem 2 minutos para responder...",
                obrigatorio=True
            )
            if erro:
                await self.send_private_response(ctx, content=erro)
                return
            cep_destino = resposta
        
        # Validar CEP de destino
        cep_destino_limpo = self.validar_cep(cep_destino)
        if not cep_destino_limpo:
            await self.send_private_response(
                ctx,
                content="❌ CEP de destino inválido! Digite um CEP válido com 8 dígitos."
            )
            return
        
        # Mostrar mensagem de processamento
        await self.send_private_response(
            ctx,
            content=f"⏳ Calculando frete...\n\n"
                   f"**Dimensões:** {comprimento_val}cm x {largura_val}cm x {altura_val}cm\n"
                   f"**Peso:** {peso_val}kg\n"
                   f"**CEP Origem:** {cep_origem_limpo}\n"
                   f"**CEP Destino:** {cep_destino_limpo}"
        )
        
        # Calcular frete
        resultado, erro = await self.calcular_frete(
            cep_origem_limpo,
            cep_destino_limpo,
            comprimento_val,
            largura_val,
            altura_val,
            peso=peso_val
        )
        
        if erro:
            await self.send_private_response(ctx, content=erro)
            return
        
        # Processar resultados
        if not resultado or not isinstance(resultado, list):
            await self.send_private_response(
                ctx,
                content="❌ Não foi possível obter os valores de frete. Tente novamente."
            )
            return
        
        # Criar embed com os resultados
        embed = discord.Embed(
            title="📦 Cálculo de Frete - Correios",
            description=f"**Dimensões:** {comprimento_val}cm x {largura_val}cm x {altura_val}cm\n"
                       f"**Peso:** {peso_val}kg\n"
                       f"**CEP Origem:** {cep_origem_limpo}\n"
                       f"**CEP Destino:** {cep_destino_limpo}",
            color=discord.Color.blue()
        )
        
        resultados_encontrados = False
        for servico_data in resultado:
            codigo_servico = servico_data.get("codigo")
            nome_servico = self.servicos.get(codigo_servico, f"Serviço {codigo_servico}")
            
            valor = servico_data.get("valor")
            prazo = servico_data.get("prazoEntrega")
            erro_servico = servico_data.get("erro")
            msg_erro = servico_data.get("msgErro")
            
            if erro_servico or msg_erro:
                embed.add_field(
                    name=f"❌ {nome_servico}",
                    value=f"Erro: {msg_erro or 'Erro desconhecido'}",
                    inline=False
                )
            elif valor and prazo:
                resultados_encontrados = True
                # Formatar valor (assumindo que vem como string ou número)
                try:
                    valor_float = float(valor)
                    valor_formatado = f"R$ {valor_float:.2f}".replace(".", ",")
                except:
                    valor_formatado = str(valor)
                
                embed.add_field(
                    name=f"✅ {nome_servico}",
                    value=f"**Valor:** {valor_formatado}\n**Prazo:** {prazo} dia(s)",
                    inline=False
                )
        
        if not resultados_encontrados:
            embed.add_field(
                name="⚠️ Atenção",
                value="Nenhum serviço retornou valores válidos. Verifique os dados informados.",
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Frete(bot))

