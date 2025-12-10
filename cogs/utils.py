import discord
from discord.ext import commands
from discord import app_commands
import platform
import psutil
from datetime import datetime

class Utils(commands.Cog):
    """Comandos utilitários do bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
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
    
    @commands.hybrid_command(name='ping', aliases=['latencia'])
    async def ping(self, ctx):
        """Verificar a latência do bot"""
        latency = round(self.bot.latency * 1000)
        
        embed = discord.Embed(
            title="🏓 Pong!",
            color=discord.Color.green()
        )
        embed.add_field(name="Latência", value=f"{latency}ms", inline=True)
        embed.add_field(name="Status", value="✅ Online", inline=True)
        
        await self.send_private_response(ctx, embed=embed)
    
    @commands.hybrid_command(name='info', aliases=['botinfo', 'sobre'])
    async def info(self, ctx):
        """Informações sobre o bot"""
        user_name = ctx.author.display_name or ctx.author.name
        
        description = f"""Olá, **{user_name}**,

Com um sorriso contagiante e seu boné estiloso, o Papelzinho não é apenas fofo, ele é uma verdadeira fonte de recursos. Desenvolvido para ser seu melhor amigo no Discord, ele está aqui para:

• **Fornecer Informações Necessárias**: Precisa de um lembrete rápido sobre um procedimento, a localização de um arquivo importante ou o horário de uma reunião? Pergunte ao Papelzinho!

• **Compartilhar Truques e Atalhos**: Descubra maneiras inteligentes de otimizar suas tarefas e aproveitar ao máximo as ferramentas que usamos. O Papelzinho tem sempre um truque na manga!

• **Trazer Novas Dicas**: Mantenha-se atualizado com as últimas novidades, melhores práticas e sacadas que podem fazer a diferença no seu dia a dia profissional.

Nosso objetivo é que o Papelzinho seja um assistente proativo e amigável, ajudando a simplificar processos, inovar em nossas rotinas e fortalecer ainda mais nossa colaboração. Ele está sempre pronto para aprender e crescer com a gente!

**Como interagir com o Papelzinho?** Basta marcá-lo em uma mensagem ou usar comandos específicos que iremos divulgar em breve! Ele estará em canais específicos, pronto para ajudar quando você precisar."""
        
        embed = discord.Embed(
            title="🤖 Papelzinho - Seu Assistente no Discord",
            description=description,
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Adicionar estatísticas em um campo separado (opcional)
        embed.add_field(
            name="📊 Estatísticas",
            value=f"Servidores: {len(self.bot.guilds)}\n"
                  f"Usuários: {len(self.bot.users)}\n"
                  f"Comandos: {len(self.bot.commands)}",
            inline=True
        )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        await self.send_private_response(ctx, embed=embed)
    
    @commands.hybrid_command(name='serverinfo', aliases=['servidor'])
    async def serverinfo(self, ctx):
        """Informações sobre o servidor"""
        if not ctx.guild:
            await self.send_private_response(ctx, content="❌ Este comando só funciona em servidores!")
            return
        
        guild = ctx.guild
        
        embed = discord.Embed(
            title=f"📊 {guild.name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(
            name="👥 Membros",
            value=f"Total: {guild.member_count}\n"
                  f"Humanos: {len([m for m in guild.members if not m.bot])}\n"
                  f"Bots: {len([m for m in guild.members if m.bot])}",
            inline=True
        )
        
        embed.add_field(
            name="📝 Canais",
            value=f"Texto: {len(guild.text_channels)}\n"
                  f"Voz: {len(guild.voice_channels)}\n"
                  f"Categorias: {len(guild.categories)}",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Outros",
            value=f"Roles: {len(guild.roles)}\n"
                  f"Emojis: {len(guild.emojis)}\n"
                  f"Boost: {guild.premium_subscription_count}",
            inline=True
        )
        
        embed.add_field(
            name="👑 Dono",
            value=guild.owner.mention if guild.owner else "N/A",
            inline=True
        )
        
        embed.add_field(
            name="📅 Criado em",
            value=f"<t:{int(guild.created_at.timestamp())}:R>",
            inline=True
        )
        
        embed.set_footer(text=f"ID: {guild.id}")
        
        await self.send_private_response(ctx, embed=embed)
    
    @commands.hybrid_command(name='userinfo', aliases=['usuario', 'user'])
    @app_commands.describe(usuario='Usuário para ver informações (opcional)')
    async def userinfo(self, ctx, usuario: discord.Member = None):
        """Informações sobre um usuário"""
        if not ctx.guild:
            await self.send_private_response(ctx, content="❌ Este comando só funciona em servidores!")
            return
        
        user = usuario or ctx.author
        
        embed = discord.Embed(
            title=f"👤 {user.display_name}",
            color=user.color if user.color != discord.Color.default() else discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        embed.add_field(
            name="📝 Informações",
            value=f"Tag: {user}\n"
                  f"ID: {user.id}\n"
                  f"Bot: {'Sim' if user.bot else 'Não'}",
            inline=False
        )
        
        embed.add_field(
            name="📅 Conta criada",
            value=f"<t:{int(user.created_at.timestamp())}:R>",
            inline=True
        )
        
        embed.add_field(
            name="📅 Entrou no servidor",
            value=f"<t:{int(user.joined_at.timestamp())}:R>" if user.joined_at else "N/A",
            inline=True
        )
        
        if user.roles[1:]:  # Excluir @everyone
            roles = ', '.join([role.mention for role in user.roles[1:]])
            if len(roles) > 1024:
                roles = roles[:1021] + "..."
            embed.add_field(
                name=f"🎭 Roles ({len(user.roles) - 1})",
                value=roles,
                inline=False
            )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}")
        
        await self.send_private_response(ctx, embed=embed)


async def setup(bot):
    await bot.add_cog(Utils(bot))

