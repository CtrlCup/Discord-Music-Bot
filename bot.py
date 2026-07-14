import discord
from discord.ext import commands, tasks
import json
import logging
import asyncio
import os
from datetime import datetime
import sys
import time
from dotenv import load_dotenv


# Load general bot metadata first, then local environment configuration (which can override it)
load_dotenv('static.env')
load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

def _env_bool(name, default):
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in ('1', 'true', 'yes', 'on')

def _env_list(name, default):
    value = os.getenv(name)
    return default if not value else [item.strip() for item in value.split(',') if item.strip()]

# Load configuration entirely from environment variables (.env)
def load_config():
    if not os.getenv('DISCORD_BOT_TOKEN'):
        logger.error("DISCORD_BOT_TOKEN ist nicht in der .env gesetzt!")
        sys.exit(1)

    try:
        radio_streams = json.loads(os.getenv('RADIO_STREAMS', '[]'))
    except json.JSONDecodeError:
        logger.error("RADIO_STREAMS in der .env ist kein gültiges JSON!")
        sys.exit(1)

    return {
        'bot': {
            'token': os.getenv('DISCORD_BOT_TOKEN'),
            'display_name': os.getenv('BOT_DISPLAY_NAME', '🎵 MusicMaster Bot'),
            'prefix': _env_list('BOT_PREFIX', ['!', '/']),
            'activity': os.getenv('BOT_ACTIVITY', 'Hört auf /info'),
            'version': os.getenv('BOT_VERSION', '0.1.1'),
            'description': os.getenv('BOT_DESCRIPTION', 'Ein mit Rollen geschützter Musik- und Statistik-Bot'),
            'support_server': os.getenv('BOT_SUPPORT_SERVER', ''),
            'github': os.getenv('BOT_GITHUB', ''),
        },
        'database': {
            'type': os.getenv('DB_TYPE', 'sqlite'),
            'local': _env_bool('DB_LOCAL', True),
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'username': os.getenv('MYSQL_USER', 'root'),
            'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', 'discord_bot_stats'),
            'sqlite_path': os.getenv('SQLITE_PATH', 'bot_database.db'),
        },
        'music': {
            'timeout': int(os.getenv('MUSIC_TIMEOUT', '300')),
            'empty_channel_timeout': int(os.getenv('MUSIC_EMPTY_CHANNEL_TIMEOUT', '120')),
            'default_stream_url': os.getenv('MUSIC_DEFAULT_STREAM_URL', 'https://ilovemusic.de/iloveradio.m3u'),
            'radio_streams': radio_streams,
        },
        'features': {
            'playlists': {
                'max_playlists_per_user': int(os.getenv('PLAYLISTS_MAX_PER_USER', '10')),
            },
        },
        'notifications': {
            'song_change_default_enabled': _env_bool('NOTIFICATIONS_SONG_CHANGE_DEFAULT_ENABLED', True),
        },
        'oauth': {
            'client_id': os.getenv('DISCORD_OAUTH_CLIENT_ID', ''),
            'client_secret': os.getenv('DISCORD_OAUTH_CLIENT_SECRET', ''),
            'redirect_uri': os.getenv('DISCORD_OAUTH_REDIRECT_URI', ''),
            'web_port': int(os.getenv('OAUTH_WEB_PORT', '8080')),
            'scopes': _env_list('OAUTH_SCOPES', ['identify', 'email']),
        },
        'spotify': {
            'client_id': os.getenv('SPOTIFY_CLIENT_ID', ''),
            'client_secret': os.getenv('SPOTIFY_CLIENT_SECRET', ''),
        },
    }

