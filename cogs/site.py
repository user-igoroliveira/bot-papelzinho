import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from bs4 import BeautifulSoup
import re
import asyncio

class Site(commands.Cog):
    """Sistema de busca no site PapeleEstilo"""
    
    def __init__(self, bot):
        self.bot = bot
        self.base_url = "https://papeleestilo.com.br"
    
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
    
    async def buscar_produtos(self, termo):
        """Buscar produtos no site e extrair links"""
        url = f"{self.base_url}/?s={termo}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    produtos_links = []
                    
                    # Buscar por elementos que contenham "Quantidade mínima"
                    qtd_elements = soup.find_all(string=re.compile(r'Quantidade mínima', re.I))
                    
                    for qtd_text in qtd_elements[:10]:  # Limitar para performance
                        # Encontrar o elemento pai que contém todas as informações
                        parent = qtd_text.find_parent()
                        
                        # Subir alguns níveis para pegar o container completo do produto
                        for _ in range(3):
                            if parent:
                                parent = parent.find_parent()
                            else:
                                break
                        
                        if parent:
                            # Extrair nome e link do produto
                            nome = None
                            link = None
                            
                            # Buscar por headings
                            for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
                                heading = parent.find(tag)
                                if heading:
                                    nome = heading.get_text(strip=True)
                                    # Tentar pegar link do heading
                                    link_elem = heading.find('a')
                                    if link_elem and link_elem.get('href'):
                                        link = link_elem.get('href')
                                    break
                            
                            # Se não encontrou, buscar por links
                            if not link:
                                link_elem = parent.find('a', href=re.compile(r'/produto/'))
                                if link_elem:
                                    link = link_elem.get('href')
                                    if not nome:
                                        nome = link_elem.get_text(strip=True)
                            
                            # Se ainda não tem nome, tentar extrair do texto
                            if not nome:
                                texto = parent.get_text() if hasattr(parent, 'get_text') else str(parent)
                                linhas = texto.split('\n')
                                for linha in linhas:
                                    linha = linha.strip()
                                    if (linha and 3 < len(linha) < 100 and 
                                        'Quantidade mínima' not in linha and 
                                        'Prazo de confecção' not in linha and
                                        'unidades' not in linha.lower() and
                                        'dias' not in linha.lower()):
                                        nome = linha
                                        break
                            
                            if nome and link:
                                # Normalizar link
                                if not link.startswith('http'):
                                    if link.startswith('/'):
                                        link = f"{self.base_url}{link}"
                                    else:
                                        link = f"{self.base_url}/{link}"
                                
                                # Evitar duplicatas
                                if not any(p.get('link') == link for p in produtos_links):
                                    produtos_links.append({
                                        'nome': nome,
                                        'link': link
                                    })
                    
                    # Se não encontrou pelo método acima, tentar buscar por links diretos
                    if not produtos_links:
                        links = soup.find_all('a', href=re.compile(r'/produto/'))
                        for link_elem in links[:10]:
                            link = link_elem.get('href')
                            nome = link_elem.get_text(strip=True)
                            
                            if link and nome and len(nome) > 3:
                                if not link.startswith('http'):
                                    if link.startswith('/'):
                                        link = f"{self.base_url}{link}"
                                    else:
                                        link = f"{self.base_url}/{link}"
                                
                                if not any(p.get('link') == link for p in produtos_links):
                                    produtos_links.append({
                                        'nome': nome,
                                        'link': link
                                    })
                    
                    # Retornar apenas os 3 primeiros
                    return produtos_links[:3]
                    
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            print(f"Erro ao buscar produtos: {e}")
            return None
    
    async def buscar_detalhes_produto(self, link_produto):
        """Buscar detalhes completos de um produto acessando sua página"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(link_produto, headers=headers, timeout=15) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    produto = {}
                    
                    # Extrair nome do produto (h1 geralmente contém o nome)
                    h1 = soup.find('h1')
                    if h1:
                        produto['nome'] = h1.get_text(strip=True)
                    
                    # Extrair quantidade mínima
                    texto_completo = soup.get_text()
                    qtd_match = re.search(r'Quantidade mínima[:\s]*(\d+)', texto_completo, re.I)
                    if qtd_match:
                        produto['quantidade_minima'] = f"{qtd_match.group(1)} unidades"
                    else:
                        produto['quantidade_minima'] = "Não informado"
                    
                    # Extrair prazo de confecção
                    prazo_match = re.search(r'Prazo de confecção[:\s]*([^\.]+)', texto_completo, re.I)
                    if prazo_match:
                        produto['prazo'] = prazo_match.group(1).strip()
                    else:
                        produto['prazo'] = "Não informado"
                    
                    # Extrair preços (atual e original)
                    # Padrão: ~~R$ 28,60~~ (original) e R$ 27,15 (atual)
                    preco_original = None
                    preco_atual = None
                    
                    # Buscar por padrão de preço riscado (original)
                    preco_riscado = soup.find(string=re.compile(r'R\$\s*[\d.,]+'))
                    if preco_riscado:
                        parent = preco_riscado.find_parent()
                        if parent and parent.name in ['del', 's', 'strike']:
                            match = re.search(r'R\$\s*([\d.,]+)', preco_riscado, re.I)
                            if match:
                                preco_original = f"R$ {match.group(1)}"
                    
                    # Buscar preço atual (geralmente após o preço riscado)
                    # Procurar por "O preço atual é: R$ X"
                    preco_atual_match = re.search(r'O preço atual é[:\s]*R\$\s*([\d.,]+)', texto_completo, re.I)
                    if preco_atual_match:
                        preco_atual = f"R$ {preco_atual_match.group(1)}"
                    else:
                        # Tentar encontrar preço que não está riscado
                        preco_elem = soup.find('span', class_=re.compile(r'price|preco', re.I))
                        if preco_elem:
                            preco_text = preco_elem.get_text()
                            match = re.search(r'R\$\s*([\d.,]+)', preco_text, re.I)
                            if match:
                                preco_atual = f"R$ {match.group(1)}"
                        else:
                            # Última tentativa: buscar qualquer R$ que não esteja riscado
                            precos = re.findall(r'R\$\s*([\d.,]+)', texto_completo, re.I)
                            if precos:
                                # Pegar o último (geralmente é o atual)
                                preco_atual = f"R$ {precos[-1]}"
                    
                    # Montar string de valor
                    if preco_atual:
                        if preco_original:
                            produto['valor'] = f"{preco_atual} (era {preco_original})"
                        else:
                            produto['valor'] = preco_atual
                    else:
                        produto['valor'] = "Consulte o site"
                    
                    produto['link'] = link_produto
                    
                    return produto
                    
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            print(f"Erro ao buscar detalhes do produto: {e}")
            return None
    
    
    @commands.hybrid_command(name='site', aliases=['buscar', 'pesquisar'])
    @app_commands.describe(termo='Termo de busca (ex: hmp, convite, casamento)')
    async def site(self, ctx, termo: str = None):
        """Buscar produtos no site PapeleEstilo"""
        
        if not termo:
            await self.send_private_response(
                ctx,
                content="🔍 **Busca no site PapeleEstilo**\n\n"
                       "Por favor, informe o termo de busca.\n"
                       "Exemplo: `/site hmp` ou `!site convite`"
            )
            return
        
        # Enviar mensagem de carregamento
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=True)
        
        # Buscar produtos (retorna links)
        produtos_links = await self.buscar_produtos(termo)
        
        if not produtos_links:
            await self.send_private_response(
                ctx,
                content=f"❌ Nenhum produto encontrado para o termo: **{termo}**\n\n"
                       "Tente usar outro termo de busca."
            )
            return
        
        # Buscar detalhes completos de cada produto (acessar páginas individuais)
        produtos_completos = []
        for produto_link in produtos_links:
            detalhes = await self.buscar_detalhes_produto(produto_link['link'])
            if detalhes:
                # Garantir que o nome está presente
                if not detalhes.get('nome'):
                    detalhes['nome'] = produto_link.get('nome', 'Produto sem nome')
                produtos_completos.append(detalhes)
        
        if not produtos_completos:
            await self.send_private_response(
                ctx,
                content=f"❌ Não foi possível obter detalhes dos produtos para o termo: **{termo}**\n\n"
                       "Tente novamente mais tarde."
            )
            return
        
        # Criar embed com os resultados
        embed = discord.Embed(
            title=f"🔍 Resultados da busca: {termo}",
            description=f"Encontrados **{len(produtos_completos)}** produto(s) no site PapeleEstilo:",
            color=discord.Color.blue(),
            url=f"{self.base_url}/?s={termo}"
        )
        
        for i, produto in enumerate(produtos_completos, 1):
            field_value = (
                f"**Quantidade mínima:** {produto.get('quantidade_minima', 'Não informado')}\n"
                f"**Prazo de confecção:** {produto.get('prazo', 'Não informado')}\n"
                f"**Valor:** {produto.get('valor', 'Consulte o site')}"
            )
            
            # Adicionar link se disponível
            if produto.get('link'):
                field_value += f"\n[Ver produto]({produto['link']})"
            
            embed.add_field(
                name=f"{i}. {produto.get('nome', 'Produto sem nome')}",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text=f"Site: papeleestilo.com.br | Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Site(bot))

