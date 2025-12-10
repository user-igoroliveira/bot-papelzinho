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
        """Buscar produtos no site"""
        url = f"{self.base_url}/?s={termo}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status != 200:
                        return None
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    produtos = []
                    
                    # Buscar por elementos que contenham "Quantidade mínima"
                    # Isso é mais confiável para este site específico
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
                            produto_data = self.extrair_dados_produto(parent, soup)
                            if produto_data and produto_data.get('nome'):
                                # Evitar duplicatas
                                if not any(p.get('nome') == produto_data.get('nome') for p in produtos):
                                    produtos.append(produto_data)
                    
                    # Se não encontrou pelo método acima, tentar buscar por artigos ou divs
                    if not produtos:
                        product_selectors = [
                            'article',
                            '.product',
                            '.produto',
                            '.item',
                            'div[class*="product"]',
                            'div[class*="produto"]',
                            'div[class*="entry"]'
                        ]
                        
                        for selector in product_selectors:
                            items = soup.select(selector)
                            if items:
                                for item in items[:10]:
                                    produto_data = self.extrair_dados_produto(item, soup)
                                    if produto_data and produto_data.get('nome'):
                                        if not any(p.get('nome') == produto_data.get('nome') for p in produtos):
                                            produtos.append(produto_data)
                                if produtos:
                                    break
                    
                    return produtos[:3]  # Retornar apenas os 3 primeiros
                    
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            print(f"Erro ao buscar produtos: {e}")
            return None
    
    def extrair_dados_produto(self, elemento, soup):
        """Extrair dados de um produto do HTML"""
        produto = {}
        
        if not elemento:
            return None
        
        # Extrair nome do produto
        # Tentar diferentes seletores
        nome = None
        
        # Primeiro, tentar encontrar título/heading antes de "Quantidade mínima"
        texto_completo = elemento.get_text() if hasattr(elemento, 'get_text') else str(elemento)
        
        # Buscar por headings (h1, h2, h3, h4) no elemento
        for tag in ['h1', 'h2', 'h3', 'h4', 'h5']:
            heading = elemento.find(tag)
            if heading:
                nome = heading.get_text(strip=True)
                if nome and len(nome) > 3 and len(nome) < 100:
                    break
        
        # Se não encontrou, buscar por links ou títulos
        if not nome:
            link = elemento.find('a')
            if link:
                nome = link.get_text(strip=True)
                if not nome or len(nome) < 3:
                    # Tentar pegar do atributo title ou alt
                    nome = link.get('title') or link.get('alt') or ''
        
        # Se ainda não encontrou, pegar primeira linha significativa antes de "Quantidade mínima"
        if not nome or len(nome) < 3:
            linhas = texto_completo.split('\n')
            for linha in linhas:
                linha = linha.strip()
                # Ignorar linhas muito curtas ou muito longas, e que contenham palavras-chave
                if (linha and 3 < len(linha) < 100 and 
                    'Quantidade mínima' not in linha and 
                    'Prazo de confecção' not in linha and
                    'unidades' not in linha.lower() and
                    'dias' not in linha.lower()):
                    nome = linha
                    break
        
        produto['nome'] = nome if nome else "Produto sem nome"
        
        # Extrair quantidade mínima
        texto_completo = elemento.get_text() if hasattr(elemento, 'get_text') else str(elemento)
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
        
        # Extrair valor/preço
        # Tentar diferentes padrões de preço
        preco_patterns = [
            r'R\$\s*([\d.,]+)',
            r'valor[:\s]*R\$\s*([\d.,]+)',
            r'preço[:\s]*R\$\s*([\d.,]+)',
            r'(\d+[.,]\d{2})\s*reais',
        ]
        
        valor = None
        for pattern in preco_patterns:
            match = re.search(pattern, texto_completo, re.I)
            if match:
                valor = f"R$ {match.group(1)}"
                break
        
        produto['valor'] = valor if valor else "Consulte o site"
        
        return produto if produto.get('nome') else None
    
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
        
        # Buscar produtos
        produtos = await self.buscar_produtos(termo)
        
        if not produtos:
            await self.send_private_response(
                ctx,
                content=f"❌ Nenhum produto encontrado para o termo: **{termo}**\n\n"
                       "Tente usar outro termo de busca."
            )
            return
        
        # Criar embed com os resultados
        embed = discord.Embed(
            title=f"🔍 Resultados da busca: {termo}",
            description=f"Encontrados **{len(produtos)}** produto(s) no site PapeleEstilo:",
            color=discord.Color.blue(),
            url=f"{self.base_url}/?s={termo}"
        )
        
        for i, produto in enumerate(produtos, 1):
            field_value = (
                f"**Quantidade mínima:** {produto.get('quantidade_minima', 'Não informado')}\n"
                f"**Prazo de confecção:** {produto.get('prazo', 'Não informado')}\n"
                f"**Valor:** {produto.get('valor', 'Consulte o site')}"
            )
            
            embed.add_field(
                name=f"{i}. {produto.get('nome', 'Produto sem nome')}",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text=f"Site: papeleestilo.com.br | Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Site(bot))

