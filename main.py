import discord
from discord.ext import commands
from sqlalchemy import create_engine, text

# ================= CONFIG =================

TOKEN = "TU_TOKEN_DEL_BOT"

DB_USER = "u13_Q9m5REH6Vj"
DB_PASSWORD = "jKWdy7^WU9Hcpd5x^nNyGf+T"
DB_HOST = "db-mia.trustsnodes.com"
DB_PORT = 3306
DB_NAME = "s13_BOT_DISCORD"

WARN_ACTION_CHANNEL = 123456789012345678
LOG_CHANNEL_ID = 123456789012345678

# =========================================

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True
)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="god ", intents=intents)

# ================= DATABASE =================

def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS actions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                action_type VARCHAR(20) NOT NULL,
                reason TEXT,
                moderator_id BIGINT,
                duration VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

def registrar_accion(user_id, guild_id, action_type, reason, moderator_id, duration=None):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO actions (user_id, guild_id, action_type, reason, moderator_id, duration)
                VALUES (:user_id, :guild_id, :action_type, :reason, :moderator_id, :duration)
            """),
            {
                "user_id": user_id,
                "guild_id": guild_id,
                "action_type": action_type,
                "reason": reason,
                "moderator_id": moderator_id,
                "duration": duration
            }
        )

def contar_warns(user_id, guild_id):
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT COUNT(*) FROM actions
                WHERE user_id = :user_id
                AND guild_id = :guild_id
                AND action_type = 'warn'
            """),
            {"user_id": user_id, "guild_id": guild_id}
        )
        return result.scalar()

def obtener_historial(user_id, guild_id):
    with engine.begin() as conn:
        return conn.execute(
            text("""
                SELECT action_type, reason, created_at
                FROM actions
                WHERE user_id = :user_id AND guild_id = :guild_id
                ORDER BY created_at DESC
            """),
            {"user_id": user_id, "guild_id": guild_id}
        ).fetchall()

# ================= LOG =================

async def send_log(title, member, moderator, reason, color):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=False)
    embed.add_field(name="Moderador", value=f"{moderator} (`{moderator.id}`)", inline=False)
    embed.add_field(name="Razón", value=reason, inline=False)

    await channel.send(embed=embed)

# ================= EVENTS =================

@bot.event
async def on_ready():
    init_db()
    print(f"Bot conectado como {bot.user}")

# ================= COMANDOS =================

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No se especificó razón"):
    registrar_accion(
        member.id,
        ctx.guild.id,
        "warn",
        reason,
        ctx.author.id
    )

    warns = contar_warns(member.id, ctx.guild.id)

    await send_log(
        "⚠️ Warn",
        member,
        ctx.author,
        reason,
        discord.Color.orange()
    )

    await ctx.send(
        embed=discord.Embed(
            title="⚠️ Advertencia aplicada",
            description=f"{member.mention} ahora tiene **{warns}/3 warns**",
            color=discord.Color.orange()
        )
    )

    if warns >= 3:
        channel = bot.get_channel(WARN_ACTION_CHANNEL)
        if channel:
            await channel.send(
                embed=discord.Embed(
                    title="🚨 3 Advertencias",
                    description=f"{member.mention} ha alcanzado **3 warns**.",
                    color=discord.Color.red()
                )
            )

@bot.command(name="historial")
@commands.has_permissions(moderate_members=True)
async def historial(ctx, member: discord.Member):
    acciones = obtener_historial(member.id, ctx.guild.id)

    if not acciones:
        await ctx.send("Este usuario no tiene historial.")
        return

    embed = discord.Embed(
        title=f"📄 Historial de {member}",
        color=discord.Color.blurple()
    )

    for action, reason, date in acciones[:10]:
        embed.add_field(
            name=f"{action.upper()} — {date.strftime('%Y-%m-%d %H:%M')}",
            value=reason or "Sin razón",
            inline=False
        )

    await ctx.send(embed=embed)

@bot.command(name="sanciones")
@commands.has_permissions(moderate_members=True)
async def sanciones(ctx, member: discord.Member):
    await historial(ctx, member)

# ================= RUN =================

bot.run(TOKEN)
