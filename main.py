import discord
from discord.ext import commands
import os, re, asyncio
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

# =========================================================
# CONFIGURACIÓN
# =========================================================

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Falta el TOKEN del bot")

# Configuración de la base de datos
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "discord_bot")

# Canales y IDs
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0"))
WARN_ACTION_CHANNEL = int(os.getenv("WARN_ACTION_CHANNEL", "0"))

# =========================================================
# INICIALIZACIÓN DEL BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="god ",
    intents=intents,
    help_command=None  # Deshabilitar help por defecto
)

# =========================================================
# CONEXIÓN A LA BASE DE DATOS
# =========================================================

try:
    engine = create_engine(
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        pool_pre_ping=True,
        pool_recycle=280
    )
    print("✅ Conexión a la base de datos configurada")
except Exception as e:
    print(f"❌ Error al conectar a la base de datos: {e}")
    engine = create_engine('sqlite:///bot.db')
    print("✅ Usando SQLite como base de datos alternativa")

# =========================================================
# FUNCIONES DE BASE DE DATOS
# =========================================================

def init_db():
    """Inicializa las tablas en la base de datos"""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_guild (user_id, guild_id)
            )
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_warns (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                total_warns INT DEFAULT 0,
                last_warn_date TIMESTAMP NULL,
                UNIQUE KEY unique_user_guild (user_id, guild_id)
            )
        """))
    print("✅ Base de datos inicializada")

def registrar_accion(user_id, guild_id, action_type, reason, moderator_id, duration=None):
    """Registra una acción en la base de datos"""
    try:
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
        return True
    except Exception as e:
        print(f"❌ Error al registrar acción: {e}")
        return False

def contar_warns(user_id, guild_id):
    """Cuenta los warns de un usuario"""
    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    SELECT total_warns FROM user_warns
                    WHERE user_id = :user_id AND guild_id = :guild_id
                """),
                {"user_id": user_id, "guild_id": guild_id}
            ).fetchone()
            return result[0] if result else 0
    except Exception as e:
        print(f"❌ Error al contar warns: {e}")
        return 0

def obtener_historial(user_id, guild_id, limit=10):
    """Obtiene el historial de un usuario"""
    try:
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
    except Exception as e:
        print(f"❌ Error al obtener historial: {e}")
        return []

def reset_warns(user_id, guild_id):
    """Resetea los warns de un usuario"""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM user_warns
                    WHERE user_id = :user_id AND guild_id = :guild_id
                """),
                {"user_id": user_id, "guild_id": guild_id}
            )
        return True
    except Exception as e:
        print(f"❌ Error al resetear warns: {e}")
        return False

# =========================================================
# UTILIDADES
# =========================================================

def parse_time(text):
    """Convierte texto de tiempo a segundos"""
    match = re.match(r"(\d+)([smhd])", text.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 1)

async def send_log(title, member, moderator, reason, color, duration=None):
    """Envía un log al canal correspondiente"""
    try:
        channel = bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            print(f"❌ No se encontró el canal de logs: {LOG_CHANNEL_ID}")
            return
        
        embed = discord.Embed(title=title, color=color, timestamp=datetime.utcnow())
        embed.add_field(name="👤 Usuario", value=f"{member.mention}\nID: `{member.id}`", inline=True)
        embed.add_field(name="🛡️ Moderador", value=f"{moderator.mention}\nID: `{moderator.id}`", inline=True)
        embed.add_field(name="📝 Razón", value=reason[:1024] if reason else "No especificada", inline=False)
        
        if duration:
            embed.add_field(name="⏱️ Duración", value=duration, inline=True)
        
        await channel.send(embed=embed)
    except Exception as e:
        print(f"❌ Error al enviar log: {e}")

def create_embed(title, description, color):
    """Crea un embed básico"""
    return discord.Embed(title=title, description=description, color=color)

def tiene_permisos_moderacion(member):
    """Verifica si un miembro tiene permisos de moderación"""
    return (
        member.guild_permissions.administrator or
        member.guild_permissions.moderate_members or
        member.guild_permissions.kick_members or
        member.guild_permissions.ban_members or
        member.guild_permissions.manage_messages
    )

# =========================================================
# EVENTOS
# =========================================================

@bot.event
async def on_ready():
    """Evento cuando el bot está listo"""
    print(f"✅ Bot conectado como {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print(f"👥 Conectado a {len(bot.guilds)} servidores")
    
    init_db()
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="los warns de los usuarios"
        )
    )

# =========================================================
# COMANDOS DE MODERACIÓN
# =========================================================

@bot.command()
async def warn(ctx, member: discord.Member = None, *, reason="No se especificó razón"):
    """Da un warn a un usuario"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.\n"
            "Permisos válidos: **Moderate Members**, **Kick Members**, **Ban Members**, **Manage Messages** o **Administrator**",
            discord.Color.red()
        ))
        return
    
    if member is None:
        await ctx.send(embed=create_embed(
            "❌ Usuario requerido",
            f"Debes mencionar a un usuario.\nUso: `{ctx.prefix}warn @usuario [razón]`",
            discord.Color.red()
        ))
        return
    
    if member == ctx.author:
        await ctx.send(embed=create_embed("❌ Error", "No puedes advertirte a ti mismo.", discord.Color.red()))
        return
    
    if member.bot:
        await ctx.send(embed=create_embed("❌ Error", "No puedes advertir a un bot.", discord.Color.red()))
        return
    
    # Verificar jerarquía (excepto para el owner)
    if ctx.author.id != ctx.guild.owner_id:
        if member.top_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes advertir a {member.mention} porque tiene un rol igual o superior al tuyo.",
                discord.Color.red()
            ))
            return
    
    registrar_accion(
        member.id, ctx.guild.id, "warn", 
        reason, ctx.author.id
    )
    
    warns = contar_warns(member.id, ctx.guild.id)
    
    await send_log(
        "⚠️ Warn Aplicado",
        member, ctx.author, reason,
        discord.Color.orange()
    )
    
    embed = create_embed(
        "⚠️ Warn Registrado",
        f"{member.mention} ha recibido una advertencia.\n\n"
        f"**Razón:** {reason}\n"
        f"**Warns actuales:** {warns}/3",
        discord.Color.orange()
    )
    await ctx.send(embed=embed)
    
    if warns >= 3:
        action_channel = bot.get_channel(WARN_ACTION_CHANNEL) if WARN_ACTION_CHANNEL else ctx.channel
        if action_channel:
            await action_channel.send(
                embed=create_embed(
                    "🚨 ¡Alerta! 3 Warns",
                    f"{member.mention} ha alcanzado **3 warns**.\n"
                    "Se recomienda revisar el caso y aplicar una sanción correspondiente.",
                    discord.Color.red()
                )
            )

