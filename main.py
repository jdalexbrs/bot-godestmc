import discord
from discord.ext import commands
import os, asyncio, re
from datetime import datetime, timedelta
from keep_alive import keep_alive

TOKEN = os.environ["TOKEN"]

GUILD_ID = 1401779980945592400
LOG_CHANNEL_ID = 1405694108302970910
WARN_ROLE_ID = 1406275869252522056

# Almacenamiento en memoria para sanciones
sanciones_data = {}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# SOLUCIÓN: Desactivar el comando help integrado
bot = commands.Bot(
    command_prefix="god ",
    intents=intents,
    help_command=None  # Esta línea soluciona el error
)

# ========= SISTEMA DE REGISTRO DE SANCIONES (EN MEMORIA) =========
def guardar_sancion(usuario_id, tipo, razon, moderador_id, duracion=None):
    usuario_id = str(usuario_id)
    
    if usuario_id not in sanciones_data:
        sanciones_data[usuario_id] = []
    
    sancion = {
        "tipo": tipo,
        "razon": razon,
        "moderador": str(moderador_id),
        "fecha": datetime.utcnow().isoformat(),
        "duracion": duracion
    }
    
    sanciones_data[usuario_id].append(sancion)
    return sancion

def obtener_sanciones_usuario(usuario_id):
    usuario_id = str(usuario_id)
    return sanciones_data.get(usuario_id, [])

def obtener_warns_usuario(usuario_id):
    todas = obtener_sanciones_usuario(usuario_id)
    return [s for s in todas if s["tipo"] == "warn"]

# ========= FUNCIONES AUXILIARES =========
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

async def notify_user(user, action, reason, duration=None, moderator=None):
    try:
        embed = discord.Embed(
            title=f"🔔 Notificación de {action}",
            color=discord.Color.orange()
        )
        embed.add_field(name="📌 Acción", value=action, inline=False)
        if duration:
            embed.add_field(name="⏱ Duración", value=duration, inline=True)
        embed.add_field(name="📝 Razón", value=reason, inline=False)
        if moderator:
            embed.add_field(name="👤 Moderador", value=f"{moderator.name}#{moderator.discriminator}", inline=True)
        embed.set_footer(text=f"Servidor: {bot.get_guild(GUILD_ID).name}")
        await user.send(embed=embed)
        return True
    except:
        return False

@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="god help"))

