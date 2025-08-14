import discord
from discord.ext import commands
import os
from keep_alive import keep_alive

TOKEN = os.environ["TOKEN"] 

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot conectado como {bot.user}")

@bot.command()
async def hola(ctx):
    await ctx.send("¡Hola! Estoy activo 24/7 😎")

# Mantener vivo
keep_alive()

# Ejecutar bot
bot.run(TOKEN)
