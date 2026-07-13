import discord
from discord.ext import commands
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.db_operations import DatabaseOperations
from utils.permissions import is_admin_check, get_roles_for_guild

logger = logging.getLogger('discord_bot.settings')


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None

    async def cog_load(self):
        self.db = self.bot.db

    @commands.hybrid_group(name='settings', invoke_without_command=True)
    @is_admin_check()
    async def settings(self, ctx):
        """Zeigt/ändert die Bot-Einstellungen für diesen Server"""
        await self.show(ctx)

    @settings.command(name='show')
    @is_admin_check()
    async def show(self, ctx):
        """Zeigt die aktuellen Einstellungen für diesen Server"""
        guild_settings = await DatabaseOperations.get_guild_settings(self.db, ctx.guild.id)

        channel_id = guild_settings.get('announce_channel_id')
        channel = ctx.guild.get_channel(channel_id) if channel_id else None
        enabled = guild_settings.get('announce_enabled')
        if enabled is None:
            enabled = self.bot.config.get('notifications', {}).get('song_change_default_enabled', True)

        user_role_id = guild_settings.get('user_role_id')
        supporter_role_id = guild_settings.get('supporter_role_id')
        admin_role_id = guild_settings.get('admin_role_id')

        user_role = ctx.guild.get_role(user_role_id) if user_role_id else None
        supporter_role = ctx.guild.get_role(supporter_role_id) if supporter_role_id else None
        admin_role = ctx.guild.get_role(admin_role_id) if admin_role_id else None

        embed = discord.Embed(title="⚙️ Server-Einstellungen", color=discord.Color.blue())
        
        embed.add_field(
            name="🎵 Songwechsel-Ankündigungen",
            value=f"Status: {'✅ Aktiv' if enabled else '❌ Deaktiviert'}\n"
                  f"Kanal: {channel.mention if channel else 'Nicht gesetzt'}",
            inline=False
        )

        embed.add_field(
            name="👥 Gruppen-Rollen",
            value=f"**User:** {user_role.mention if user_role else 'Nicht gesetzt (Jeder)'}\n"
                  f"**Supporter:** {supporter_role.mention if supporter_role else 'Nicht gesetzt (Nur Admins)'}\n"
                  f"**Admin:** {admin_role.mention if admin_role else 'Nicht gesetzt (Nur Server-Manager)'}",
            inline=False
        )

        embed.add_field(
            name="Befehle für Einstellungen",
            value="`!settings announce #kanal` - Ankündigungskanal setzen\n"
                  "`!settings announce_toggle on/off` - Ankündigungen an-/ausschalten",
            inline=False
        )

        embed.add_field(
            name="Befehle für Gruppen",
            value="`!settings setrole user @Rolle` - User-Rolle zuweisen\n"
                  "`!settings setrole supporter @Rolle` - Supporter-Rolle zuweisen\n"
                  "`!settings setrole admin @Rolle` - Admin-Rolle zuweisen\n"
                  "`!settings removerole <gruppe>` - Rolle einer Gruppe entziehen",
            inline=False
        )
        
        await ctx.send(embed=embed)

    @settings.command(name='announce')
    @is_admin_check()
    async def announce(self, ctx, channel: discord.TextChannel):
        """Legt den Kanal für Songwechsel-Ankündigungen fest"""
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, announce_channel_id=channel.id)
        await ctx.send(f"✅ Songwechsel-Ankündigungen werden jetzt in {channel.mention} gepostet.")

    @settings.command(name='announce_toggle')
    @is_admin_check()
    async def announce_toggle(self, ctx, state: str):
        """Schaltet Songwechsel-Ankündigungen an oder aus (on/off)"""
        if state.lower() not in ('on', 'off'):
            return await ctx.send("❌ Bitte `on` oder `off` angeben.")

        enabled = state.lower() == 'on'
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, announce_enabled=enabled)
        await ctx.send(f"✅ Songwechsel-Ankündigungen sind jetzt **{'aktiviert' if enabled else 'deaktiviert'}**.")

    @settings.command(name='setrole')
    @is_admin_check()
    async def setrole(self, ctx, group: str, role: discord.Role):
        """Weist einer Gruppe (user, supporter, admin) eine Discord-Rolle zu"""
        group = group.lower()
        if group not in ('user', 'supporter', 'admin'):
            return await ctx.send("❌ Ungültige Gruppe. Erlaubt sind: `user`, `supporter`, `admin`.")

        setting_name = f"{group}_role_id"
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, **{setting_name: role.id})
        await ctx.send(f"✅ Gruppe **{group}** wurde erfolgreich die Rolle {role.mention} zugewiesen.")

    @settings.command(name='removerole')
    @is_admin_check()
    async def removerole(self, ctx, group: str):
        """Entzieht einer Gruppe (user, supporter, admin) ihre Rollenzuweisung"""
        group = group.lower()
        if group not in ('user', 'supporter', 'admin'):
            return await ctx.send("❌ Ungültige Gruppe. Erlaubt sind: `user`, `supporter`, `admin`.")

        setting_name = f"{group}_role_id"
        await DatabaseOperations.set_guild_setting(self.db, ctx.guild.id, **{setting_name: None})
        await ctx.send(f"✅ Rollenzuweisung für Gruppe **{group}** wurde aufgehoben.")


async def setup(bot):
    await bot.add_cog(Settings(bot))