config = load_config()

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.voice_states = True
        
        super().__init__(
            command_prefix=config['bot']['prefix'],
            intents=intents,
            help_command=None  # We'll create a custom help command
        )
        
        self.config = config
        self.start_time = datetime.utcnow()
        self.oauth_states = {}  # state -> (user_id, created_at), used by the !connect OAuth2 flow
        self.db = None
        self.oauth_db = None
        self.oauth_runner = None
        self._last_activity_time = time.time()
        self._current_status = discord.Status.offline
        self._current_activity = None

    async def setup_hook(self):
        # Shared DB handle (initialized before loading cogs so they can access self.bot.db)
        from utils.database import Database
        self.db = Database(self.config)
        await self.db.initialize()
        self.oauth_db = self.db

        # Load cogs
        await self.load_cogs()

        @self.before_invoke
        async def before_any_command(ctx):
            if not ctx.guild:
                # 1. Try to find a guild where the user is in a voice channel
                for g in self.guilds:
                    m = g.get_member(ctx.author.id)
                    if m and m.voice and m.voice.channel:
                        ctx.guild = g
                        ctx.author = m
                        break
                # 2. Fallback: find the first guild they share with the bot
                if not ctx.guild:
                    for g in self.guilds:
                        m = g.get_member(ctx.author.id)
                        if m:
                            ctx.guild = g
                            ctx.author = m
                            break

        # Web server for the OAuth2 account-link flow (cogs/account.py)
        from utils.oauth_server import start_oauth_server
        self.oauth_runner = await start_oauth_server(self)

        await self._sync_app_commands()
        self.presence_check_loop.start()

    async def _sync_app_commands(self):
        """Registriert alle Hybrid-Commands (siehe Cogs) als Discord Slash-Commands (/).
        Ist DEV_GUILD_ID gesetzt, werden die Commands NUR auf diesen einen Server
        synchronisiert (sofort sichtbar, praktisch zum Testen). Globale und
        Guild-spezifische Commands sind für Discord getrennte Objekte - würde man
        beides gleichzeitig syncen, erschiene jeder Befehl auf dem Dev-Server doppelt.
        Ohne DEV_GUILD_ID wird stattdessen global synchronisiert (kann bis zu einer
        Stunde dauern, bis es überall sichtbar ist) - das ist der Produktivmodus."""
        dev_guild_id = os.getenv('DEV_GUILD_ID')

        if dev_guild_id:
            try:
                # copy_global_to() muss vor dem Leeren der globalen Liste passieren,
                # da es die Commands aus genau dieser lokalen Liste kopiert
                guild = discord.Object(id=int(dev_guild_id))
                self.tree.copy_global_to(guild=guild)
                synced_guild = await self.tree.sync(guild=guild)
                logger.info(f"{len(synced_guild)} Slash-Commands sofort auf Server {dev_guild_id} synchronisiert (DEV_GUILD_ID gesetzt, kein globaler Sync)")
            except Exception:
                logger.exception("Guild-Slash-Command-Sync fehlgeschlagen")

            try:
                # Globale Commands danach leeren, damit keine alten globalen
                # Registrierungen neben dem Guild-Sync doppelt auftauchen
                self.tree.clear_commands(guild=None)
                await self.tree.sync()
            except Exception:
                logger.exception("Bereinigung der globalen Slash-Commands fehlgeschlagen")
        else:
            try:
                synced = await self.tree.sync()
                logger.info(f"{len(synced)} Slash-Commands global synchronisiert")
            except Exception:
                logger.exception("Globaler Slash-Command-Sync fehlgeschlagen")

    async def load_cogs(self):
        """Load all cogs from the cogs directory"""
        # Load advanced cogs instead of basic ones
        cog_files = ['music_advanced', 'stats', 'statistics_advanced', 'playlists', 'info', 'account', 'settings']

        for cog_file in cog_files:
            try:
                await self.load_extension(f'cogs.{cog_file}')
                logger.info(f'Loaded cog: {cog_file}')
            except Exception as e:
                logger.error(f'Failed to load cog {cog_file}: {e}')
    
    async def on_ready(self):
        logger.info(f'{self.user} ({config["bot"]["display_name"]}) has connected to Discord!')
        logger.info(f'Bot is in {len(self.guilds)} guilds')
        
        # Set bot activity
        activity = discord.Activity(
            type=discord.ActivityType.listening,
            name=config['bot']['activity']
        )
        await self.change_presence(activity=activity)
        
        # Try to set nickname to display_name if possible
        for guild in self.guilds:
            try:
                if guild.me.nick != config['bot']['display_name']:
                    await guild.me.edit(nick=config['bot']['display_name'])
            except discord.Forbidden:
                pass  # May not have permission in some servers
        
    async def on_guild_join(self, guild):
        logger.info(f'Joined new guild: {guild.name} (ID: {guild.id})')

    async def close(self):
        if self.oauth_runner:
            await self.oauth_runner.cleanup()
        await super().close()

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"❌ Befehl nicht gefunden. Nutze `{ctx.prefix}info` für eine Liste aller Befehle.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Fehlende Argumente. Bitte überprüfe die Befehlssyntax.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Dieser Befehl ist auf Cooldown. Versuche es in {error.retry_after:.1f} Sekunden erneut.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Dir fehlen die nötigen Berechtigungen für diesen Befehl.")
        else:
            logger.error(f'Unhandled error: {error}')
            await ctx.send(f"❌ Ein unerwarteter Fehler ist aufgetreten:\n`{error}`")

    async def change_presence(self, *, activity=None, status=None, shard_id=None):
        if status is not None:
            self._current_status = status
        if activity is not None:
            self._current_activity = activity
        await super().change_presence(activity=activity, status=status, shard_id=shard_id)

    def reset_activity_timer(self):
        self._last_activity_time = time.time()

    @tasks.loop(seconds=10)
    async def presence_check_loop(self):
        await self.update_presence()

    async def update_presence(self):
        is_playing = False
        for vc in self.voice_clients:
            if vc.is_connected() and (vc.is_playing() or vc.is_paused()):
                is_playing = True
                break

        current_time = time.time()
        time_since_activity = current_time - self._last_activity_time
        in_grace_period = time_since_activity < 120

        if is_playing:
            status = discord.Status.online
            activity = self.activity
        elif in_grace_period:
            status = discord.Status.online
            activity = discord.Activity(
                type=discord.ActivityType.listening,
                name=self.config['bot']['activity']
            )
        else:
            status = discord.Status.offline
            activity = None

        if self._current_status != status or self._current_activity != activity:
            await self.change_presence(status=status, activity=activity)

    async def on_command(self, ctx):
        self.reset_activity_timer()
        await self.update_presence()

    async def on_interaction(self, interaction):
        self.reset_activity_timer()
        await self.update_presence()

async def main():
    bot = MusicBot()
    
    try:
        await bot.start(config['bot']['token'])
    except discord.LoginFailure:
        logger.error("Invalid bot token! Please check config.json")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
