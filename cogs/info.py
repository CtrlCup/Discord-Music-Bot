import discord
from discord.ext import commands
import platform
from datetime import datetime
import psutil
import sys

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='info', aliases=['help', 'hilfe'])
    async def info(self, ctx):
        """Zeigt alle verfügbaren Befehle und Informationen zum Bot"""
        
        embed = discord.Embed(
            title="🤖 Bot Information",
            description="Ein multifunktionaler Discord Bot mit Musik- und Statistikfunktionen",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        
        # Bot creator info
        embed.add_field(
            name="👨‍💻 Entwickler",
            value="**Gamerfreak_LP aka Alex**",
            inline=False
        )
        
        # Music commands
        music_commands = [
            "`!play <link/suche>` - Spielt einen Song oder fügt ihn zur Warteschlange hinzu",
            "`!stop` - Stoppt die Musik und leert die Warteschlange",
            "`!pause` - Pausiert die aktuelle Wiedergabe",
            "`!resume` - Setzt die pausierte Wiedergabe fort",
            "`!skip` / `!next` - Überspringt den aktuellen Song",
            "`!previous` / `!prev` - Spielt den vorherigen Song",
            "`!queue` / `!q` - Zeigt die Warteschlange",
            "`!volume <0-100>` - Ändert die Lautstärke"
        ]
        embed.add_field(
            name="🎵 Musik-Befehle",
            value="\n".join(music_commands),
            inline=False
        )
        
        # Stats commands
        stats_commands = [
            "`!stats` - Zeigt deine eigenen Statistiken",
            "`!stats <@user/name>` - Zeigt Statistiken eines anderen Benutzers",
            "`!leaderboard <messages/voice>` - Zeigt die Top 10 Rangliste"
        ]
        embed.add_field(
            name="📊 Statistik-Befehle",
            value="\n".join(stats_commands),
            inline=False
        )
        
        # System commands
        system_commands = [
            "`!info` / `!help` - Zeigt diese Hilfe",
            "`!ping` - Zeigt die Bot-Latenz",
            "`!uptime` - Zeigt die Betriebszeit des Bots",
            "`!botinfo` - Zeigt technische Bot-Informationen",
            "`!invite` - Zeigt den Einladungslink für den Bot"
        ]
        embed.add_field(
            name="ℹ️ System-Befehle",
            value="\n".join(system_commands),
            inline=False
        )
        
        # Features
        features = [
            "✅ YouTube/YouTube Music Unterstützung",
            "📊 Automatisches Tracking von Statistiken",
            "💾 Datenbank-Speicherung (MySQL/SQLite)",
            "🎵 Warteschlangen-System für Musik",
            "👥 Multi-Server Unterstützung"
        ]
        embed.add_field(
            name="✨ Features",
            value="\n".join(features),
            inline=False
        )
        
        # Note about prefix
        embed.add_field(
            name="📝 Hinweis",
            value="Alle Befehle funktionieren mit `!` oder `/` als Präfix",
            inline=False
        )
        
        # Footer
        embed.set_footer(
            text=f"Bot Version 1.0 | Entwickelt mit ❤️ von Gamerfreak_LP",
            icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='ping')
    async def ping(self, ctx):
        """Zeigt die Bot-Latenz"""
        latency = round(self.bot.latency * 1000)
        
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latenz: **{latency}ms**",
            color=discord.Color.green() if latency < 200 else discord.Color.orange() if latency < 500 else discord.Color.red()
        )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='uptime')
    async def uptime(self, ctx):
        """Zeigt die Betriebszeit des Bots"""
        uptime = datetime.utcnow() - self.bot.start_time
        
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = []
        if days > 0:
            uptime_str.append(f"{days} Tag{'e' if days != 1 else ''}")
        if hours > 0:
            uptime_str.append(f"{hours} Stunde{'n' if hours != 1 else ''}")
        if minutes > 0:
            uptime_str.append(f"{minutes} Minute{'n' if minutes != 1 else ''}")
        uptime_str.append(f"{seconds} Sekunde{'n' if seconds != 1 else ''}")
        
        embed = discord.Embed(
            title="⏰ Bot Betriebszeit",
            description=" ".join(uptime_str),
            color=discord.Color.blue(),
            timestamp=self.bot.start_time
        )
        embed.set_footer(text="Bot gestartet")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='botinfo')
    async def botinfo(self, ctx):
        """Zeigt technische Informationen über den Bot"""
        
        # System info
        py_version = platform.python_version()
        discord_version = discord.__version__
        os_info = f"{platform.system()} {platform.release()}"
        
        # Bot stats
        guild_count = len(self.bot.guilds)
        user_count = sum(guild.member_count for guild in self.bot.guilds)
        
        # Memory usage
        process = psutil.Process()
        memory_usage = process.memory_info().rss / 1024 / 1024  # Convert to MB
        
        embed = discord.Embed(
            title="🤖 Bot Informationen",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="📊 Statistiken",
            value=f"Server: **{guild_count}**\nBenutzer: **{user_count:,}**",
            inline=True
        )
        
        embed.add_field(
            name="💻 System",
            value=f"Python: **{py_version}**\nDiscord.py: **{discord_version}**\nOS: **{os_info}**",
            inline=True
        )
        
        embed.add_field(
            name="💾 Ressourcen",
            value=f"RAM: **{memory_usage:.2f} MB**\nCPU: **{psutil.cpu_percent()}%**",
            inline=True
        )
        
        embed.add_field(
            name="👨‍💻 Entwickler",
            value="**Gamerfreak_LP aka Alex**",
            inline=True
        )
        
        embed.add_field(
            name="🔗 Links",
            value="[GitHub](https://github.com) | [Support Server](https://discord.gg)",
            inline=True
        )
        
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        await ctx.send(embed=embed)
    
    @commands.command(name='invite')
    async def invite(self, ctx):
        """Zeigt den Einladungslink für den Bot"""
        
        permissions = discord.Permissions(
            send_messages=True,
            read_messages=True,
            add_reactions=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            use_external_emojis=True,
            connect=True,
            speak=True,
            use_voice_activation=True,
            change_nickname=True,
            manage_messages=True
        )
        
        invite_url = discord.utils.oauth_url(
            self.bot.user.id,
            permissions=permissions,
            scopes=["bot", "applications.commands"]
        )
        
        embed = discord.Embed(
            title="🔗 Bot einladen",
            description=f"Klicke [hier]({invite_url}) um den Bot zu deinem Server einzuladen!",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Benötigte Berechtigungen",
            value="• Nachrichten senden/lesen\n• In Sprachkanäle verbinden\n• Musik abspielen\n• Einbettungen senden\n• Reaktionen hinzufügen",
            inline=False
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Info(bot))
