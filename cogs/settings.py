import discord
from discord.ext import commands
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.db_operations import DatabaseOperations

logger = logging.getLogger('discord_bot.settings')


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None

    async def cog_load(self):
        self.db = Database(self.bot.config)
        await self.db.initialize()

    @commands.group(name='settings', invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    async def settings(self, ctx):
        """Zeigt/ändert die Bot-Einstellungen für diesen Server"""
        await self.show(ctx)

    @settings.command(name='show')
    @commands.has_permissions(manage_guild=True)
    async def show(self, ctx):
        """Zeigt die aktuellen Einstellungen für diesen Server"""
        guild_settings = await DatabaseOperations.get_guild_settings(self.db, ctx.guild.id)

        channel_id = guild_settings.get('announce_channel_id')
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        enabled = guild_settings.get('announce_enabled')
        if enabled is None:
            enabled = self.bot.config.get('notifications', {}).get('song_change_default_enabled', True)

        embed = discord.Embed(title="⚙️ Server-Einstellungen", color=discord.Color.blue())
        embed.add_field(
            name="🎵 Songwechsel-Ankündigungen",
            value=f"Status: {'✅ Aktiv' if enabled else '❌ Deaktiviert'}\n"
                  f"Kanal: {channel.mention if channel else 'Nicht gesetzt'}",
            inline=False
        )
        embed.add_field(
            name="Befehle",
            value="`!settings announce #kanal` - Ankündigungskanal setzen\n"
                  "`!settings announce_toggle on/off` - Ankündigungen an-/ausschalten",
            inline=False
        )
        await ctx.send(embed=embed)

    @settings.command(name='announce')
    @commands.has_permissions(manage_guild=True)
    async def announce(self, ctx, channel: discord.TextChannel):
        """Legt den Kanal für Songwechsel-Ankündigungen fest"""
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, announce_channel_id=channel.id)
        await ctx.send(f"✅ Songwechsel-Ankündigungen werden jetzt in {channel.mention} gepostet.")

    @settings.command(name='announce_toggle')
    @commands.has_permissions(manage_guild=True)
    async def announce_toggle(self, ctx, state: str):
        """Schaltet Songwechsel-Ankündigungen an oder aus (on/off)"""
        if state.lower() not in ('on', 'off'):
            return await ctx.send("❌ Bitte `on` oder `off` angeben.")

        enabled = state.lower() == 'on'
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, announce_enabled=enabled)
        await ctx.send(f"✅ Songwechsel-Ankündigungen sind jetzt **{'aktiviert' if enabled else 'deaktiviert'}**.")


async def setup(bot):
    await bot.add_cog(Settings(bot))