@bot.command()
async def unwarn(ctx, member: discord.Member = None, cantidad: int = 1):
    """Remueve warns de un usuario"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.",
            discord.Color.red()
        ))
        return
    
    if member is None:
        await ctx.send(embed=create_embed(
            "❌ Usuario requerido",
            f"Debes mencionar a un usuario.\nUso: `{ctx.prefix}unwarn @usuario [cantidad]`",
            discord.Color.red()
        ))
        return
    
    warns_actuales = contar_warns(member.id, ctx.guild.id)
    
    if warns_actuales == 0:
        await ctx.send(embed=create_embed("ℹ️ Información", f"{member.mention} no tiene warns.", discord.Color.blue()))
        return
    
    if cantidad > warns_actuales:
        cantidad = warns_actuales
    
    reset_warns(member.id, ctx.guild.id)
    nuevo_total = warns_actuales - cantidad
    
    if nuevo_total > 0:
        registrar_accion(
            member.id, ctx.guild.id, "unwarn", 
            f"Se removieron {cantidad} warns, quedan {nuevo_total}", 
            ctx.author.id
        )
    
    embed = create_embed(
        "✅ Warns Removidos",
        f"Se han removido **{cantidad}** warn(s) de {member.mention}\n"
        f"**Anteriores:** {warns_actuales}\n"
        f"**Actuales:** {nuevo_total}",
        discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="historial")
async def historial(ctx, member: discord.Member = None):
    """Muestra el historial de un usuario"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.",
            discord.Color.red()
        ))
        return
    
    if member is None:
        await ctx.send(embed=create_embed(
            "❌ Usuario requerido",
            f"Debes mencionar a un usuario.\nUso: `{ctx.prefix}historial @usuario`",
            discord.Color.red()
        ))
        return
    
    acciones = obtener_historial(member.id, ctx.guild.id)
    warns = contar_warns(member.id, ctx.guild.id)
    
    if not acciones:
        await ctx.send(embed=create_embed(
            "📄 Historial Vacío",
            f"{member.mention} no tiene historial de sanciones.",
            discord.Color.blue()
        ))
        return
    
    embed = discord.Embed(
        title=f"📄 Historial de {member}",
        description=f"**Warns actuales:** {warns}/3",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    for i, (action, reason, mod_id, duration, fecha) in enumerate(acciones, 1):
        fecha_str = fecha.strftime('%d/%m/%Y %H:%M')
        value = f"**Razón:** {reason or 'Sin razón'}\n"
        value += f"**Fecha:** {fecha_str}\n"
        if duration:
            value += f"**Duración:** {duration}\n"
        if mod_id:
            value += f"**Moderador:** <@{mod_id}>"
        
        embed.add_field(
            name=f"{i}. {action.upper()}",
            value=value,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command()
async def mute(ctx, member: discord.Member = None, tiempo: str = None, *, reason="Sin razón"):
    """Silencia a un usuario temporalmente"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.",
            discord.Color.red()
        ))
        return
    
    if member is None or tiempo is None:
        await ctx.send(embed=create_embed(
            "❌ Argumentos faltantes",
            f"Uso correcto: `{ctx.prefix}mute @usuario <tiempo> [razón]`\n"
            "Ejemplo: `god mute @usuario 1h Spam`",
            discord.Color.red()
        ))
        return
    
    if member == ctx.author:
        await ctx.send(embed=create_embed(
            "❌ Error",
            "No puedes silenciarte a ti mismo.",
            discord.Color.red()
        ))
        return
    
    if member.bot:
        await ctx.send(embed=create_embed(
            "❌ Error",
            "No puedes silenciar a un bot.",
            discord.Color.red()
        ))
        return
    
    # Verificar jerarquía de roles (excepto para el owner)
    if ctx.author.id != ctx.guild.owner_id:
        if member.top_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes silenciar a {member.mention} porque tiene un rol igual o superior al tuyo.",
                discord.Color.red()
            ))
            return
    
    # Verificar que el bot pueda silenciar al usuario
    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send(embed=create_embed(
            "❌ Error de Jerarquía del Bot",
            f"No puedo silenciar a {member.mention} porque tiene un rol igual o superior al mío.\n"
            "Mueve mi rol más arriba en la jerarquía.",
            discord.Color.red()
        ))
        return
    
    seconds = parse_time(tiempo)
    if not seconds:
        await ctx.send(embed=create_embed(
            "❌ Error",
            "Formato de tiempo inválido. Usa: `1d` (días), `2h` (horas), `30m` (minutos), `60s` (segundos)",
            discord.Color.red()
        ))
        return
    
    # Verificar que el tiempo no exceda el máximo permitido (28 días)
    if seconds > 2419200:  # 28 días en segundos
        await ctx.send(embed=create_embed(
            "❌ Error",
            "El tiempo máximo de silencio es de 28 días.",
            discord.Color.red()
        ))
        return
    
    try:
        await member.timeout(timedelta(seconds=seconds), reason=reason)
        
        registrar_accion(
            member.id, ctx.guild.id, "mute",
            reason, ctx.author.id, tiempo
        )
        
        await send_log(
            "🔇 Usuario Silenciado",
            member, ctx.author, reason,
            discord.Color.dark_gray(), tiempo
        )
        
        await ctx.send(embed=create_embed(
            "🔇 Mute Aplicado",
            f"{member.mention} ha sido silenciado por {tiempo}.\n"
            f"**Razón:** {reason}",
            discord.Color.dark_gray()
        ))
    except discord.Forbidden:
        await ctx.send(embed=create_embed(
            "❌ Error de Permisos",
            "No tengo permisos para silenciar a este usuario.\n"
            "Asegúrate de que:\n"
            "• El bot tiene el permiso **Aislar miembros**\n"
            "• El rol del bot está por encima del rol del usuario\n"
            "• El usuario no es el dueño del servidor",
            discord.Color.red()
        ))
    except Exception as e:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"No se pudo silenciar al usuario: {str(e)}",
            discord.Color.red()
        ))

@bot.command()
async def unmute(ctx, member: discord.Member = None):
    """Remueve el silencio de un usuario"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.",
            discord.Color.red()
        ))
        return
    
    if member is None:
        await ctx.send(embed=create_embed(
            "❌ Usuario requerido",
            f"Debes mencionar a un usuario.\nUso: `{ctx.prefix}unmute @usuario`",
            discord.Color.red()
        ))
        return
    
    if not member.is_timed_out():
        await ctx.send(embed=create_embed(
            "ℹ️ Información",
            f"{member.mention} no está silenciado.",
            discord.Color.blue()
        ))
        return
    
    try:
        await member.timeout(None, reason="Unmute manual")
        
        registrar_accion(
            member.id, ctx.guild.id, "unmute",
            "Unmute manual", ctx.author.id
        )
        
        await send_log(
            "🔊 Usuario Desilenciado",
            member, ctx.author, "Unmute manual",
            discord.Color.green()
        )
        
        await ctx.send(embed=create_embed(
            "✅ Unmute Aplicado",
            f"{member.mention} ha sido desilenciado.",
            discord.Color.green()
        ))
    except Exception as e:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"No se pudo desilenciar al usuario: {str(e)}",
            discord.Color.red()
        ))

