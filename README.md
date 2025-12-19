# 🤖 Papelzinho - Bot Discord

Bot Discord criado com Python e discord.py, hospedado na Square Cloud.

## 📋 Funcionalidades

- ✅ Comandos com prefixo e slash commands
- ✅ Sistema de comandos personalizados
- ✅ Banco de dados SQLite
- ✅ Comandos utilitários (ping, info, serverinfo, userinfo)
- ✅ Sistema modular com cogs

## 🚀 Instalação

### 1. Clonar o repositório

```bash
git clone https://github.com/seu-usuario/bot-papelzinho.git
cd bot-papelzinho
```

### 2. Instalar dependências

```bash
pip3 install -r requirements.txt
```

**Nota:** Se o comando `pip` não funcionar, use `pip3`.

### 3. Configurar variáveis de ambiente

Copie o arquivo `.env.example` para `.env` e preencha com suas credenciais:

```bash
cp .env.example .env
```

Edite o arquivo `.env`:
```
DISCORD_TOKEN=seu_token_do_discord
PREFIX=!
```

## 📝 Como obter o Token do Discord

1. Acesse [Discord Developer Portal](https://discord.com/developers/applications)
2. Crie uma nova aplicação ou selecione uma existente
3. Vá em "Bot" e crie um bot
4. Copie o token e adicione no arquivo `.env`

## 🎮 Comandos Disponíveis

### Comandos Utilitários

- `!ping` ou `/ping` - Verificar latência do bot
- `!info` ou `/info` - Informações sobre o bot
- `!serverinfo` ou `/serverinfo` - Informações do servidor
- `!userinfo [usuário]` ou `/userinfo [usuário]` - Informações de um usuário

### Comandos Personalizados

- `!addcommand <nome> <resposta>` ou `/addcommand` - Criar um comando personalizado
- `!delcommand <nome>` ou `/delcommand` - Deletar um comando personalizado
- `!listcommands` ou `/listcommands` - Listar todos os comandos personalizados

### Exemplos de Comandos Personalizados

```
!addcommand oi Olá {user}! Bem-vindo ao servidor!
!addcommand regras Leia as regras em #regras
```

Variáveis disponíveis nos comandos personalizados:
- `{user}` - Menção do usuário
- `{username}` - Nome do usuário
- `{server}` - Nome do servidor

## 📤 Enviar para o GitHub

### 1. Criar repositório no GitHub

1. Acesse [GitHub](https://github.com) e crie um novo repositório chamado `bot-papelzinho`
2. **Não** inicialize com README, .gitignore ou licença (já temos esses arquivos)

### 2. Fazer push do código

```bash
git init
git add .
git commit -m "Initial commit - Bot Papelzinho"
git branch -M main
git remote add origin https://github.com/seu-usuario/bot-papelzinho.git
git push -u origin main
```

### 3. Autenticação no GitHub

Se solicitado, você precisará autenticar. Opções:

**Opção A - Token de Acesso Pessoal (Recomendado):**
1. Acesse [GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)](https://github.com/settings/tokens)
2. Clique em "Generate new token (classic)"
3. Dê um nome e selecione o escopo `repo`
4. Copie o token gerado
5. Use o token como senha quando o Git solicitar credenciais

**Opção B - GitHub CLI:**
```bash
# Instalar GitHub CLI (se não tiver)
sudo apt install gh  # ou use outro método de instalação

# Autenticar
gh auth login

# Fazer push
git push -u origin main
```

## ☁️ Deploy na Square Cloud

### 1. Criar conta na Square Cloud

Acesse [Square Cloud](https://squarecloud.app/) e crie uma conta.

### 2. Conectar repositório GitHub

1. No painel da Square Cloud, vá em "Applications"
2. Clique em "Create Application"
3. Selecione "Connect GitHub Repository"
4. Autorize o acesso ao GitHub
5. Selecione o repositório `bot-papelzinho`

### 3. Configurar variáveis de ambiente

Na Square Cloud, adicione as variáveis de ambiente:
- `DISCORD_TOKEN` - Token do bot
- `PREFIX` - Prefixo dos comandos (opcional, padrão: !)

### 4. Configurar execução do ambiente

**Recomendado: Modo Automático** ✅

1. Escolha o modo **Automático**
2. Arquivo principal: `main.py`
3. A Square Cloud detectará automaticamente e executará o bot

**Alternativa: Modo Manual**

Se preferir o modo Manual, configure:
- **Ambiente**: Python 3.11 (ou 3.10)
- **Comando de inicialização**: `python3 main.py`

**Nota:** O arquivo `squarecloud.json` já está configurado no repositório e será usado automaticamente pela Square Cloud.

## 📁 Estrutura do Projeto

```
bot-papelzinho/
├── main.py                 # Arquivo principal do bot
├── requirements.txt        # Dependências Python
├── .env.example           # Exemplo de variáveis de ambiente
├── .gitignore             # Arquivos ignorados pelo Git
├── README.md              # Este arquivo
├── cogs/                  # Módulos do bot (cogs)
│   ├── __init__.py
│   ├── custom_commands.py  # Sistema de comandos personalizados
│   └── utils.py            # Comandos utilitários
└── data/                  # Banco de dados (criado automaticamente)
    └── bot.db             # Banco SQLite
```

## 🔧 Desenvolvimento

### Executar localmente

```bash
python3 main.py
```

**Nota:** Se o comando `python` não funcionar, use `python3`. Em alguns sistemas Linux, o Python 3 é acessado através de `python3`.

### Adicionar novos comandos

Crie um novo arquivo em `cogs/` e adicione ao `load_extensions()` em `main.py`:

```python
# cogs/meu_cog.py
from discord.ext import commands

class MeuCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.hybrid_command(name='meucomando')
    async def meu_comando(self, ctx):
        await ctx.send("Olá!")

async def setup(bot):
    await bot.add_cog(MeuCog(bot))
```

## 📄 Licença

Este projeto é de código aberto e está disponível sob a licença MIT.

## 🤝 Contribuindo

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues e pull requests.

## 📞 Suporte

Se tiver dúvidas ou problemas, abra uma issue no repositório.

