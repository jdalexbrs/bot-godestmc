import discord
from discord.ext import commands
import os, re, asyncio
from datetime import datetime, timedelta

from sqlalchemy import (
    create_engine, Column, Integer, BigInteger,
    String, Text, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

# =========================================================
# VARIABLES DE ENTORNO
# =========================================================

REQUIRED_ENV_VARS = [
    "TOKEN",
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "GUILD_ID",
    "LOG_CHANNEL_ID",
    "WARN_ROLE_ID",
    "WARN_ACTION_CHANNEL",
    "PROMOTE_CHANNEL",
    "DEMOTE_CHANNEL"
]

for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        raise RuntimeError(f"Falta la variable de entorno: {var}")

TOKEN = os.getenv("TOKEN")

GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
WARN_ROLE_ID = int(os.getenv("WARN_ROLE_ID"))
WARN_ACTION_CHANNEL = int(os.getenv("WARN_ACTION_CHANNEL"))
PROMOTE_CHANNEL = int(os.getenv("PROMOTE_CHANNEL"))
DEMOTE_CHANNEL = int(os.getenv("DEMOTE_CHANNEL"))

# =========================================================
# BASE DE DATOS (MySQL)
# =========================================================

DB_URL = (
    f"mysql+mysqlconnector://{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)

engine = create_engine(DB_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class Accion(Base):
    __tablename__ = "acciones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False)
    moderator_id = Column(BigInteger, nullable=False)
    tipo = Column(String(20), nullable=False)
    razon = Column(Text, nullable=False)
    duracion = Column(String(20), nullable=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    guild_id = Column(BigInteger, nullable=False)

Base.metadata.create_all(engine)

def registrar_accion(user_id, tipo, razon, moderator_id, duracion=None):
    session = SessionLocal()
    try:
        accion = Accion(
            user_id=user_id,
            moderator_id=moderator_id,
            tipo=tipo,
            razon=razon,
            duracion=duracion,
            guild_id=GUILD_ID
        )
        session.add(accion)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print("DB ERROR:", e)
    finally:
        session.close()

def obtener_acciones(user_id):
    session = SessionLocal()
    try:
        return (
            session.query(Accion)
            .filter_by(user_id=user_id, guild_id=GUILD_ID)
            .order_by(Accion.fecha.desc())
            .all()
        )
    finally:
        session.close()

def contar_warns(user_id):
    session = SessionLocal()
    try:
        return (
            session.query(Accion)
            .filter_by(user_id=user_id, tipo="warn", guild_id=GUILD_ID)
            .count()
        )
    finally:
        session.close()

# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="god ",
    intents=intents,
    help_command=None
)

# =========================================================
# UTILIDADES
# =========================================================

def parse_time(text):
    match = re.match(r"(\d+)([smhd])", text.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s":1, "m":60, "h":3600, "d":86400}[unit]

async def send_log(title, member, moderator, reason, color, duration=None):
    embed = discord.Embed(title=title, color=color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Usuario", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="Moderador", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Razón", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duración", value=duration, inline=False)

    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

def error_embed(msg):
    return discord.Embed(title="Error", description=msg, color=discord.Color.red())

# =========================================================
# EVENTOS
# =========================================================

@bot.event
async def on_ready():
    print(f"Conectado como {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="god help"
        )
    )

# =========================================================
# COMANDOS
# =========================================================

@bot.command()
@commands.has_permissions(manage_roles=True)
async def warn(ctx, member: discord.Member, *, reason="Sin razón"):
    await member.add_roles(ctx.guild.get_role(WARN_ROLE_ID))
    registrar_accion(member.id, "warn", reason, ctx.author.id)
    await send_log("⚠️ Warn", member, ctx.author, reason, discord.Color.yellow())

    warns = contar_warns(member.id)
    if warns >= 3:
        channel = bot.get_channel(WARN_ACTION_CHANNEL)
        if channel:
            await channel.send(
                embed=discord.Embed(
                    title="🚨 3 Advertencias",
                    description=f"{member.mention} ha alcanzado 3 warns",
                    color=discord.Color.orange()
                )
            )

    await ctx.send(f"{member.mention} advertido.")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def mute(ctx, member: discord.Member, tiempo: str, *, reason="Sin razón"):
    seconds = parse_time(tiempo)
    if not seconds:
        await ctx.send(embed=error_embed("Tiempo inválido"))
        return

    await member.timeout(timedelta(seconds=seconds), reason=reason)
    registrar_accion(member.id, "mute", reason, ctx.author.id, tiempo)
    await send_log("🔇 Mute", member, ctx.author, reason, discord.Color.dark_grey(), tiempo)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    registrar_accion(member.id, "unmute", "Unmute manual", ctx.author.id)
    await send_log("🔊 Unmute", member, ctx.author, "Unmute manual", discord.Color.green())

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="Sin razón"):
    await member.kick(reason=reason)
    registrar_accion(member.id, "kick", reason, ctx.author.id)
    await send_log("👢 Kick", member, ctx.author, reason, discord.Color.orange())

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Sin razón"):
    await member.ban(reason=reason)
    registrar_accion(member.id, "ban", reason, ctx.author.id)
    await send_log("⛔ Ban", member, ctx.author, reason, discord.Color.red())

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    await ctx.guild.unban(user)
    registrar_accion(user_id, "unban", "Unban manual", ctx.author.id)
    await ctx.send(f"{user} desbaneado.")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def promote(ctx, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    registrar_accion(member.id, "promote", role.name, ctx.author.id)
    await bot.get_channel(PROMOTE_CHANNEL).send(f"{member.mention} promovido a {role.name}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def demote(ctx, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    registrar_accion(member.id, "demote", role.name, ctx.author.id)
    await bot.get_channel(DEMOTE_CHANNEL).send(f"{member.mention} degradado de {role.name}")

@bot.command()
@commands.has_permissions(manage_roles=True)
async def historial(ctx, member: discord.Member):
    acciones = obtener_acciones(member.id)
    if not acciones:
        await ctx.send("Sin historial.")
        return

    embed = discord.Embed(
        title=f"Historial de {member}",
        color=discord.Color.blurple()
    )

    for a in acciones[:15]:
        embed.add_field(
            name=f"{a.tipo.upper()} | {a.fecha.strftime('%d/%m/%Y %H:%M')}",
            value=f"Razón: {a.razon}\nModerador: <@{a.moderator_id}>",
            inline=False
        )

    await ctx.send(embed=embed)

# =========================================================
# RUN
# =========================================================

bot.run(TOKEN)
