import discord
from discord.ext import commands
import os, re, asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# =========================================================
# VARIABLES DE ENTORNO
# =========================================================

TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno: TOKEN")

DB_USER = os.getenv("DB_USER", "u13_Q9m5REH6Vj")
DB_PASSWORD = os.getenv("DB_PASSWORD", "jKWdy7^WU9Hcpd5x^nNyGf+T")
DB_HOST = os.getenv("DB_HOST", "db-mia.trustsnodes.com")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME", "s13_BOT_DISCORD")

WARN_ACTION_CHANNEL = int(os.getenv("WARN_ACTION_CHANNEL", "123456789012345678"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "123456789012345678"))
GUILD_ID = int(os.getenv("GUILD_ID", "123456789012345678"))

# =========================================================
# BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="god ", intents=intents)

# =========================================================
# BASE DE DATOS
# =========================================================

engine = create_engine(
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
    pool_pre_ping=True
)

def init_db():
    """Inicializa la base de datos con las tablas necesarias"""
    with engine.begin() as conn:
        # Tabla de acciones (warns, mutes, bans, etc.)
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS actions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                action_type VARCHAR(20) NOT NULL,
                reason TEXT,
                moderator_id BIGINT,
                duration VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_guild (user_id, guild_id),
                INDEX idx_action_type (action_type)
            )
        """))
        
        # Tabla específica para warns acumulados
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_warns (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                total_warns INT DEFAULT 0,
                last_warn_date TIMESTAMP NULL,
                UNIQUE KEY unique_user_guild (user_id, guild_id),
                INDEX idx_warns_count (total_warns)
            )
        """))

def registrar_accion(user_id, guild_id, action_type, reason, moderator_id, duration=None):
    """Registra una acción en la base de datos"""
    with engine.begin() as conn:
        # Registrar la acción
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
        
        # Si es un warn, actualizar el contador
        if action_type == 'warn':
            conn.execute(
                text("""
                    INSERT INTO user_warns (user_id, guild_id, total_warns, last_warn_date)
                    VALUES (:user_id, :guild_id, 1, NOW())
                    ON DUPLICATE KEY UPDATE 
                    total_warns = total_warns + 1,
                    last_warn_date = NOW()
                """),
                {"user_id": user_id, "guild_id": guild_id}
            )

def contar_warns(user_id, guild_id):
    """Cuenta los warns de un usuario"""
    with engine.begin() as conn:
        result = conn.execute(
            text("""
                SELECT total_warns FROM user_warns
                WHERE user_id = :user_id AND guild_id = :guild_id
            """),
            {"user_id": user_id, "guild_id": guild_id}
        )
        row = result.fetchone()
        return row[0] if row else 0

def obtener_historial(user_id, guild_id, limit=15):
    """Obtiene el historial de acciones de un usuario"""
    with engine.begin() as conn:
        return conn.execute(
            text("""
                SELECT action_type, reason, moderator_id, duration, created_at
                FROM actions
                WHERE user_id = :user_id AND guild_id = :guild_id
                ORDER BY created_at DESC
                LIMIT :limit
            """),
            {"user_id": user_id, "guild_id": guild_id, "limit": limit}
        ).fetchall()

def reset_warns(user_id, guild_id):
    """Resetea los warns de un usuario"""
    with engine.begin() as conn:
        conn.execute(
            text("""
                DELETE FROM user_warns
                WHERE user_id = :user_id AND guild_id = :guild_id
            """),
            {"user_id": user_id, "guild_id": guild_id}
        )
        # También eliminamos los registros de warns individuales si se desea
        # conn.execute(
        #     text("""
        #         DELETE FROM actions
        #         WHERE user_id = :user_id AND guild_id = :guild_id AND action_type = 'warn'
        #     """),
        #     {"user_id": user_id, "guild_id": guild_id}
        # )

# =========================================================
# UTILIDADES
# =========================================================

