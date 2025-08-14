import discord
from discord.ext import commands
import os, asyncio, re
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
    embed.set_thumbnail(url=target.display_avatar.url if hasattr(target, "display_avatar") else target.avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{target} ({target.id})", inline=False)
    embed.add_field(name="🛡 Moderador", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="📄 Razón", value=reason, inline=False)
    if tiempo:
        embed.add_field(name="⏳ Duración", value=tiempo, inline=False)
    embed.set_footer(text="Sistema de moderación")
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

# BAN
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, user_id: int, tiempo: str = None, *, reason="No se especificó razón"):
    guild = bot.get_guild(GUILD_ID)
    user = await bot.fetch_user(user_id)
    await guild.ban(user, reason=reason)
    await send_log("🚫 Ban", user, ctx.author, reason, discord.Color.red(), tiempo)
    await ctx.send(f"✅ Usuario {user} baneado.")
    if tiempo:
        seconds = parse_time(tiempo)
        if seconds:
            await asyncio.sleep(seconds)
            await guild.unban(user)
            await send_log("♻️ Unban automático", user, ctx.author, "Fin de sanción", discord.Color.green())

# KICK
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, user_id: int, *, reason="No se especificó razón"):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        await member.kick(reason=reason)
        await send_log("👢 Kick", member, ctx.author, reason, discord.Color.orange())
        await ctx.send(f"✅ Usuario {member} expulsado.")
    else:
        await ctx.send("❌ Usuario no encontrado.")

# MUTE
@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, user_id: int, tiempo: str = None, *, reason="No se especificó razón"):
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        seconds = parse_time(tiempo) if tiempo else None
        until = discord.utils.utcnow() + discord.timedelta(seconds=seconds) if seconds else None
        await member.timeout(until, reason=reason)
        await send_log("🔇 Mute", member, ctx.author, reason, discord.Color.dark_gray(), tiempo)
        await ctx.send(f"✅ Usuario {member} muteado.")
    else:
        await ctx.send("❌ Usuario no encontrado.")

# WARN
@bot.command()
async def warn(ctx, user_id: int, tiempo: str = None, *, reason="No se especificó razón"):
    if WARN_ROLE_ID not in [role.id for role in ctx.author.roles]:
        await ctx.send("❌ No tienes el rol necesario para usar este comando.")
        return
    guild = bot.get_guild(GUILD_ID)
    member = guild.get_member(user_id)
    if member:
        await send_log("⚠️ Warn", member, ctx.author, reason, discord.Color.yellow(), tiempo)
        await ctx.send(f"⚠️ Usuario {member} advertido.")
    else:
        await ctx.send("❌ Usuario no encontrado.")

keep_alive()
bot.run(TOKEN)
