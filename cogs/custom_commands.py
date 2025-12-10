import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import os
from datetime import datetime

class CustomCommands(commands.Cog):
    """Sistema de comandos personalizados"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db_path = 'data/bot.db'
        self.init_database()
    
    def init_database(self):
        """Inicializar banco de dados"""
        os.makedirs('data', exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Tabela de comandos personalizados
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS custom_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                command_response TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT,
                uses INTEGER DEFAULT 0,
                UNIQUE(guild_id, command_name)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Obter conexão com o banco de dados"""
        return sqlite3.connect(self.db_path)
    
    @commands.hybrid_command(name='addcommand', aliases=['addcmd', 'criarcomando'])
    @app_commands.describe(
        nome='Nome do comando',
        resposta='Resposta do comando'
    )
    async def add_command(self, ctx, nome: str, *, resposta: str):
        """Criar um comando personalizado (prefixo ou slash)"""
        if not ctx.guild:
            await ctx.send("❌ Este comando só funciona em servidores!")
            return
        
        # Validar nome do comando
        if len(nome) < 2 or len(nome) > 20:
            await ctx.send("❌ O nome do comando deve ter entre 2 e 20 caracteres!")
            return
        
        if not nome.isalnum():
            await ctx.send("❌ O nome do comando deve conter apenas letras e números!")
            return
        
        # Verificar se já existe
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT command_name FROM custom_commands WHERE guild_id = ? AND command_name = ?',
            (ctx.guild.id, nome.lower())
        )
        
        if cursor.fetchone():
            conn.close()
            await ctx.send(f"❌ O comando `{nome}` já existe!")
            return
        
        # Criar comando
        cursor.execute(
            '''INSERT INTO custom_commands 
               (guild_id, command_name, command_response, created_by, created_at, uses)
               VALUES (?, ?, ?, ?, ?, 0)''',
            (ctx.guild.id, nome.lower(), resposta, ctx.author.id, datetime.now().isoformat())
        )
        
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ Comando `{nome}` criado com sucesso!")
    
    @commands.hybrid_command(name='delcommand', aliases=['delcmd', 'deletarcomando'])
    @app_commands.describe(nome='Nome do comando a deletar')
    async def del_command(self, ctx, nome: str):
        """Deletar um comando personalizado"""
        if not ctx.guild:
            await ctx.send("❌ Este comando só funciona em servidores!")
            return
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT created_by FROM custom_commands WHERE guild_id = ? AND command_name = ?',
            (ctx.guild.id, nome.lower())
        )
        
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            await ctx.send(f"❌ O comando `{nome}` não existe!")
            return
        
        # Verificar permissões (criador ou admin)
        created_by = result[0]
        if ctx.author.id != created_by and not ctx.author.guild_permissions.administrator:
            conn.close()
            await ctx.send("❌ Você não tem permissão para deletar este comando!")
            return
        
        cursor.execute(
            'DELETE FROM custom_commands WHERE guild_id = ? AND command_name = ?',
            (ctx.guild.id, nome.lower())
        )
        
        conn.commit()
        conn.close()
        
        await ctx.send(f"✅ Comando `{nome}` deletado com sucesso!")
    
    @commands.hybrid_command(name='listcommands', aliases=['listcmd', 'comandos'])
    async def list_commands(self, ctx):
        """Listar todos os comandos personalizados do servidor"""
        if not ctx.guild:
            await ctx.send("❌ Este comando só funciona em servidores!")
            return
        
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT command_name, uses FROM custom_commands WHERE guild_id = ? ORDER BY uses DESC',
            (ctx.guild.id,)
        )
        
        commands_list = cursor.fetchall()
        conn.close()
        
        if not commands_list:
            await ctx.send("📝 Não há comandos personalizados neste servidor.")
            return
        
        embed = discord.Embed(
            title=f"📋 Comandos Personalizados - {ctx.guild.name}",
            color=discord.Color.blue()
        )
        
        commands_text = "\n".join([f"`{cmd[0]}` - {cmd[1]} uso(s)" for cmd in commands_list])
        embed.description = commands_text
        embed.set_footer(text=f"Total: {len(commands_list)} comando(s)")
        
        await ctx.send(embed=embed)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Listener para executar comandos personalizados"""
        if message.author.bot:
            return
        
        if not message.guild:
            return
        
        # Verificar se é um comando personalizado
        prefix = self.bot.command_prefix
        if isinstance(prefix, str):
            if not message.content.startswith(prefix):
                return
            command_name = message.content[len(prefix):].split()[0].lower()
        else:
            return
        
        # Verificar se não é um comando do bot
        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return
        
        # Buscar comando personalizado
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT command_response FROM custom_commands WHERE guild_id = ? AND command_name = ?',
            (message.guild.id, command_name)
        )
        
        result = cursor.fetchone()
        
        if result:
            # Atualizar contador de usos
            cursor.execute(
                'UPDATE custom_commands SET uses = uses + 1 WHERE guild_id = ? AND command_name = ?',
                (message.guild.id, command_name)
            )
            conn.commit()
            
            # Enviar resposta
            response = result[0]
            # Substituir variáveis (opcional)
            response = response.replace('{user}', message.author.mention)
            response = response.replace('{username}', message.author.name)
            response = response.replace('{server}', message.guild.name)
            
            await message.channel.send(response)
        
        conn.close()
    
    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handler de erros para slash commands"""
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ Aguarde {error.retry_after:.1f} segundos antes de usar novamente.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "❌ Ocorreu um erro ao executar o comando.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(CustomCommands(bot))

