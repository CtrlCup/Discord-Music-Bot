import discord
from discord.ext import commands
import logging
from datetime import datetime
from collections import deque
from utils.permissions import is_user_check

logger = logging.getLogger('discord_bot.bug')

class Bug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_logs = {}

    def add_log(self, user_id: int, entry: str):
        """Add a log entry to the user's rolling action log"""
        if user_id not in self.user_logs:
            self.user_logs[user_id] = deque(maxlen=10)
        self.user_logs[user_id].append(entry)

    def get_logs(self, user_id: int):
        """Get the user's rolling action log"""
        return list(self.user_logs.get(user_id, []))

    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Log command execution details for each user"""
        user_id = ctx.author.id
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        command_name = ctx.command.qualified_name if ctx.command else "Unbekannt"
        guild_name = ctx.guild.name if ctx.guild else "Direct Message"
        
        args = []
        if ctx.interaction:
            # Slash commands
            args = [f"{k}={v}" for k, v in ctx.interaction.namespace]
        else:
            # Prefix commands (strip command name from message content)
            raw_args = ctx.message.content[len(ctx.prefix) + len(ctx.command.name):].strip()
            if raw_args:
                args = [raw_args]

        args_str = f" ({', '.join(args)})" if args else ""
        log_entry = f"[{timestamp}] Befehl: !{command_name}{args_str} [Server: {guild_name}]"
        self.add_log(user_id, log_entry)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Log command errors for each user"""
        user_id = ctx.author.id
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] FEHLER: {error}"
        self.add_log(user_id, log_entry)

    @commands.hybrid_command(name='bug', aliases=['bugreport', 'report'])
    @is_user_check()
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def bug(self, ctx, *, message: str):
        """Meldet einen Fehler/Bug direkt an den Entwickler"""
        user = ctx.author
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # Get user logs
        user_logs = self.get_logs(user.id)
        logs_str = "\n".join(user_logs) if user_logs else "Keine Aktionen aufgezeichnet."
        
        # Build embed for developer
        embed = discord.Embed(
            title="🐛 Neuer Bug-Report",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Verfasser", value=f"{user.mention} ({user} · ID: {user.id})", inline=True)
        embed.add_field(name="Server", value=ctx.guild.name if ctx.guild else "Direct Message", inline=True)
        embed.add_field(name="Uhrzeit", value=timestamp, inline=True)
        embed.add_field(name="Bug-Beschreibung", value=message, inline=False)
        
        # Ensure log size fits within Discord embed field limit (1024 characters)
        if len(logs_str) > 1000:
            logs_str = "..." + logs_str[-990:]
        embed.add_field(name="Letzte Aktionen & Fehler des Nutzers", value=f"```text\n{logs_str}\n```", inline=False)
        
        try:
            # Fetch application owner
            app_info = await self.bot.application_info()
            owner = app_info.owner
            
            # Send to application owner
            if isinstance(owner, discord.Team):
                for member in owner.members:
                    await member.send(embed=embed)
            else:
                await owner.send(embed=embed)
                
            await ctx.send("✅ Dein Bug-Report wurde erfolgreich an den Entwickler gesendet! Vielen Dank für dein Feedback.", ephemeral=True)
        except Exception as e:
            logger.error(f"Fehler beim Senden des Bug-Reports: {e}")
            await ctx.send("❌ Der Bug-Report konnte nicht per Direktnachricht an den Entwickler gesendet werden.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Bug(bot))