# ========= COMANDO WARNINGS =========
@bot.command()
@commands.has_permissions(manage_roles=True)
async def warnings(ctx, usuario_id: str = None):
    if not usuario_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god warnings <id_usuario>`\nEjemplo: `god warnings 123456789012345678`"
        )
        await ctx.send(embed=embed)
        return

    try:
        usuario_id = int(usuario_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    warns = obtener_warns_usuario(usuario_id)
    
    if not warns:
        embed = discord.Embed(
            title=f"⚠️ Advertencias de <@{usuario_id}>",
            description="Este usuario no tiene advertencias registradas.",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(
        title=f"⚠️ Advertencias de <@{usuario_id}>",
        description=f"Total: {len(warns)} advertencia(s)",
        color=discord.Color.gold()
    )
    
    for i, warn in enumerate(warns, 1):
        fecha = datetime.fromisoformat(warn["fecha"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        moderador = f"<@{warn['moderador']}>"
        embed.add_field(
            name=f"Advertencia #{i}",
            value=f"**Razón:** {warn['razon']}\n**Moderador:** {moderador}\n**Fecha:** {fecha}",
            inline=False
        )

    await ctx.send(embed=embed)

# ========= COMANDO SANCIONES =========
@bot.command()
@commands.has_permissions(manage_roles=True)
async def sanciones(ctx, usuario_id: str = None):
    if not usuario_id:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god sanciones <id_usuario>`\nEjemplo: `god sanciones 123456789012345678`"
        )
        await ctx.send(embed=embed)
        return

    try:
        usuario_id = int(usuario_id)
    except ValueError:
        await ctx.send(embed=error_embed("❌ Error", "El ID de usuario debe ser numérico."))
        return

    sanciones = obtener_sanciones_usuario(usuario_id)
    
    if not sanciones:
        embed = discord.Embed(
            title=f"📜 Historial de sanciones de <@{usuario_id}>",
            description="Este usuario no tiene sanciones registradas.",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)
        return

    # Contadores por tipo de sanción
    contadores = {"warn": 0, "mute": 0, "ban": 0, "kick": 0, "unmute": 0, "unban": 0}
    for s in sanciones:
        tipo = s["tipo"]
        if tipo in contadores:
            contadores[tipo] += 1
        else:
            contadores[tipo] = 1
    
    embed = discord.Embed(
        title=f"📜 Historial de sanciones de <@{usuario_id}>",
        description=(
            f"Total: {len(sanciones)} sanción(es)\n"
            f"⚠️ Warns: {contadores['warn']} | 🔇 Mutes: {contadores['mute']}\n"
            f"👢 Kicks: {contadores['kick']} | 🚫 Bans: {contadores['ban']}\n"
            f"🔊 Unmutes: {contadores['unmute']} | ♻️ Unbans: {contadores['unban']}"
        ),
        color=discord.Color.blue()
    )
    
    # Ordenar sanciones por fecha (más recientes primero)
    sanciones_ordenadas = sorted(sanciones, key=lambda x: x["fecha"], reverse=True)
    
    for sancion in sanciones_ordenadas[:10]:  # Mostrar máximo 10 sanciones
        tipo = sancion["tipo"]
        fecha = datetime.fromisoformat(sancion["fecha"]).strftime("%Y-%m-%d %H:%M:%S UTC")
        moderador = f"<@{sancion['moderador']}>"
        
        # Emojis según tipo de sanción
        emoji = {
            "warn": "⚠️",
            "mute": "🔇",
            "ban": "🚫",
            "kick": "👢",
            "unmute": "🔊",
            "unban": "♻️"
        }.get(tipo, "📝")
        
        titulo = f"{emoji} {tipo.capitalize()} - {fecha}"
        valor = f"**Razón:** {sancion['razon']}\n**Moderador:** {moderador}"
        
        if sancion.get("duracion"):
            valor += f"\n**Duración:** {sancion['duracion']}"
            
        embed.add_field(name=titulo, value=valor, inline=False)
    
    if len(sanciones) > 10:
        embed.set_footer(text=f"Mostrando 10 de {len(sanciones)} sanciones | Más recientes primero")
    else:
        embed.set_footer(text=f"Total: {len(sanciones)} sanciones")
    
    await ctx.send(embed=embed)

