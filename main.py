import discord
from discord.ext import commands
import os, re, asyncio, json
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from typing import Optional
from urllib.parse import quote_plus


# =========================================================
# CONFIGURACIÓN
# =========================================================

# Variables de entorno requeridas
REQUIRED_ENV_VARS = [
    "TOKEN",
    "DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME",
    "GUILD_ID",
    "LOG_CHANNEL_ID"
]

for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        raise RuntimeError(f"❌ Falta la variable de entorno: {var}")

TOKEN = os.getenv("TOKEN")

# Configuración de base de datos
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PASSWORD_ESCAPED = quote_plus(DB_PASSWORD)
DB_NAME = os.getenv("DB_NAME")

# IDs y Canales
GUILD_ID = int(os.getenv("GUILD_ID"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID"))
WARN_ACTION_CHANNEL = int(os.getenv("WARN_ACTION_CHANNEL", "0"))
PROMOTE_CHANNEL = int(os.getenv("PROMOTE_CHANNEL", "0"))
DEMOTE_CHANNEL = int(os.getenv("DEMOTE_CHANNEL", "0"))

# =========================================================
# INICIALIZACIÓN DEL BOT
# =========================================================

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="god ",
    intents=intents,
    help_command=None  # Deshabilitamos el help por defecto para usar el personalizado
)

# =========================================================
# CONEXIÓN A LA BASE DE DATOS
# =========================================================

try:
    engine = create_engine(
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD_ESCAPED}@{DB_HOST}:{DB_PORT}/{DB_NAME}",
        pool_pre_ping=True,
        pool_recycle=280
    )

    print("✅ Conexión a la base de datos configurada")
except Exception as e:
    print(f"❌ Error al conectar a la base de datos MySQL: {e}")
    # Fallback a SQLite local
    engine = create_engine('sqlite:///bot.db', pool_pre_ping=True)
    print("✅ Usando SQLite como base de datos alternativa")

# =========================================================
# FUNCIONES DE BASE DE DATOS
# =========================================================

def init_db():
    """Inicializa las tablas en la base de datos"""
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS acciones (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                tipo VARCHAR(20) NOT NULL,
                razon TEXT,
                moderator_id BIGINT,
                duracion VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_guild (user_id, guild_id),
                INDEX idx_tipo (tipo),
                INDEX idx_fecha (created_at)
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

def registrar_accion(user_id, guild_id, tipo, razon, moderator_id, duracion=None):
    """Registra una acción en la base de datos"""
    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO acciones (user_id, guild_id, tipo, razon, moderator_id, duracion)
                    VALUES (:user_id, :guild_id, :tipo, :razon, :moderator_id, :duracion)
                """),
                {
                    "user_id": user_id,
                    "guild_id": guild_id,
                    "tipo": tipo,
                    "razon": razon,
                    "moderator_id": moderator_id,
                    "duracion": duracion
                }
            )
            
            if tipo == 'warn':
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

def obtener_historial(user_id, guild_id, limit=15):
    """Obtiene el historial de un usuario"""
    try:
        with engine.begin() as conn:
            acciones = conn.execute(
                text("""
                    SELECT tipo, razon, moderator_id, duracion, created_at
                    FROM acciones
                    WHERE user_id = :user_id AND guild_id = :guild_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"user_id": user_id, "guild_id": guild_id, "limit": limit}
            ).fetchall()
            
            # Convertir a lista de diccionarios
            return [
                {
                    "tipo": tipo,
                    "razon": razon,
                    "moderator_id": moderator_id,
                    "duracion": duracion,
                    "fecha": created_at
                }
                for tipo, razon, moderator_id, duracion, created_at in acciones
            ]
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

def obtener_acciones_por_tipo(user_id, guild_id, tipo):
    """Obtiene acciones específicas por tipo"""
    try:
        with engine.begin() as conn:
            acciones = conn.execute(
                text("""
                    SELECT tipo, razon, moderator_id, duracion, created_at
                    FROM acciones
                    WHERE user_id = :user_id AND guild_id = :guild_id AND tipo = :tipo
                    ORDER BY created_at DESC
                """),
                {"user_id": user_id, "guild_id": guild_id, "tipo": tipo}
            ).fetchall()
            
            return [
                {
                    "tipo": tipo_db,
                    "razon": razon,
                    "moderator_id": moderator_id,
                    "duracion": duracion,
                    "fecha": created_at
                }
                for tipo_db, razon, moderator_id, duracion, created_at in acciones
            ]
    except Exception as e:
        print(f"❌ Error al obtener acciones por tipo: {e}")
        return []

# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def parse_time(text):
    """Convierte texto de tiempo a segundos"""
    match = re.match(r"(\d+)([smhd])", text.lower())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return value * multipliers.get(unit, 1)

def tiempo_formato(seconds):
    """Convierte segundos a formato legible"""
    if seconds >= 86400:
        return f"{seconds // 86400}d"
    elif seconds >= 3600:
        return f"{seconds // 3600}h"
    elif seconds >= 60:
        return f"{seconds // 60}m"
    else:
        return f"{seconds}s"

def create_embed(title, description="", color=discord.Color.blue()):
    """Crea un embed básico"""
    embed = discord.Embed(title=title, description=description, color=color)
    return embed