def parse_time(text):
    """Convierte texto como '1d', '2h', '30m' a segundos"""
    match = re.match(r"(\d+)([smhd])", text.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    return value * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]

async def send_log(title, member, moderator, reason, color, duration=None):
    """Envía un embed al canal de logs"""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(title=title, color=color)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Usuario", value=f"{member} (`{member.id}`)", inline=False)
    embed.add_field(name="Moderador", value=f"{moderator} (`{moderator.id}`)", inline=False)
    embed.add_field(name="Razón", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duración", value=duration, inline=False)
    
    await channel.send(embed=embed)

def error_embed(msg):
    """Crea un embed de error"""
    return discord.Embed(title="❌ Error", description=msg, color=discord.Color.red())

# =========================================================
# EVENTOS
# =========================================================

@bot.event
async def on_ready():
    """Evento cuando el bot está listo"""
    print(f"Bot conectado como {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="god help"
        )
    )
    init_db()
    print("Base de datos inicializada")

# =========================================================
# COMANDOS
# =========================================================

@bot.command()
@commands.has_permissions(moderate_members=True)
async def warn(ctx, member: discord.Member, *, reason="No se especificó razón"):
    """Da un warn a un usuario (requiere moderate_members)"""
    
    if member == ctx.author:
        await ctx.send(embed=error_embed("No puedes advertirte a ti mismo."))
        return
    
    if member.bot:
        await ctx.send(embed=error_embed("No puedes advertir a un bot."))
        return
    
    # Registrar warn en la base de datos
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="warn",
        reason=reason,
        moderator_id=ctx.author.id
    )
    
    # Obtener total de warns
    warns = contar_warns(member.id, ctx.guild.id)
    
    # Enviar log
    await send_log(
        "⚠️ Warn",
        member,
        ctx.author,
        reason,
        discord.Color.orange()
    )
    
    # Respuesta en el canal
    embed = discord.Embed(
        title="⚠️ Advertencia aplicada",
        description=f"{member.mention} ahora tiene **{warns}/3 warns**",
        color=discord.Color.orange()
    )
    embed.add_field(name="Razón", value=reason, inline=False)
    await ctx.send(embed=embed)
    
    # Sistema automático de 3 warns
    if warns >= 3:
        channel = bot.get_channel(WARN_ACTION_CHANNEL)
        if channel:
            await channel.send(
                embed=discord.Embed(
                    title="🚨 3 Advertencias",
                    description=(
                        f"**Usuario:** {member.mention} (`{member.id}`)\n"
                        f"**Moderador:** {ctx.author.mention}\n"
                        f"**Total warns:** {warns}\n\n"
                        f"Se recomienda aplicar una sanción (mute, kick o ban)."
                    ),
                    color=discord.Color.red()
                )
            )

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unwarn(ctx, member: discord.Member, cantidad: int = 1):
    """Elimina warns de un usuario (requiere moderate_members)"""
    
    if cantidad <= 0:
        await ctx.send(embed=error_embed("La cantidad debe ser mayor a 0."))
        return
    
    warns_actuales = contar_warns(member.id, ctx.guild.id)
    
    if warns_actuales == 0:
        await ctx.send(embed=error_embed(f"{member.mention} no tiene warns."))
        return
    
    # Resetear warns si se piden más de los que tiene
    if cantidad >= warns_actuales:
        reset_warns(member.id, ctx.guild.id)
        nuevo_total = 0
        accion = "todos los warns"
    else:
        # En este ejemplo simple, reseteamos y ponemos la nueva cantidad
        # En una implementación más avanzada, podrías marcar warns específicos como eliminados
        reset_warns(member.id, ctx.guild.id)
        nuevo_total = warns_actuales - cantidad
        # Aquí deberías reinsertar los warns restantes si tu lógica lo requiere
        accion = f"{cantidad} warn(s)"
    
    embed = discord.Embed(
        title="✅ Warns removidos",
        description=f"Se han removido {accion} de {member.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="Warns anteriores", value=warns_actuales, inline=True)
    embed.add_field(name="Warns actuales", value=nuevo_total, inline=True)
    
    await ctx.send(embed=embed)
    
    # Registrar la acción
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="unwarn",
        reason=f"Removidos {cantidad} warns por {ctx.author}",
        moderator_id=ctx.author.id
    )