@bot.command(name="checkwarns")
async def checkwarns(ctx, member: discord.Member = None):
    """Revisa los warns de un usuario"""
    # Verificar permisos
    if not tiene_permisos_moderacion(ctx.author):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas permisos de moderación para usar este comando.",
            discord.Color.red()
        ))
        return
    
    target = member or ctx.author
    warns = contar_warns(target.id, ctx.guild.id)
    
    color = discord.Color.red() if warns >= 3 else discord.Color.orange() if warns > 0 else discord.Color.green()
    
    embed = discord.Embed(
        title=f"⚠️ Warns de {target}",
        color=color
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Warns Actuales", value=f"**{warns}/3**", inline=True)
    
    if warns > 0:
        with engine.begin() as conn:
            ultimos = conn.execute(
                text("""
                    SELECT reason, created_at FROM actions
                    WHERE user_id = :user_id AND guild_id = :guild_id AND action_type = 'warn'
                    ORDER BY created_at DESC LIMIT 3
                """),
                {"user_id": target.id, "guild_id": ctx.guild.id}
            ).fetchall()
        
        if ultimos:
            detalle = "\n".join([
                f"• {i+1}. {reason} ({fecha.strftime('%d/%m/%Y')})"
                for i, (reason, fecha) in enumerate(ultimos)
            ])
            embed.add_field(name="Últimos Warns", value=detalle, inline=False)
    
    await ctx.send(embed=embed)

# =========================================================
# COMANDO DE AYUDA PERSONALIZADO
# =========================================================

@bot.command(name="ayuda")
async def ayuda(ctx):
    """Muestra la ayuda del bot"""
    embed = discord.Embed(
        title="🤖 Comandos de Moderación",
        description="Prefijo: `god `\n\n**Permisos válidos para usar los comandos:**\n• Moderate Members (Aislar miembros)\n• Kick Members\n• Ban Members\n• Manage Messages\n• Administrator",
        color=discord.Color.blue()
    )
    
    moderacion = """
    **`warn <@usuario> [razón]`** - Da una advertencia
    **`unwarn <@usuario> [cantidad]`** - Remueve advertencias
    **`checkwarns [@usuario]`** - Revisa warns actuales
    **`historial <@usuario>`** - Muestra historial completo
    **`mute <@usuario> <tiempo> [razón]`** - Silencia temporalmente
    **`unmute <@usuario>`** - Remueve silencio
    """
    
    embed.add_field(name="🛡️ Comandos de Moderación", value=moderacion, inline=False)
    embed.add_field(name="⏱️ Formatos de tiempo", value="`1d` (días), `2h` (horas), `30m` (minutos), `60s` (segundos)", inline=False)
    embed.add_field(name="📊 Sistema de Warns", value="• Los warns se almacenan en base de datos\n• Al llegar a 3 warns se notifica\n• No se usan roles para los warns", inline=False)
    embed.add_field(name="🆘 Soporte", value="Para problemas, contacta con los administradores.", inline=False)
    
    await ctx.send(embed=embed)

# =========================================================
# MANEJO DE ERRORES
# =========================================================

@bot.event
async def on_command_error(ctx, error):
    """Maneja errores de comandos"""
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "No tienes permisos para usar este comando.\n"
            "Necesitas alguno de estos permisos: **Moderate Members**, **Kick Members**, **Ban Members**, **Manage Messages** o **Administrator**",
            discord.Color.red()
        ))
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=create_embed(
            "❌ Usuario no encontrado",
            "No se pudo encontrar al usuario mencionado.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=create_embed(
            "❌ Argumento faltante",
            f"Falta un argumento requerido.\nUso correcto: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`",
            discord.Color.red()
        ))
    elif isinstance(error, commands.CommandNotFound):
        embed = create_embed(
            "❌ Comando no encontrado",
            f"El comando `{ctx.invoked_with}` no existe.\n\nUsa `{ctx.prefix}ayuda` para ver los comandos disponibles.",
            discord.Color.red()
        )
        await ctx.send(embed=embed)
    else:
        print(f"Error no manejado: {error}")
        await ctx.send(embed=create_embed(
            "❌ Error",
            "Ha ocurrido un error inesperado.",
            discord.Color.red()
        ))

# =========================================================
# EJECUCIÓN
# =========================================================

if __name__ == "__main__":
    print("🚀 Iniciando bot...")
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Error: Token inválido. Verifica tu token de Discord.")
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