# ========= COMANDO HELP =========
@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="🆘 Centro de Ayuda del Bot de Moderación",
        description="Lista completa de comandos disponibles y su uso",
        color=discord.Color.blue()
    )
    
    # Moderación
    embed.add_field(
        name="🚨 **Comandos de Moderación**",
        value=(
            "`god ban <id> [tiempo] [razón]` - Banea a un usuario\n"
            "`god kick <id> [razón]` - Expulsa a un usuario\n"
            "`god mute <id> <tiempo> [razón]` - Mutea a un usuario\n"
            "`god unmute <id> [razón]` - Desmutea a un usuario\n"
            "`god warn <id> [razón]` - Advertencia a un usuario\n"
            "`god warnings <id>` - Muestra advertencias de un usuario\n"
            "`god sanciones <id>` - Muestra historial de sanciones"
        ),
        inline=False
    )
    
    # Roles
    embed.add_field(
        name="🎭 **Comandos de Gestión de Roles**",
        value=(
            "`god promote @usuario @rango_anterior @nuevo_rango [razón]` - Asciende a un usuario\n"
            "`god demote @usuario @rango_anterior @nuevo_rango [razón]` - Degrada a un usuario"
        ),
        inline=False
    )
    
    # Utilidades
    embed.add_field(
        name="🔧 **Comandos de Utilidad**",
        value=(
            "`god help` - Muestra este mensaje de ayuda\n"
            "`god ping` - Comprueba la latencia del bot"
        ),
        inline=False
    )
    
    # Ejemplos
    embed.add_field(
        name="📚 **Ejemplos de Uso**",
        value=(
            "`god ban 123456789012345678 1h Spam`\n"
            "`god promote @Usuario @Novato @Experto Por buen desempeño`\n"
            "`god mute 123456789012345678 30m Lenguaje inapropiado`"
        ),
        inline=False
    )
    
    # Notas importantes
    embed.add_field(
        name="⚠️ **Notas Importantes**",
        value=(
            "• Todos los comandos requieren permisos específicos\n"
            "• Los tiempos usan formato: `s` (segundos), `m` (minutos), `h` (horas), `d` (días)\n"
            "• Los IDs de usuario son números de 18 dígitos"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"Solicitado por {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await ctx.send(embed=embed)

# ========= COMANDO PING =========
@bot.command()
async def ping(ctx):
    """Comprueba la latencia del bot"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Latencia del bot: **{latency}ms**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

# ========= COMANDOS DE MODERACIÓN =========
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
        
        # Notificar al usuario antes de banear
        action = "baneo" + (" temporal" if tiempo else " permanente")
        duration = tiempo if tiempo else "Indefinido"
        notified = await notify_user(user, action, reason, duration, ctx.author)
        
        await guild.ban(user, reason=reason)
        guardar_sancion(user_id, "ban", reason, ctx.author.id, duracion=tiempo)
        await send_log("🚫 Ban", user, ctx.author, reason, discord.Color.red(), tiempo)
        await ctx.send(f"✅ Usuario {user} baneado.")
        
        if tiempo:
            seconds = parse_time(tiempo)
            if seconds:
                await asyncio.sleep(seconds)
                try:
                    await guild.unban(user)
                    guardar_sancion(user_id, "unban", "Fin de sanción automático", bot.user.id)
                    await send_log("♻️ Unban automático", user, ctx.author, "Fin de sanción", discord.Color.green())
                except discord.Forbidden:
                    await ctx.send("❌ Error: No tengo permisos para desbanear")

    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para banear usuarios"))
    except discord.NotFound:
        await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado"))

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
            # Notificar al usuario antes de kickear
            notified = await notify_user(member, "expulsión", reason, None, ctx.author)
            
            await member.kick(reason=reason)
            guardar_sancion(user_id, "kick", reason, ctx.author.id)
            await send_log("👢 Kick", member, ctx.author, reason, discord.Color.orange())
            await ctx.send(f"✅ Usuario {member} expulsado.")
        else:
            await ctx.send(embed=error_embed("❌ Error", "Usuario no encontrado en el servidor"))
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para expulsar usuarios"))

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
        guardar_sancion(user_id, "mute", reason, ctx.author.id, duracion=tiempo)
        
        # Notificar al usuario después de mutear
        notified = await notify_user(member, "muteo", reason, tiempo, ctx.author)
        
        await send_log("🔇 Mute", member, ctx.author, reason, discord.Color.dark_gray(), tiempo)
        await ctx.send(f"✅ Usuario {member} muteado por {tiempo}.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para mutear usuarios"))

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
        guardar_sancion(user_id, "unmute", reason, ctx.author.id)
        await send_log("🔊 Unmute", member, ctx.author, reason, discord.Color.green())
        await ctx.send(f"✅ Usuario {member} desmuteado.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para desmutear usuarios"))

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
        guardar_sancion(user_id, "warn", reason, ctx.author.id)
        
        # Notificar al usuario
        notified = await notify_user(member, "advertencia", reason, None, ctx.author)
        
        await send_log("⚠️ Warn", member, ctx.author, reason, discord.Color.yellow())
        await ctx.send(f"⚠️ Usuario {member} advertido.")
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para asignar el rol de warn"))

# ========= COMANDO PROMOTE =========
@bot.command()
@commands.has_permissions(manage_roles=True)
async def promote(ctx, member: discord.Member = None, old_role: discord.Role = None, new_role: discord.Role = None, *, reason="No se especificó razón"):
    if not member or not old_role or not new_role:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god promote <@usuario> <@rango_anterior> <@nuevo_rango> [razón]`\n"
            "Ejemplo: `god promote @Usuario @Novato @Experto Por buen desempeño`"
        )
        await ctx.send(embed=embed)
        return
    
    try:
        # Verificar que el usuario tiene el rol anterior
        if old_role not in member.roles:
            await ctx.send(embed=error_embed("❌ Error", f"El usuario no tiene el rol {old_role.mention}"))
            return
        
        # Verificar jerarquía de roles
        if ctx.guild.me.top_role <= new_role:
            await ctx.send(embed=error_embed("❌ Error", "No puedo asignar un rol superior al mío"))
            return
        
        # Realizar promoción
        await member.remove_roles(old_role)
        await member.add_roles(new_role)
        
        # Embed de ejemplo (personalizable)
        embed = discord.Embed(
            title="🎉 Promote",
            description=f"¡Felicidades {member.mention}! Has sido ascendido.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Rango Anterior", value=old_role.mention, inline=True)
        embed.add_field(name="Nuevo Rango", value=new_role.mention, inline=True)
        embed.add_field(name="Razón", value=reason, inline=False)
        embed.add_field(name="Moderador", value=ctx.author.mention, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await ctx.send(embed=embed)
        await send_rank_log("⬆️ Promote", member, ctx.author, old_role, new_role, reason)
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para gestionar estos roles"))

# ========= COMANDO DEMOTE =========
@bot.command()
@commands.has_permissions(manage_roles=True)
async def demote(ctx, member: discord.Member = None, old_role: discord.Role = None, new_role: discord.Role = None, *, reason="No se especificó razón"):
    if not member or not old_role or not new_role:
        embed = error_embed(
            "❌ Uso incorrecto",
            "Formato correcto:\n`god demote <@usuario> <@rango_anterior> <@nuevo_rango> [razón]`\n"
            "Ejemplo: `god demote @Usuario @Experto @Novato Por bajo rendimiento`"
        )
        await ctx.send(embed=embed)
        return
    
    try:
        # Verificar que el usuario tiene el rol anterior
        if old_role not in member.roles:
            await ctx.send(embed=error_embed("❌ Error", f"El usuario no tiene el rol {old_role.mention}"))
            return
        
        # Verificar jerarquía de roles
        if ctx.guild.me.top_role <= old_role or ctx.guild.me.top_role <= new_role:
            await ctx.send(embed=error_embed("❌ Error", "No puedo gestionar roles superiores al mío"))
            return
        
        # Realizar degradación
        await member.remove_roles(old_role)
        await member.add_roles(new_role)
        
        # Embed de ejemplo (personalizable)
        embed = discord.Embed(
            title="🔻 Demote",
            description=f"{member.mention} ha sido degradado de rango.",
            color=discord.Color.dark_grey()
        )
        embed.add_field(name="Rango Anterior", value=old_role.mention, inline=True)
        embed.add_field(name="Nuevo Rango", value=new_role.mention, inline=True)
        embed.add_field(name="Razón", value=reason, inline=False)
        embed.add_field(name="Moderador", value=ctx.author.mention, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        
        await ctx.send(embed=embed)
        await send_rank_log("⬇️ Demote", member, ctx.author, old_role, new_role, reason)
        
    except discord.Forbidden:
        await ctx.send(embed=error_embed("❌ Error", "No tengo permisos para gestionar estos roles"))

# Función para registrar cambios de rango en el log
async def send_rank_log(action, member, moderator, old_role, new_role, reason):
    embed = discord.Embed(
        title=f"{action}",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="👤 Usuario", value=f"{member} ({member.id})", inline=False)
    embed.add_field(name="🛡 Moderador", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="🔽 Rango Anterior", value=old_role.mention, inline=True)
    embed.add_field(name="🔼 Nuevo Rango", value=new_role.mention, inline=True)
    embed.add_field(name="📄 Razón", value=reason, inline=False)
    embed.set_footer(text="Sistema de Rangos")
    
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel:
        await channel.send(embed=embed)

keep_alive()
bot.run(TOKEN)