def tiene_permisos_moderacion(member):
    """Verifica si un miembro tiene permisos de moderación"""
    return (
        member.guild_permissions.administrator or
        member.guild_permissions.moderate_members or
        member.guild_permissions.kick_members or
        member.guild_permissions.ban_members or
        member.guild_permissions.manage_messages or
        member.guild_permissions.manage_roles
    )

async def notify_user_dm(user, action_type, reason, duration=None, moderator=None):
    """Envía notificación por DM al usuario afectado"""
    if isinstance(user, discord.Member) and user.bot:
        return False
    
    try:
        embed = discord.Embed(
            title=f"🔔 Notificación del servidor",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )
        
        # Mapear tipos de acción a mensajes amigables
        action_titles = {
            "warn": "⚠️ Has recibido una advertencia",
            "mute": "🔇 Has sido silenciado temporalmente",
            "ban": "🚫 Has sido baneado del servidor",
            "kick": "👢 Has sido expulsado del servidor",
            "promote": "🎉 ¡Felicidades! Has sido promovido",
            "demote": "🔻 Has sido degradado de rango",
            "unmute": "🔊 Tu silencio ha sido removido"
        }
        
        guild_name = bot.get_guild(GUILD_ID).name if bot.get_guild(GUILD_ID) else "el servidor"
        embed.description = action_titles.get(action_type, f"Acción: {action_type}") + f" en **{guild_name}**"
        
        if reason:
            embed.add_field(name="📝 Razón", value=reason, inline=False)
        
        if duration:
            embed.add_field(name="⏱️ Duración", value=duration, inline=True)
        
        if moderator and isinstance(moderator, discord.Member):
            embed.add_field(name="👤 Moderador", value=f"{moderator.name}", inline=True)
        
        embed.set_footer(text="Notificación automática del sistema")
        
        if isinstance(user, discord.Member):
            await user.send(embed=embed)
        elif isinstance(user, discord.User):
            await user.send(embed=embed)
        
        return True
    except discord.Forbidden:
        # El usuario tiene DMs desactivados
        return False
    except Exception as e:
        print(f"Error enviando DM: {e}")
        return False

async def send_log_detailed(action, member, moderator, reason, color, duration=None, extra_fields=None):
    """Sistema de logs mejorado con más detalles"""
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        print(f"❌ No se encontró el canal de logs: {LOG_CHANNEL_ID}")
        return
    
    # Mapear emojis según tipo de acción
    emoji_map = {
        "warn": "⚠️",
        "mute": "🔇",
        "ban": "🚫",
        "kick": "👢",
        "unmute": "🔊",
        "unban": "♻️",
        "promote": "🎉",
        "demote": "🔻",
        "unwarn": "✅"
    }
    
    emoji = emoji_map.get(action.lower(), "📝")
    
    embed = discord.Embed(
        title=f"{emoji} {action}",
        color=color,
        timestamp=datetime.utcnow()
    )
    
    # Configurar thumbnail con avatar del usuario
    if member and hasattr(member, 'display_avatar') and member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    
    # Campos básicos
    if member:
        embed.add_field(name="👤 Usuario", 
                       value=f"{member.mention}\nID: `{member.id}`", 
                       inline=False)
    
    if moderator:
        embed.add_field(name="🛡️ Moderador", 
                       value=f"{moderator.mention}\nID: `{moderator.id}`", 
                       inline=False)
    
    if reason:
        # Limitar la longitud de la razón si es muy larga
        razon_display = reason[:1000] + "..." if len(reason) > 1000 else reason
        embed.add_field(name="📄 Razón", value=razon_display, inline=False)
    
    if duration:
        embed.add_field(name="⏳ Duración", value=duration, inline=True)
    
    # Campos adicionales
    if extra_fields and isinstance(extra_fields, dict):
        for name, value in extra_fields.items():
            if value:
                embed.add_field(name=name, value=str(value)[:500], inline=False)
    
    # Footer con información contextual
    embed.set_footer(text=f"ID: {member.id if member else 'N/A'} • Sistema de moderación")
    
    await channel.send(embed=embed)

async def check_3_warns(member, moderator):
    """Verifica si un usuario tiene 3 warns y notifica"""
    warns = contar_warns(member.id, member.guild.id)
    
    if warns >= 3:
        channel = bot.get_channel(WARN_ACTION_CHANNEL) if WARN_ACTION_CHANNEL else bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            return
            
        # Obtener historial de warns
        warns_acciones = obtener_acciones_por_tipo(member.id, member.guild.id, "warn")
        
        embed = discord.Embed(
            title="🚨 ¡Alerta! Usuario con 3 advertencias",
            description=(
                f"El usuario {member.mention} (`{member.id}`) ha alcanzado **3 advertencias**.\n"
                f"**Por favor, revisa el caso y aplica una sanción apropiada.**"
            ),
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        
        # Añadir resumen de las últimas advertencias
        if warns_acciones:
            historial_text = ""
            for i, accion in enumerate(warns_acciones[:3], 1):
                fecha_str = accion['fecha'].strftime("%d/%m/%Y %H:%M")
                razon_corta = accion['razon'][:80] + "..." if len(accion['razon']) > 80 else accion['razon']
                historial_text += f"**#{i}** - {razon_corta}\n"
                historial_text += f"`Mod: <@{accion['moderator_id']}> | {fecha_str}`\n\n"
            
            embed.add_field(
                name="📜 Últimas advertencias",
                value=historial_text,
                inline=False
            )
        
        # Estadísticas del usuario
        total_acciones = len(obtener_historial(member.id, member.guild.id, limit=50))
        
        embed.add_field(name="📊 Estadísticas", 
                       value=f"**Total acciones registradas:** {total_acciones}\n"
                             f"**Warns actuales:** {warns}", 
                       inline=True)
        
        embed.add_field(name="👤 Información del usuario",
                       value=f"**Unido:** {member.joined_at.strftime('%d/%m/%Y') if member.joined_at else 'N/A'}\n"
                             f"**Cuenta creada:** {member.created_at.strftime('%d/%m/%Y')}",
                       inline=True)
        
        embed.set_footer(text=f"ID: {member.id} | Notificación automática")
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await channel.send(embed=embed)

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
            name="god help | Sistema de moderación"
        )
    )