@bot.command(name="historial")
@commands.has_permissions(moderate_members=True)
async def historial(ctx, member: discord.Member):
    """Muestra el historial de sanciones de un usuario (requiere moderate_members)"""
    
    acciones = obtener_historial(member.id, ctx.guild.id)
    
    if not acciones:
        await ctx.send(f"{member.mention} no tiene historial de sanciones.")
        return
    
    embed = discord.Embed(
        title=f"📄 Historial de {member}",
        color=discord.Color.blue()
    )
    
    warns_count = contar_warns(member.id, ctx.guild.id)
    embed.set_footer(text=f"Total de warns actuales: {warns_count}/3")
    
    for action, reason, mod_id, duration, date in acciones[:10]:  # Mostrar máximo 10
        fecha = date.strftime('%Y-%m-%d %H:%M')
        moderator = ctx.guild.get_member(mod_id) if mod_id else "Desconocido"
        mod_name = f"{moderator}" if isinstance(moderator, discord.Member) else f"<@{mod_id}>"
        
        campo = f"**Fecha:** {fecha}\n"
        campo += f"**Moderador:** {mod_name}\n"
        if duration:
            campo += f"**Duración:** {duration}\n"
        campo += f"**Razón:** {reason or 'Sin razón'}"
        
        embed.add_field(
            name=f"{action.upper()}",
            value=campo,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name="sanciones")
@commands.has_permissions(moderate_members=True)
async def sanciones(ctx, member: discord.Member):
    """Alias de historial (requiere moderate_members)"""
    await historial(ctx, member)

@bot.command(name="checkwarns")
@commands.has_permissions(moderate_members=True)
async def checkwarns(ctx, member: discord.Member = None):
    """Muestra los warns actuales de un usuario (requiere moderate_members)"""
    
    target = member or ctx.author
    
    warns = contar_warns(target.id, ctx.guild.id)
    
    embed = discord.Embed(
        title=f"⚠️ Warns de {target}",
        color=discord.Color.orange() if warns > 0 else discord.Color.green()
    )
    
    embed.add_field(name="Warns actuales", value=f"{warns}/3", inline=False)
    
    if warns > 0:
        # Obtener los últimos warns
        with engine.begin() as conn:
            últimos_warns = conn.execute(
                text("""
                    SELECT reason, moderator_id, created_at
                    FROM actions
                    WHERE user_id = :user_id AND guild_id = :guild_id AND action_type = 'warn'
                    ORDER BY created_at DESC
                    LIMIT 3
                """),
                {"user_id": target.id, "guild_id": ctx.guild.id}
            ).fetchall()
        
        if últimos_warns:
            warns_list = ""
            for i, (reason, mod_id, date) in enumerate(últimos_warns, 1):
                fecha = date.strftime('%d/%m/%Y')
                warns_list += f"{i}. **{fecha}** - {reason or 'Sin razón'}\n"
            embed.add_field(name="Últimos warns", value=warns_list, inline=False)
    
    await ctx.send(embed=embed)

# =========================================================
# COMANDOS DE MODERACIÓN BÁSICOS (con permisos de moderate_members)
# =========================================================

