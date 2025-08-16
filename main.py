import discord
from discord.ext import commands
import os, asyncio, re
from datetime import timedelta
from keep_alive import keep_alive

TOKEN = os.environ["TOKEN"]

GUILD_ID = 1401779980945592400
LOG_CHANNEL_ID = 1405694108302970910
WARN_ROLE_ID = 1401779980991725626

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix="god ", intents=intents)

def parse_time(t):
    match = re.match(r"(\d+)([smhd])", t.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s":1, "m":60, "h":3600, "d":86400}[unit]

async def send_log(action, target, moderator, reason, color, tiempo=None):
    embed = discord.Embed(
        title=f"{action}",
        color=color
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{target} ({target.id})", inline=False)
    embed.add_field(name="🛡 Moderador", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="📄 Razón", value=reason, inline=False)
    if tiempo:
        embed.add_field(name="⏳ Duración", value=tiempo, inline=False)
    embed.set_footer(text="Sistema de moderación")
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

def error_embed(title, description):
    return discord.Embed(title=title, description=description, color=discord.Color.red())

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

# ========= COMANDO BAN =========
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, user_id: str = None, tiempo: str = None, *, reason="No se especificó razón"):
    if not user_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god ban <id_usuario> [tiempo] [razón]`\nEjemplo: `god ban 123456789012345678 1h Spam`"
        )
        await ctx.send(embed=embed)
        return
    
    try:
        user_id = int(user_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        user = await bot.fetch_user(user_id)
        await guild.ban(user, reason=reason)
        await send_log("🚫 Ban", user, ctx.author, reason, discord.Color.red(), tiempo)
        await ctx.send(f"✅ Usuario {user} baneado.")
        
        if tiempo:
            seconds = parse_time(tiempo)
            if seconds:
                await asyncio.sleep(seconds)
                try:
                    await guild.unban(user)
                    await send_log("♻️ Unban automático", user, ctx.author, "Fin de sanción", discord.Color.green())
                except discord.Forbidden:
                    await ctx.send("❌ Error: No tengo permisos para desbanear")

    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para banear usuarios"))
    except discord.NotFound:
        await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado"))

# ========= COMANDO KICK =========
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, user_id: str = None, *, reason="No se especificó razón"):
    if not user_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god kick <id_usuario> [razón]`\nEjemplo: `god kick 123456789012345678 Mala conducta`"
        )
        await ctx.send(embed=embed)
        return

    try:
        user_id = int(user_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(user_id)
        if member:
            await member.kick(reason=reason)
            await send_log("👢 Kick", member, ctx.author, reason, discord.Color.orange())
            await ctx.send(f"✅ Usuario {member} expulsado.")
        else:
            await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado en el servidor"))
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para expulsar usuarios"))

# ========= COMANDO MUTE =========
@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, user_id: str = None, tiempo: str = None, *, reason="No se especificó razón"):
    if not user_id or not tiempo:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god mute <id_usuario> <tiempo> [razón]`\nEjemplo: `god mute 123456789012345678 30m Lenguaje inapropiado`"
        )
        await ctx.send(embed=embed)
        return

    try:
        user_id = int(user_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(user_id)
        if not member:
            await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado en el servidor"))
            return
            
        seconds = parse_time(tiempo)
        if not seconds:
            await ctx.send(embed=error_embed("❌ Error", "Formato de tiempo inválido. Usa: `10s`, `5m`, `2h`, `1d`."))
            return
            
        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        await member.timeout(until, reason=reason)
        await send_log("🔇 Mute", member, ctx.author, reason, discord.Color.dark_gray(), tiempo)
        await ctx.send(f"✅ Usuario {member} muteado por {tiempo}.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para mutear usuarios"))

# ========= COMANDO UNMUTE =========
@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, user_id: str = None, *, reason="No se especificó razón"):
    if not user_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god unmute <id_usuario> [razón]`\nEjemplo: `god unmute 123456789012345678`"
        )
        await ctx.send(embed=embed)
        return

    try:
        user_id = int(user_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(user_id)
        if not member:
            await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado en el servidor"))
            return
            
        if not member.is_timed_out():
            await ctx.send(embed=error_embed("❌ Error", "El usuario no está muteado"))
            return
            
        await member.timeout(None, reason=reason)
        await send_log("🔊 Unmute", member, ctx.author, reason, discord.Color.green())
        await ctx.send(f"✅ Usuario {member} desmuteado.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para desmutear usuarios"))

# ========= COMANDO WARN =========
@bot.command()
@commands.has_permissions(manage_roles=True)
async def warn(ctx, user_id: str = None, *, reason="No se especificó razón"):
    if not user_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god warn <id_usuario> [razón]`\nEjemplo: `god warn 123456789012345678 Comportamiento inapropiado`"
        )
        await ctx.send(embed=embed)
        return

    try:
        user_id = int(user_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    try:
        guild = bot.get_guild(GUILD_ID)
        member = guild.get_member(user_id)
        if not member:
            await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado en el servidor"))
            return
            
        warn_role = guild.get_role(WARN_ROLE_ID)
        if not warn_role:
            await ctx.send(embed=error_embed("❌ Error", "Rol de warn no encontrado"))
            return
            
        await member.add_roles(warn_role, reason=reason)
        await send_log("⚠️ Warn", member, ctx.author, reason, discord.Color.yellow())
        await ctx.send(f"⚠️ Usuario {member} advertido.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para asignar el rol de warn"))

keep_alive()
bot.run(TOKEN)
