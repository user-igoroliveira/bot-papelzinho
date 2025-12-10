import discord
from discord.ext import commands
from discord import app_commands
import re
import os
import asyncio
from math import sqrt

class Caixas(commands.Cog):
    """Sistema de busca de caixas por medidas"""
    
    def __init__(self, bot):
        self.bot = bot
        self.caixas_file = 'caixas.txt'
        self.caixas_data = []
        self.load_caixas()
    
    def load_caixas(self):
        """Carregar dados das caixas do arquivo"""
        if not os.path.exists(self.caixas_file):
            return
        
        self.caixas_data = []
        
        with open(self.caixas_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Pular o cabeçalho (linha 1)
            for line in lines[1:]:
                line = line.strip()
                if not line or 'VAZIO' in line.upper():
                    continue
                
                # Dividir por tabulação
                parts = line.split('\t')
                if len(parts) < 2:
                    continue
                
                codigo = parts[0].strip()
                medida_interna = parts[1].strip()
                
                # Extrair medidas (formato: 90x150x70mm)
                medidas = self.parse_medidas(medida_interna)
                if medidas:
                    self.caixas_data.append({
                        'codigo': codigo,
                        'medida_interna': medida_interna,
                        'largura': medidas[0],
                        'comprimento': medidas[1],
                        'altura': medidas[2],
                        'medida_externa': parts[2].strip() if len(parts) > 2 else '-',
                        'aproveitamento': parts[3].strip() if len(parts) > 3 else '-'
                    })
    
    def parse_medidas(self, medida_str):
        """Extrair medidas numéricas de uma string (ex: '90x150x70mm' -> [90, 150, 70])"""
        # Remover espaços e 'mm'
        medida_str = medida_str.replace('mm', '').replace(' ', '').strip()
        
        # Procurar padrão numérico x numérico x numérico
        match = re.match(r'(\d+)x(\d+)x(\d+)', medida_str)
        if match:
            return [int(match.group(1)), int(match.group(2)), int(match.group(3))]
        
        return None
    
    def calculate_distance(self, medidas_usuario, medidas_caixa):
        """Calcular distância euclidiana entre as medidas"""
        # Considerar todas as combinações possíveis (permutações)
        # Largura x Comprimento x Altura pode ser organizada de diferentes formas
        usuario_l, usuario_c, usuario_a = medidas_usuario
        
        caixa_l, caixa_c, caixa_a = medidas_caixa
        
        # Calcular distância considerando que a caixa pode ser rotacionada
        # Testar todas as 6 permutações possíveis
        permutations = [
            (caixa_l, caixa_c, caixa_a),
            (caixa_l, caixa_a, caixa_c),
            (caixa_c, caixa_l, caixa_a),
            (caixa_c, caixa_a, caixa_l),
            (caixa_a, caixa_l, caixa_c),
            (caixa_a, caixa_c, caixa_l),
        ]
        
        min_distance = float('inf')
        
        for perm in permutations:
            # A caixa deve ser maior ou igual em todas as dimensões
            if perm[0] >= usuario_l and perm[1] >= usuario_c and perm[2] >= usuario_a:
                # Calcular distância euclidiana
                distance = sqrt(
                    (perm[0] - usuario_l) ** 2 +
                    (perm[1] - usuario_c) ** 2 +
                    (perm[2] - usuario_a) ** 2
                )
                min_distance = min(min_distance, distance)
        
        return min_distance if min_distance != float('inf') else None
    
    def find_best_caixas(self, largura, comprimento, altura):
        """Encontrar as 3 caixas mais próximas das medidas solicitadas"""
        medidas_usuario = [largura, comprimento, altura]
        
        resultados = []
        
        for caixa in self.caixas_data:
            medidas_caixa = [caixa['largura'], caixa['comprimento'], caixa['altura']]
            distance = self.calculate_distance(medidas_usuario, medidas_caixa)
            
            if distance is not None:
                resultados.append({
                    'caixa': caixa,
                    'distance': distance
                })
        
        # Ordenar por distância (menor primeiro)
        resultados.sort(key=lambda x: x['distance'])
        
        # Retornar as 3 melhores
        return resultados[:3]
    
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
    
    @commands.hybrid_command(name='caixas', aliases=['caixa', 'buscar'])
    @app_commands.describe(medidas='Medidas no formato LarguraxComprimentoxAltura (ex: 150x150x100)')
    async def caixas(self, ctx, medidas: str = None):
        """Buscar caixas por medidas aproximadas"""
        
        # Se não forneceu medidas, perguntar e esperar resposta
        if not medidas:
            await self.send_private_response(
                ctx,
                content="📦 **Qual a medida aproximada você precisa?**\n\n"
                       "Por favor, informe no formato: `LarguraxComprimentoxAltura`\n"
                       "Exemplo: `150x150x100`\n\n"
                       "Você tem 60 segundos para responder..."
            )
            
            # Esperar resposta do usuário (apenas para prefix commands)
            if not ctx.interaction:
                def check(message):
                    return message.author == ctx.author and message.channel == ctx.channel
                
                try:
                    resposta = await self.bot.wait_for('message', check=check, timeout=60.0)
                    medidas = resposta.content.strip()
                except asyncio.TimeoutError:
                    await ctx.send("⏰ Tempo esgotado! Use o comando novamente.", delete_after=10)
                    return
            else:
                # Para slash commands, informar que precisa fornecer as medidas
                return
        
        # Validar formato das medidas
        medidas_parseadas = self.parse_medidas(medidas)
        if not medidas_parseadas:
            await self.send_private_response(
                ctx,
                content="❌ Formato inválido! Use o formato: `LarguraxComprimentoxAltura`\n"
                       "Exemplo: `150x150x100`"
            )
            return
        
        largura, comprimento, altura = medidas_parseadas
        
        # Buscar as melhores caixas
        melhores_caixas = self.find_best_caixas(largura, comprimento, altura)
        
        if not melhores_caixas:
            await self.send_private_response(
                ctx,
                content=f"❌ Não foram encontradas caixas adequadas para as medidas: **{largura}x{comprimento}x{altura}mm**"
            )
            return
        
        # Criar embed com os resultados
        embed = discord.Embed(
            title=f"📦 Caixas Recomendadas - {largura}x{comprimento}x{altura}mm",
            description=f"Encontradas **{len(melhores_caixas)}** caixa(s) mais próxima(s) das suas medidas:",
            color=discord.Color.blue()
        )
        
        for i, resultado in enumerate(melhores_caixas, 1):
            caixa = resultado['caixa']
            
            field_value = (
                f"**Medida Interna:** {caixa['medida_interna']}\n"
                f"**Medida Externa:** {caixa['medida_externa']}\n"
                f"**Aproveitamento:** {caixa['aproveitamento']}"
            )
            
            embed.add_field(
                name=f"{i}. Código: {caixa['codigo']}",
                value=field_value,
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Caixas(bot))

