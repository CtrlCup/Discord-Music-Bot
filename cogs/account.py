import discord
from discord.ext import commands
from urllib.parse import urlencode
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.db_operations import DatabaseOperations
from utils.oauth_server import create_state

logger = logging.getLogger('discord_bot.account')

AUTHORIZE_URL = 'https://discord.com/oauth2/authorize'


class Account(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @property
    def db(self) -> Database:
        return self.bot.oauth_db

    @commands.command(name='connect')
    async def connect(self, ctx):
        """Verknüpft dein Discord-Konto per Login, um private Zusatzdaten in !stats freizuschalten"""
        oauth_cfg = self.bot.config.get('oauth', {})
        if not oauth_cfg.get('client_id') or not oauth_cfg.get('client_secret') or not oauth_cfg.get('redirect_uri'):
            return await ctx.send("❌ OAuth-Login ist auf diesem Bot nicht konfiguriert.")

        state = create_state(self.bot, ctx.author.id)
        params = {
            'client_id': oauth_cfg['client_id'],
            'redirect_uri': oauth_cfg['redirect_uri'],
            'response_type': 'code',
            'scope': ' '.join(self.bot.config.get('oauth', {}).get('scopes', ['identify', 'email'])),
            'state': state,
            'prompt': 'consent'
        }
        authorize_url = f"{AUTHORIZE_URL}?{urlencode(params)}"

        message = (
            "🔒 **Discord-Konto verknüpfen**\n"
            "Klicke auf den folgenden Link und bestätige die Anfrage bei Discord, um zusätzliche "
            "private Details in deinen eigenen `!stats` freizuschalten:\n"
            f"{authorize_url}\n\n"
            "Der Link ist 10 Minuten gültig und nur für deinen Account bestimmt - nicht weitergeben!"
        )

        try:
            await ctx.author.send(message)
            if ctx.guild is not None:
                await ctx.send("📬 Ich habe dir den Verknüpfungs-Link per Direktnachricht geschickt!")
        except discord.Forbidden:
            await ctx.send(
                "⚠️ Ich konnte dir keine Direktnachricht senden (DMs geschlossen?). "
                "Bitte aktiviere DMs von Servermitgliedern und versuche es erneut, "
                "da der Link nicht öffentlich im Kanal gepostet werden sollte."
            )

    @commands.command(name='disconnect')
    async def disconnect(self, ctx):
        """Entfernt die Verknüpfung deines Discord-Kontos wieder"""
        await DatabaseOperations.delete_oauth_link(self.db, ctx.author.id)
        await ctx.send("✅ Verknüpfung entfernt. Deine `!stats` zeigen wieder nur die öffentlichen Daten.")


async def setup(bot):
    await bot.add_cog(Account(bot))
