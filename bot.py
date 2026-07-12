import discord
from discord.ext import commands
import json
import logging
import asyncio
import os
from datetime import datetime
import sys
from dotenv import load_dotenv

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
            'activity': os.getenv('BOT_ACTIVITY', 'Listening to !info'),
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
            'multi_channel_support': _env_bool('MUSIC_MULTI_CHANNEL_SUPPORT', True),
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
        self.oauth_db = None
        self.oauth_runner = None

    async def setup_hook(self):
        # Load cogs
        await self.load_cogs()

        # Shared DB handle + web server for the OAuth2 account-link flow (cogs/account.py)
        from utils.database import Database
        from utils.oauth_server import start_oauth_server
        self.oauth_db = Database(self.config)
        await self.oauth_db.initialize()
        self.oauth_runner = await start_oauth_server(self)

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
            name=config['bot']['activity'].replace("Listening to ", "")
        )
        await self.change_presence(activity=activity)
        
        # Try to set nickname to display_name if possible
        for guild in self.guilds:
            try:
                if guild.me.nick != config['bot']['display_name']:
                    await guild.me.edit(nick=config['bot']['display_name'])
            except discord.Forbidden:
                pass  # May not have permission in some servers
        
        # Initialize database
        from utils.database import Database
        db = Database(config)
        await db.initialize()
        
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
            await ctx.send("❌ Ein Fehler ist aufgetreten.")

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