# =========================================================
# COMANDOS DE MODERACIÓN
# =========================================================

@bot.command(name="warn")
async def warn_command(ctx, member: discord.Member, *, reason: str = "No se especificó razón"):

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
    
    # Registrar warn en la base de datos
    registrar_accion(
        member.id, ctx.guild.id, "warn", 
        reason, ctx.author.id
    )
    
    warns = contar_warns(member.id, ctx.guild.id)
    
    # Enviar log detallado
    await send_log_detailed(
        "Warn Aplicado",
        member, ctx.author, reason,
        discord.Color.orange()
    )
    
    # Notificar al usuario por DM
    await notify_user_dm(member, "warn", reason, moderator=ctx.author)
    
    # Enviar confirmación al canal
    embed = create_embed(
        "⚠️ Warn Registrado",
        f"{member.mention} ha recibido una advertencia.\n\n"
        f"**Razón:** {reason}\n"
        f"**Warns actuales:** {warns}/3",
        discord.Color.orange()
    )
    await ctx.send(embed=embed)
    
    # Verificar si tiene 3 warns
    if warns >= 3:
        await check_3_warns(member, ctx.author)

@bot.command(name="unwarn")
async def unwarn_command(ctx, member: discord.Member = None, cantidad: int = 1):
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
    
    # Registrar la acción de unwarn
    registrar_accion(
        member.id, ctx.guild.id, "unwarn", 
        f"Se removieron {cantidad} warns (anterior: {warns_actuales})", 
        ctx.author.id
    )
    
    # Actualizar contador en la base de datos
    if cantidad == warns_actuales:
        reset_warns(member.id, ctx.guild.id)
        nuevo_total = 0
    else:
        # Para reducir parcialmente, necesitamos un enfoque diferente
        # Por simplicidad, resetamos y reajustamos
        reset_warns(member.id, ctx.guild.id)
        nuevo_total = max(0, warns_actuales - cantidad)
        
        # Si todavía hay warns, actualizar contador
        if nuevo_total > 0:
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO user_warns (user_id, guild_id, total_warns, last_warn_date)
                        VALUES (:user_id, :guild_id, :total_warns, NOW())
                    """),
                    {"user_id": member.id, "guild_id": ctx.guild.id, "total_warns": nuevo_total}
                )
    
    # Enviar log
    await send_log_detailed(
        "Warns Removidos",
        member, ctx.author, 
        f"Se removieron {cantidad} warns. Quedan {nuevo_total}",
        discord.Color.green()
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
async def historial_command(ctx, member: discord.Member = None):
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
    
    acciones = obtener_historial(member.id, ctx.guild.id, limit=10)
    warns = contar_warns(member.id, ctx.guild.id)
    
    if not acciones:
        await ctx.send(embed=create_embed(
            "📄 Historial Vacío",
            f"{member.mention} no tiene historial de acciones registradas.",
            discord.Color.blue()
        ))
        return
    
    # Contar acciones por tipo
    contadores = {}
    for accion in acciones:
        tipo = accion['tipo']
        contadores[tipo] = contadores.get(tipo, 0) + 1
    
    # Crear descripción con contadores
    descripcion = f"**Total acciones:** {len(acciones)}\n"
    descripcion += f"**Warns actuales:** {warns}/3\n\n"
    
    for tipo, count in contadores.items():
        descripcion += f"**{tipo.title()}:** {count}\n"
    
    embed = discord.Embed(
        title=f"📄 Historial de {member.name}",
        description=descripcion,
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    # Emoji mapping para tipos de acción
    emoji_map = {
        "warn": "⚠️",
        "mute": "🔇",
        "ban": "🚫",
        "kick": "👢",
        "unmute": "🔊",
        "unban": "♻️",
        "promote": "🎉",
        "demote": "🔻",
        "unwarn": "✅"
    }
    
    # Mostrar las últimas 5 acciones en detalle
    for i, accion in enumerate(acciones[:5], 1):
        tipo = accion['tipo']
        fecha = accion['fecha'].strftime('%d/%m/%Y %H:%M')
        emoji = emoji_map.get(tipo, "📝")
        
        field_value = f"**Razón:** {accion['razon'] or 'Sin razón especificada'}\n"
        if accion['duracion']:
            field_value += f"**Duración:** {accion['duracion']}\n"
        if accion['moderator_id']:
            field_value += f"**Moderador:** <@{accion['moderator_id']}>\n"
        field_value += f"**Fecha:** {fecha}"
        
        embed.add_field(
            name=f"{i}. {emoji} {tipo.title()}",
            value=field_value,
            inline=False
        )
    
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id} | Mostrando {len(acciones[:5])} de {len(acciones)} acciones")
    
    await ctx.send(embed=embed)

@bot.command(name="mute")
async def mute_command(ctx, member: discord.Member = None, tiempo: str = None, *, reason="Sin razón"):
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
            "Ejemplo: `god mute @usuario 1h Spam`\n"
            "Formatos: `1d` (días), `2h` (horas), `30m` (minutos), `60s` (segundos)",
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
        
        # Registrar en base de datos
        registrar_accion(
            member.id, ctx.guild.id, "mute",
            reason, ctx.author.id, tiempo
        )
        
        # Enviar log detallado
        await send_log_detailed(
            "Usuario Silenciado",
            member, ctx.author, reason,
            discord.Color.dark_gray(), tiempo
        )
        
        # Notificar al usuario por DM
        await notify_user_dm(member, "mute", reason, tiempo, ctx.author)
        
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

@bot.command(name="unmute")
async def unmute_command(ctx, member: discord.Member = None):
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
        
        await send_log_detailed(
            "Usuario Desilenciado",
            member, ctx.author, "Unmute manual",
            discord.Color.green()
        )
        
        # Notificar al usuario por DM
        await notify_user_dm(member, "unmute", "Tu silencio ha sido removido", moderator=ctx.author)
        
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
async def checkwarns_command(ctx, member: discord.Member = None):
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
    
    # Determinar color según número de warns
    if warns >= 3:
        color = discord.Color.red()
        estado = "🚨 **ALTO RIESGO** (3 o más warns)"
    elif warns > 0:
        color = discord.Color.orange()
        estado = "⚠️ **ADVERTENCIA**"
    else:
        color = discord.Color.green()
        estado = "✅ **SIN WARNS**"
    
    embed = discord.Embed(
        title=f"⚠️ Warns de {target.name}",
        color=color,
        timestamp=datetime.utcnow()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Warns Actuales", value=f"**{warns}/3**", inline=True)
    embed.add_field(name="Estado", value=estado, inline=True)
    
    if warns > 0:
        # Obtener últimos warns
        warns_acciones = obtener_acciones_por_tipo(target.id, ctx.guild.id, "warn")
        
        if warns_acciones:
            ultimos_text = ""
            for i, accion in enumerate(warns_acciones[:3], 1):
                fecha = accion['fecha'].strftime('%d/%m/%Y')
                razon_corta = accion['razon'][:50] + "..." if len(accion['razon']) > 50 else accion['razon']
                ultimos_text += f"**#{i}** - {razon_corta}\n"
                ultimos_text += f"`Fecha: {fecha} | Mod: <@{accion['moderator_id']}>`\n\n"
            
            embed.add_field(name="Últimos Warns", value=ultimos_text, inline=False)
        
        # Calcular días desde el último warn
        if warns_acciones:
            ultima_fecha = warns_acciones[0]['fecha']
            dias_desde = (datetime.utcnow() - ultima_fecha).days
            embed.add_field(name="Días desde último warn", value=f"{dias_desde} días", inline=True)
    
    # Información adicional del usuario
    embed.add_field(name="👤 Información", 
                   value=f"**ID:** {target.id}\n"
                         f"**Unido:** {target.joined_at.strftime('%d/%m/%Y') if target.joined_at else 'N/A'}",
                   inline=False)
    
    embed.set_footer(text=f"Solicitado por {ctx.author}", icon_url=ctx.author.display_avatar.url)
    
    await ctx.send(embed=embed)

# =========================================================
# COMANDOS DE GESTIÓN DE ROLES (PROMOTE/DEMOTE)
# =========================================================

@bot.command(name="promote")
async def promote_command(ctx, member: discord.Member = None, old_role: discord.Role = None, 
                          new_role: discord.Role = None, *, reason="Sin razón especificada"):
    """Promueve a un usuario a un rango superior"""
    # Verificar permisos
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas el permiso **Gestionar Roles** para usar este comando.",
            discord.Color.red()
        ))
        return
    
    # Verificar argumentos
    if not member or not old_role or not new_role:
        await ctx.send(embed=create_embed(
            "❌ Uso incorrecto",
            f"Uso: `{ctx.prefix}promote @usuario @rango_anterior @nuevo_rango [razón]`\n\n"
            "**Ejemplo:**\n"
            f"`{ctx.prefix}promote @Usuario @Novato @Experto Por buen desempeño`\n"
            f"`{ctx.prefix}promote @Usuario @Miembro @Veterano Actividad destacada`",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario existe en el servidor
    if not member.guild == ctx.guild:
        await ctx.send(embed=create_embed("❌ Error", "El usuario no está en este servidor.", discord.Color.red()))
        return
    
    # Verificar jerarquía del autor (excepto owner)
    if ctx.author.id != ctx.guild.owner_id:
        if member.top_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes promover a {member.mention} porque tiene un rol igual o superior al tuyo.",
                discord.Color.red()
            ))
            return
        
        if new_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes asignar el rol {new_role.mention} porque es igual o superior al tuyo.",
                discord.Color.red()
            ))
            return
    
    # Verificar jerarquía del bot
    if new_role >= ctx.guild.me.top_role:
        await ctx.send(embed=create_embed(
            "❌ Error de Jerarquía del Bot",
            f"No puedo asignar el rol {new_role.mention} porque es igual o superior al mío.\n"
            "Por favor, mueve mi rol más arriba en la jerarquía de roles.",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario tiene el rol antiguo
    if old_role not in member.roles:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"{member.mention} no tiene el rol {old_role.mention}.",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario no tenga ya el nuevo rol
    if new_role in member.roles:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"{member.mention} ya tiene el rol {new_role.mention}.",
            discord.Color.red()
        ))
        return
    
    try:
        # Realizar la promoción
        await member.remove_roles(old_role)
        await member.add_roles(new_role)
        
        # Registrar en base de datos
        razon_completa = f"{reason} (De {old_role.name} a {new_role.name})"
        registrar_accion(
            member.id, ctx.guild.id, "promote",
            razon_completa, ctx.author.id
        )
        
        # Enviar log detallado
        await send_log_detailed(
            "Promoción de Usuario",
            member, ctx.author, razon_completa,
            discord.Color.gold(),
            extra_fields={
                "Rango Anterior": old_role.name,
                "Nuevo Rango": new_role.name
            }
        )
        
        # Enviar al canal específico si está configurado
        if PROMOTE_CHANNEL:
            channel = bot.get_channel(PROMOTE_CHANNEL)
            if channel:
                promo_embed = discord.Embed(
                    title="🎉 ¡Nueva Promoción!",
                    description=f"¡Felicidades {member.mention}! Has sido ascendido.",
                    color=discord.Color.gold(),
                    timestamp=datetime.utcnow()
                )
                promo_embed.add_field(name="Rango Anterior", value=old_role.mention, inline=True)
                promo_embed.add_field(name="Nuevo Rango", value=new_role.mention, inline=True)
                promo_embed.add_field(name="Razón", value=reason, inline=False)
                promo_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
                promo_embed.set_thumbnail(url=member.display_avatar.url)
                promo_embed.set_footer(text=f"ID: {member.id}")
                
                await channel.send(embed=promo_embed)
        
        # Notificar al usuario por DM
        await notify_user_dm(member, "promote", 
                           f"Has sido promovido de {old_role.name} a {new_role.name}\nRazón: {reason}", 
                           moderator=ctx.author)
        
        # Confirmación en el canal
        await ctx.send(embed=create_embed(
            "✅ Promoción Exitosa",
            f"{member.mention} ha sido promovido exitosamente:\n\n"
            f"**De:** {old_role.mention}\n"
            f"**A:** {new_role.mention}\n"
            f"**Razón:** {reason}",
            discord.Color.green()
        ))
        
    except discord.Forbidden:
        await ctx.send(embed=create_embed(
            "❌ Error de Permisos",
            "No tengo permisos para gestionar estos roles.\n"
            "Asegúrate de que mi rol está por encima de los roles que intentas gestionar.",
            discord.Color.red()
        ))
    except Exception as e:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"No se pudo completar la promoción: {str(e)}",
            discord.Color.red()
        ))

@bot.command(name="demote")
async def demote_command(ctx, member: discord.Member = None, old_role: discord.Role = None,
                         new_role: discord.Role = None, *, reason="Sin razón especificada"):
    """Degrada a un usuario a un rango inferior"""
    # Verificar permisos
    if not ctx.author.guild_permissions.manage_roles:
        await ctx.send(embed=create_embed(
            "❌ Permisos Insuficientes",
            "Necesitas el permiso **Gestionar Roles** para usar este comando.",
            discord.Color.red()
        ))
        return
    
    # Verificar argumentos
    if not member or not old_role or not new_role:
        await ctx.send(embed=create_embed(
            "❌ Uso incorrecto",
            f"Uso: `{ctx.prefix}demote @usuario @rango_anterior @nuevo_rango [razón]`\n\n"
            "**Ejemplo:**\n"
            f"`{ctx.prefix}demote @Usuario @Experto @Novato Bajo rendimiento`\n"
            f"`{ctx.prefix}demote @Usuario @Veterano @Miembro Incumplimiento de reglas`",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario existe en el servidor
    if not member.guild == ctx.guild:
        await ctx.send(embed=create_embed("❌ Error", "El usuario no está en este servidor.", discord.Color.red()))
        return
    
    # Verificar jerarquía del autor (excepto owner)
    if ctx.author.id != ctx.guild.owner_id:
        if member.top_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes degradar a {member.mention} porque tiene un rol igual o superior al tuyo.",
                discord.Color.red()
            ))
            return
        
        if old_role >= ctx.author.top_role or new_role >= ctx.author.top_role:
            await ctx.send(embed=create_embed(
                "❌ Error de Jerarquía",
                f"No puedes gestionar roles iguales o superiores al tuyo.",
                discord.Color.red()
            ))
            return
    
    # Verificar jerarquía del bot
    if old_role >= ctx.guild.me.top_role or new_role >= ctx.guild.me.top_role:
        await ctx.send(embed=create_embed(
            "❌ Error de Jerarquía del Bot",
            f"No puedo gestionar roles iguales o superiores al mío.\n"
            "Por favor, mueve mi rol más arriba en la jerarquía.",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario tiene el rol antiguo
    if old_role not in member.roles:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"{member.mention} no tiene el rol {old_role.mention}.",
            discord.Color.red()
        ))
        return
    
    # Verificar que el usuario no tenga ya el nuevo rol
    if new_role in member.roles:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"{member.mention} ya tiene el rol {new_role.mention}.",
            discord.Color.red()
        ))
        return
    
    try:
        # Realizar la degradación
        await member.remove_roles(old_role)
        await member.add_roles(new_role)
        
        # Registrar en base de datos
        razon_completa = f"{reason} (De {old_role.name} a {new_role.name})"
        registrar_accion(
            member.id, ctx.guild.id, "demote",
            razon_completa, ctx.author.id
        )
        
        # Enviar log detallado
        await send_log_detailed(
            "Degradación de Usuario",
            member, ctx.author, razon_completa,
            discord.Color.dark_gray(),
            extra_fields={
                "Rango Anterior": old_role.name,
                "Nuevo Rango": new_role.name
            }
        )
        
        # Enviar al canal específico si está configurado
        if DEMOTE_CHANNEL:
            channel = bot.get_channel(DEMOTE_CHANNEL)
            if channel:
                demo_embed = discord.Embed(
                    title="🔻 Degradación de Usuario",
                    description=f"{member.mention} ha sido degradado de rango.",
                    color=discord.Color.dark_gray(),
                    timestamp=datetime.utcnow()
                )
                demo_embed.add_field(name="Rango Anterior", value=old_role.mention, inline=True)
                demo_embed.add_field(name="Nuevo Rango", value=new_role.mention, inline=True)
                demo_embed.add_field(name="Razón", value=reason, inline=False)
                demo_embed.add_field(name="Moderador", value=ctx.author.mention, inline=True)
                demo_embed.set_thumbnail(url=member.display_avatar.url)
                demo_embed.set_footer(text=f"ID: {member.id}")
                
                await channel.send(embed=demo_embed)
        
        # Notificar al usuario por DM
        await notify_user_dm(member, "demote", 
                           f"Has sido degradado de {old_role.name} a {new_role.name}\nRazón: {reason}", 
                           moderator=ctx.author)
        
        # Confirmación en el canal
        await ctx.send(embed=create_embed(
            "✅ Degradación Exitosa",
            f"{member.mention} ha sido degradado:\n\n"
            f"**De:** {old_role.mention}\n"
            f"**A:** {new_role.mention}\n"
            f"**Razón:** {reason}",
            discord.Color.dark_gray()
        ))
        
    except discord.Forbidden:
        await ctx.send(embed=create_embed(
            "❌ Error de Permisos",
            "No tengo permisos para gestionar estos roles.\n"
            "Asegúrate de que mi rol está por encima de los roles que intentas gestionar.",
            discord.Color.red()
        ))
    except Exception as e:
        await ctx.send(embed=create_embed(
            "❌ Error",
            f"No se pudo completar la degradación: {str(e)}",
            discord.Color.red()
        ))

# =========================================================
# COMANDOS DE INFORMACIÓN
# =========================================================

@bot.command(name="información", aliases=["info", "serverinfo"])
async def información_command(ctx):
    """Muestra información importante del servidor"""
    guild = ctx.guild
    
    # Estadísticas de moderación
    total_warns = 0
    total_acciones = 0
    with engine.begin() as conn:
        # Contar warns totales
        result = conn.execute(
            text("SELECT SUM(total_warns) FROM user_warns WHERE guild_id = :guild_id"),
            {"guild_id": guild.id}
        ).fetchone()
        total_warns = result[0] or 0
        
        # Contar acciones totales
        result = conn.execute(
            text("SELECT COUNT(*) FROM acciones WHERE guild_id = :guild_id"),
            {"guild_id": guild.id}
        ).fetchone()
        total_acciones = result[0] or 0
    
    embed = discord.Embed(
        title=f"🌍 {guild.name}",
        description="Información importante del servidor",
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    # Usar icono del servidor
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    # Información básica del servidor
    embed.add_field(name="👑 Propietario", value=guild.owner.mention, inline=True)
    embed.add_field(name="📅 Creado", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="👥 Miembros", value=str(guild.member_count), inline=True)
    
    # Información de canales
    text_channels = len(guild.text_channels)
    voice_channels = len(guild.voice_channels)
    embed.add_field(name="📚 Canales", value=f"Texto: {text_channels}\nVoz: {voice_channels}", inline=True)
    
    # Información de roles
    embed.add_field(name="🎭 Roles", value=str(len(guild.roles)), inline=True)
    
    # Estadísticas del bot
    embed.add_field(name="🤖 Estadísticas del Bot", 
                   value=f"**Comandos:** {len(bot.commands)}\n"
                         f"**Latencia:** {round(bot.latency * 1000)}ms", 
                   inline=True)
    
    # Estadísticas de moderación
    embed.add_field(name="📊 Estadísticas de Moderación",
                   value=f"**Warns totales:** {total_warns}\n"
                         f"**Acciones registradas:** {total_acciones}",
                   inline=True)
    
    # Información específica del servidor (personalizable)
    embed.add_field(
        name="🎮 Minecraft Java", 
        value="```IP: mc.godestmc.xyz\nVersión: 1.8 - 1.21.11```", 
        inline=False
    )
    
    embed.add_field(
        name="📱 Minecraft Bedrock", 
        value="```IP: bedrock.godestmc.xyz\nPuerto: 19132\nVersión: 1.21.90 - 1.21.111```", 
        inline=False
    )
    
    # ENLACES IMPORTANTES - CORREGIDO CON SALTOS DE LÍNEA
    embed.add_field(
        name="🔗 Enlaces importantes", 
        value="[📜 Reglas](https://discord.com/channels/1401779980945592400/1402405577027752085)\n[🛒 Tienda](PROXIMAMENTE)\n[📞 Web principal](PROXIMAMENTE)\n[📞 Soporte](Abre un ticket en el canal correspondiente)",
        inline=False
    )
    
    # Footer con información del solicitante
    embed.set_footer(text=f"Solicitado por {ctx.author.display_name}", 
                    icon_url=ctx.author.display_avatar.url)
    
    await ctx.send(embed=embed)

@bot.command(name="ping")
async def ping_command(ctx):
    """Muestra la latencia del bot"""
    latency = round(bot.latency * 1000)
    
    # Determinar color según latencia
    if latency < 100:
        color = discord.Color.green()
        estado = "🟢 Excelente"
    elif latency < 200:
        color = discord.Color.gold()
        estado = "🟡 Bueno"
    else:
        color = discord.Color.red()
        estado = "🔴 Lento"
    
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"**Latencia:** {latency}ms\n**Estado:** {estado}",
        color=color,
        timestamp=datetime.utcnow()
    )
    
    embed.set_footer(text=f"Solicitado por {ctx.author.display_name}", 
                    icon_url=ctx.author.display_avatar.url)
    
    await ctx.send(embed=embed)

# =========================================================
# COMANDO DE AYUDA MEJORADO
# =========================================================

@bot.command(name="help", aliases=["ayuda", "comandos"])
async def help_command(ctx, command_name: str = None):
    """Muestra el centro de ayuda con todos los comandos disponibles"""
    
    if command_name:
        # Ayuda específica para un comando
        cmd = bot.get_command(command_name.lower())
        if not cmd:
            embed = create_embed(
                "❌ Comando no encontrado",
                f"El comando `{command_name}` no existe.\n"
                f"Usa `{ctx.prefix}help` para ver todos los comandos disponibles.",
                discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
        
        # Crear embed para comando específico
        embed = discord.Embed(
            title=f"🆘 Ayuda: {cmd.name}",
            description=cmd.help or "Sin descripción disponible",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        # Uso del comando
        signature = f"{ctx.prefix}{cmd.name}"
        if cmd.signature:
            signature += f" {cmd.signature}"
        
        embed.add_field(name="📝 Uso", value=f"`{signature}`", inline=False)
        
        # Ejemplos
        examples = {
            "warn": f"`{ctx.prefix}warn @usuario Comportamiento inapropiado`",
            "mute": f"`{ctx.prefix}mute @usuario 1h Spam en chat`",
            "promote": f"`{ctx.prefix}promote @usuario @Novato @Experto Buen desempeño`",
            "historial": f"`{ctx.prefix}historial @usuario`",
            "checkwarns": f"`{ctx.prefix}checkwarns @usuario`"
        }
        
        if cmd.name in examples:
            embed.add_field(name="📚 Ejemplo", value=examples[cmd.name], inline=False)
        
        # Aliases
        if cmd.aliases:
            embed.add_field(name="🔤 Alias", 
                           value=", ".join([f"`{alias}`" for alias in cmd.aliases]),
                           inline=True)
        
        # Permisos requeridos
        permisos_text = "Cualquier miembro"
        if cmd.name in ["warn", "unwarn", "mute", "unmute", "checkwarns", "historial"]:
            permisos_text = "Moderación (Kick/Ban/Manage Messages)"
        elif cmd.name in ["promote", "demote"]:
            permisos_text = "Gestionar Roles"
        
        embed.add_field(name="🛡️ Permisos requeridos", value=permisos_text, inline=True)
        
        # Notas adicionales por comando
        notas = {
            "mute": "• Formatos de tiempo: `s` (segundos), `m` (minutos), `h` (horas), `d` (días)\n• Máximo: 28 días",
            "warn": "• Sistema de 3 warns: Notificación automática a moderadores\n• Los warns se almacenan en base de datos",
            "promote": "• Requiere mencionar ambos roles\n• Verifica jerarquía de roles automáticamente",
            "historial": "• Muestra las últimas 10 acciones\n• Incluye todas las sanciones y cambios de rol"
        }
        
        if cmd.name in notas:
            embed.add_field(name="⚠️ Notas importantes", value=notas[cmd.name], inline=False)
        
        embed.set_footer(text=f"Prefijo: {ctx.prefix}")
        
        await ctx.send(embed=embed)
        return
    
    # Ayuda general (todos los comandos)
    embed = discord.Embed(
        title="🆘 Centro de Ayuda - Bot de Moderación",
        description=(
            f"**Prefijo:** `{ctx.prefix}`\n"
            f"**Total de comandos:** {len(bot.commands)}\n"
            f"**Servidor:** {ctx.guild.name}\n\n"
            f"Usa `{ctx.prefix}help <comando>` para ver detalles específicos."
        ),
        color=discord.Color.blue(),
        timestamp=datetime.utcnow()
    )
    
    # Agrupar comandos por categorías
    categorias = {
        "🚨 **Moderación Básica**": [
            ("warn", "Da una advertencia a un usuario"),
            ("unwarn", "Remueve warns de un usuario"),
            ("mute", "Silencia a un usuario temporalmente"),
            ("unmute", "Remueve el silencio de un usuario"),
            ("checkwarns", "Revisa los warns de un usuario"),
            ("historial", "Muestra historial completo de un usuario")
        ],
        "🎭 **Gestión de Roles**": [
            ("promote", "Promueve a un usuario a un rango superior"),
            ("demote", "Degrada a un usuario a un rango inferior")
        ],
        "📊 **Información**": [
            ("información", "Muestra información del servidor"),
            ("ping", "Muestra la latencia del bot")
        ],
        "❓ **Ayuda**": [
            ("help", "Muestra este mensaje de ayuda")
        ]
    }
    
    for categoria, comandos in categorias.items():
        comandos_text = ""
        for nombre, desc in comandos:
            comandos_text += f"• **`{nombre}`** - {desc}\n"
        
        if comandos_text:
            embed.add_field(name=categoria, value=comandos_text, inline=False)
    
    # Sección de ejemplos rápidos
    embed.add_field(
        name="📚 **Ejemplos rápidos**",
        value=(
            f"`{ctx.prefix}warn @usuario Spam en chat`\n"
            f"`{ctx.prefix}mute @usuario 30m Lenguaje inapropiado`\n"
            f"`{ctx.prefix}promote @usuario @Novato @Experto Por buen desempeño`\n"
            f"`{ctx.prefix}historial @usuario`\n"
            f"`{ctx.prefix}información`"
        ),
        inline=False
    )
    
    # Sección de notas importantes
    embed.add_field(
        name="⚠️ **Notas importantes**",
        value=(
            "• Todos los comandos de moderación requieren permisos específicos\n"
            "• Los tiempos usan formato: `s` (segundos), `m` (minutos), `h` (horas), `d` (días)\n"
            "• El sistema de warns notifica automáticamente al llegar a 3 advertencias\n"
            "• Todas las acciones se registran en la base de datos para su seguimiento\n"
            "• Para problemas, contacta con los administradores del servidor"
        ),
        inline=False
    )
    
    # Footer con información del bot
    embed.set_footer(
        text=f"Bot: {bot.user.name} • Solicitud de: {ctx.author.display_name}",
        icon_url=ctx.author.display_avatar.url
    )
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
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
            "No tienes los permisos necesarios para usar este comando.\n"
            "Consulta con un administrador si crees que esto es un error.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=create_embed(
            "❌ Usuario no encontrado",
            "No se pudo encontrar al usuario mencionado.\n"
            "Asegúrate de que el usuario existe y está en el servidor.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.RoleNotFound):
        await ctx.send(embed=create_embed(
            "❌ Rol no encontrado",
            "No se pudo encontrar el rol mencionado.\n"
            "Verifica que el rol existe y está escrito correctamente.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=create_embed(
            "❌ Argumento faltante",
            f"Falta un argumento requerido.\n\n"
            f"**Uso correcto:** `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`\n"
            f"Usa `{ctx.prefix}help {ctx.command.name}` para más información.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=create_embed(
            "❌ Argumento inválido",
            "Uno o más argumentos son inválidos.\n"
            "Verifica que los valores proporcionados sean correctos.",
            discord.Color.red()
        ))
    elif isinstance(error, commands.CommandNotFound):
        embed = create_embed(
            "❌ Comando no encontrado",
            f"El comando `{ctx.invoked_with}` no existe.\n\n"
            f"Usa `{ctx.prefix}help` para ver todos los comandos disponibles.",
            discord.Color.red()
        )
        await ctx.send(embed=embed)
    elif isinstance(error, commands.CommandInvokeError):
        original = getattr(error, 'original', error)
        if isinstance(original, discord.Forbidden):
            await ctx.send(embed=create_embed(
                "❌ Error de Permisos del Bot",
                "No tengo los permisos necesarios para ejecutar esta acción.\n"
                "Por favor, verifica que tengo los permisos adecuados y que mi rol está por encima de los roles que intento gestionar.",
                discord.Color.red()
            ))
        else:
            print(f"Error no manejado: {original}")
            await ctx.send(embed=create_embed(
                "❌ Error Inesperado",
                "Ha ocurrido un error inesperado al ejecutar el comando.\n"
                "Los administradores han sido notificados.",
                discord.Color.red()
            ))
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
    print("🚀 Iniciando bot de moderación...")
    print(f"📊 Configuración cargada:")
    print(f"   • Servidor: {GUILD_ID}")
    print(f"   • Canal de logs: {LOG_CHANNEL_ID}")
    print(f"   • Canal de promociones: {PROMOTE_CHANNEL if PROMOTE_CHANNEL else 'No configurado'}")
    print(f"   • Canal de degradaciones: {DEMOTE_CHANNEL if DEMOTE_CHANNEL else 'No configurado'}")
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Error: Token inválido. Verifica tu token de Discord.")
    except Exception as e:
        print(f"❌ Error al iniciar el bot: {e}")
