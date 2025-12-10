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
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='info', aliases=['botinfo', 'sobre'])
    async def info(self, ctx):
        """Informações sobre o bot"""
        embed = discord.Embed(
            title="🤖 Papelzinho - Informações",
            description="Bot Discord criado com discord.py",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Estatísticas",
            value=f"Servidores: {len(self.bot.guilds)}\n"
                  f"Usuários: {len(self.bot.users)}\n"
                  f"Comandos: {len(self.bot.commands)}",
            inline=False
        )
        
        embed.add_field(
            name="💻 Tecnologias",
            value=f"Python: {platform.python_version()}\n"
                  f"discord.py: {discord.__version__}\n"
                  f"Plataforma: {platform.system()}",
            inline=False
        )
        
        embed.set_footer(text=f"Solicitado por {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='serverinfo', aliases=['servidor'])
    async def serverinfo(self, ctx):
        """Informações sobre o servidor"""
        if not ctx.guild:
            await ctx.send("❌ Este comando só funciona em servidores!")
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
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='userinfo', aliases=['usuario', 'user'])
    @app_commands.describe(usuario='Usuário para ver informações (opcional)')
    async def userinfo(self, ctx, usuario: discord.Member = None):
        """Informações sobre um usuário"""
        if not ctx.guild:
            await ctx.send("❌ Este comando só funciona em servidores!")
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
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utils(bot))