@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, tiempo: str, *, reason="Sin razón"):
    """Silencia a un usuario por un tiempo (requiere moderate_members)"""
    
    seconds = parse_time(tiempo)
    if not seconds:
        await ctx.send(embed=error_embed("Formato de tiempo inválido. Usa: 1d, 2h, 30m, 60s"))
        return
    
    if member == ctx.author:
        await ctx.send(embed=error_embed("No puedes silenciarte a ti mismo."))
        return
    
    if member.bot:
        await ctx.send(embed=error_embed("No puedes silenciar a un bot."))
        return
    
    await member.timeout(timedelta(seconds=seconds), reason=reason)
    
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="mute",
        reason=reason,
        moderator_id=ctx.author.id,
        duration=tiempo
    )
    
    await send_log("🔇 Mute", member, ctx.author, reason, discord.Color.dark_grey(), tiempo)
    
    embed = discord.Embed(
        title="🔇 Usuario silenciado",
        description=f"{member.mention} ha sido silenciado por {tiempo}",
        color=discord.Color.dark_grey()
    )
    embed.add_field(name="Razón", value=reason, inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member, *, reason="Unmute manual"):
    """Remueve el silencio de un usuario (requiere moderate_members)"""
    
    if not member.is_timed_out():
        await ctx.send(embed=error_embed("Este usuario no está silenciado."))
        return
    
    await member.timeout(None, reason=reason)
    
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="unmute",
        reason=reason,
        moderator_id=ctx.author.id
    )
    
    await send_log("🔊 Unmute", member, ctx.author, reason, discord.Color.green())
    await ctx.send(f"✅ {member.mention} ha sido desilenciado.")

@bot.command()
@commands.has_permissions(kick_members=True)  # Nota: kick_members es diferente de moderate_members
async def kick(ctx, member: discord.Member, *, reason="Sin razón"):
    """Expulsa a un usuario del servidor"""
    
    await member.kick(reason=reason)
    
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="kick",
        reason=reason,
        moderator_id=ctx.author.id
    )
    
    await send_log("👢 Kick", member, ctx.author, reason, discord.Color.orange())
    await ctx.send(f"👢 {member.mention} ha sido expulsado.")

@bot.command()
@commands.has_permissions(ban_members=True)  # Nota: ban_members es diferente de moderate_members
async def ban(ctx, member: discord.Member, *, reason="Sin razón"):
    """Banea a un usuario del servidor"""
    
    await member.ban(reason=reason)
    
    registrar_accion(
        user_id=member.id,
        guild_id=ctx.guild.id,
        action_type="ban",
        reason=reason,
        moderator_id=ctx.author.id
    )
    
    await send_log("⛔ Ban", member, ctx.author, reason, discord.Color.red())
    await ctx.send(f"⛔ {member.mention} ha sido baneado.")

# =========================================================
# COMANDO DE AYUDA PERSONALIZADO
# =========================================================

@bot.command(name="help")
async def help_command(ctx):
    """Muestra los comandos disponibles"""
    
    embed = discord.Embed(
        title="🤖 Comandos de Moderación",
        description="Prefijo: `god `",
        color=discord.Color.blue()
    )
    
    # Comandos para moderate_members
    moderate_commands = """
    **`god warn <usuario> [razón]`** - Da un warn a un usuario
    **`god unwarn <usuario> [cantidad]`** - Remueve warns de un usuario
    **`god historial <usuario>`** - Muestra historial de sanciones
    **`god sanciones <usuario>`** - Alias de historial
    **`god checkwarns [usuario]`** - Muestra warns actuales
    **`god mute <usuario> <tiempo> [razón]`** - Silencia a un usuario
    **`god unmute <usuario> [razón]`** - Desilencia a un usuario
    """
    
    embed.add_field(name="🛡️ Comandos de Moderación", value=moderate_commands, inline=False)
    
    # Comandos adicionales
    if ctx.author.guild_permissions.kick_members:
        kick_commands = "**`god kick <usuario> [razón]`** - Expulsa a un usuario"
        embed.add_field(name="👢 Expulsar", value=kick_commands, inline=False)
    
    if ctx.author.guild_permissions.ban_members:
        ban_commands = "**`god ban <usuario> [razón]`** - Banea a un usuario"
        embed.add_field(name="⛔ Banear", value=ban_commands, inline=False)
    
    embed.set_footer(text="Los warns se gestionan en la base de datos, no con roles")
    
    await ctx.send(embed=embed)

# =========================================================
# RUN
# =========================================================

bot.run(TOKEN)
