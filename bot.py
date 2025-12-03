import discord
from discord.ext import commands
import json
import logging
import asyncio
import os
from datetime import datetime
import sys

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

# Load configuration
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error("config.json not found!")
        sys.exit(1)
    except json.JSONDecodeError:
        logger.error("config.json is not valid JSON!")
        sys.exit(1)

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
        
    async def setup_hook(self):
        # Load cogs
        await self.load_cogs()
        
    async def load_cogs(self):
        """Load all cogs from the cogs directory"""
        # Load advanced cogs instead of basic ones
        cog_files = ['music_advanced', 'stats', 'statistics_advanced', 'playlists', 'info']
        
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
            except:
                pass  # May not have permission in some servers
        
        # Initialize database
        from utils.database import Database
        db = Database(config)
        await db.initialize()
        
    async def on_guild_join(self, guild):
        logger.info(f'Joined new guild: {guild.name} (ID: {guild.id})')
        
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            await ctx.send(f"❌ Befehl nicht gefunden. Nutze `{ctx.prefix}info` für eine Liste aller Befehle.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Fehlende Argumente. Bitte überprüfe die Befehlssyntax.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏱️ Dieser Befehl ist auf Cooldown. Versuche es in {error.retry_after:.1f} Sekunden erneut.")
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
