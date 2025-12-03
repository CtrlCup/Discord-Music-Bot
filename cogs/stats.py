import discord
from discord.ext import commands, tasks
import logging
from datetime import datetime, timedelta
from typing import Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.db_operations import DatabaseOperations

logger = logging.getLogger('discord_bot.stats')

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.voice_states = {}  # Track voice channel join times
        self.update_online_time.start()
    
    async def cog_load(self):
        """Initialize database when cog loads"""
        self.db = Database(self.bot.config)
        await self.db.initialize()
    
    def cog_unload(self):
        """Clean up when cog unloads"""
        self.update_online_time.cancel()
    
    @tasks.loop(minutes=5)
    async def update_online_time(self):
        """Update online time for all users periodically"""
        if not self.db:
            return
        
        for guild in self.bot.guilds:
            for member in guild.members:
                if not member.bot and member.status != discord.Status.offline:
                    try:
                        await DatabaseOperations.update_user_stats(
                            self.db,
                            member.id,
                            guild.id,
                            str(member),
                            'online_update',
                            time_seconds=300  # 5 minutes in seconds
                        )
                    except Exception as e:
                        logger.error(f"Error updating online time for {member}: {e}")
    
    @update_online_time.before_loop
    async def before_update_online_time(self):
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Track messages sent by users"""
        if message.author.bot or not message.guild:
            return
        
        try:
            await DatabaseOperations.update_user_stats(
                self.db,
                message.author.id,
                message.guild.id,
                str(message.author),
                'message',
                channel_id=message.channel.id,
                message_length=len(message.content)
            )
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Track voice channel activity"""
        if member.bot:
            return
        
        try:
            # User joined a voice channel
            if before.channel is None and after.channel is not None:
                self.voice_states[member.id] = datetime.utcnow()
                await DatabaseOperations.update_user_stats(
                    self.db,
                    member.id,
                    member.guild.id,
                    str(member),
                    'voice_join',
                    channel_id=after.channel.id
                )
                logger.info(f"{member} joined voice channel {after.channel}")
            
            # User left a voice channel
            elif before.channel is not None and after.channel is None:
                if member.id in self.voice_states:
                    del self.voice_states[member.id]
                await DatabaseOperations.update_user_stats(
                    self.db,
                    member.id,
                    member.guild.id,
                    str(member),
                    'voice_leave'
                )
                logger.info(f"{member} left voice channel {before.channel}")
            
            # User switched voice channels
            elif before.channel != after.channel and before.channel is not None and after.channel is not None:
                # End previous session
                await DatabaseOperations.update_user_stats(
                    self.db,
                    member.id,
                    member.guild.id,
                    str(member),
                    'voice_leave'
                )
                # Start new session
                self.voice_states[member.id] = datetime.utcnow()
                await DatabaseOperations.update_user_stats(
                    self.db,
                    member.id,
                    member.guild.id,
                    str(member),
                    'voice_join',
                    channel_id=after.channel.id
                )
                logger.info(f"{member} switched from {before.channel} to {after.channel}")
                
        except Exception as e:
            logger.error(f"Error tracking voice state: {e}")
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Track when a member joins the server"""
        if member.bot:
            return
        
        try:
            await DatabaseOperations.update_user_stats(
                self.db,
                member.id,
                member.guild.id,
                str(member),
                'server_join'
            )
        except Exception as e:
            logger.error(f"Error tracking member join: {e}")
    
    def format_duration(self, seconds):
        """Format duration in seconds to readable string"""
        if seconds is None or seconds == 0:
            return "0 Sekunden"
        
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        parts = []
        if days > 0:
            parts.append(f"{days} Tag{'e' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} Stunde{'n' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} Minute{'n' if minutes != 1 else ''}")
        if secs > 0 and days == 0:  # Only show seconds if less than a day
            parts.append(f"{secs} Sekunde{'n' if secs != 1 else ''}")
        
        if len(parts) == 0:
            return "0 Sekunden"
        elif len(parts) == 1:
            return parts[0]
        else:
            return ", ".join(parts[:-1]) + f" und {parts[-1]}"
    
    @commands.command(name='stats')
    async def stats(self, ctx, *, target: Optional[str] = None):
        """Zeigt Statistiken eines Benutzers an"""
        
        if target is None:
            # Show own stats
            user = ctx.author
            stats = await DatabaseOperations.get_user_stats(self.db, user.id, ctx.guild.id)
        else:
            # Try to find user by mention, ID, or name
            user = None
            
            # Check if it's a mention
            if len(ctx.message.mentions) > 0:
                user = ctx.message.mentions[0]
            else:
                # Try to find by ID
                try:
                    user_id = int(target)
                    user = ctx.guild.get_member(user_id)
                except ValueError:
                    # Try to find by name
                    user = discord.utils.find(lambda m: m.name.lower() == target.lower() or str(m).lower() == target.lower(), ctx.guild.members)
            
            if user:
                stats = await DatabaseOperations.get_user_stats(self.db, user.id, ctx.guild.id)
            else:
                # Search in database by name
                stats = await DatabaseOperations.search_user_by_name(self.db, target, ctx.guild.id)
                if stats:
                    # Try to get the member object
                    user = ctx.guild.get_member(stats['user_id'])
                    if not user:
                        # Create a fake user object for display
                        class FakeUser:
                            def __init__(self, name, id):
                                self.name = name
                                self.display_name = name
                                self.id = id
                                self.avatar = None
                        user = FakeUser(stats['username'], stats['user_id'])
        
        if not stats:
            return await ctx.send("❌ Keine Statistiken für diesen Benutzer gefunden!")
        
        # Create embed
        embed = discord.Embed(
            title=f"📊 Statistiken für {user.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if hasattr(user, 'avatar') and user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        # Add fields
        if stats['first_joined']:
            first_joined = datetime.fromisoformat(str(stats['first_joined']))
            embed.add_field(
                name="🚪 Erstes Mal beigetreten",
                value=first_joined.strftime("%d.%m.%Y %H:%M"),
                inline=True
            )
        
        if stats['last_seen']:
            last_seen = datetime.fromisoformat(str(stats['last_seen']))
            embed.add_field(
                name="👁️ Zuletzt gesehen",
                value=last_seen.strftime("%d.%m.%Y %H:%M"),
                inline=True
            )
        
        embed.add_field(
            name="💬 Nachrichten gesendet",
            value=f"{stats['message_count']:,}",
            inline=True
        )
        
        embed.add_field(
            name="🎤 Zeit in Sprachkanälen",
            value=self.format_duration(stats['voice_time_seconds']),
            inline=True
        )
        
        # Calculate days since first join
        if stats['first_joined']:
            first_joined = datetime.fromisoformat(str(stats['first_joined']))
            days_on_server = (datetime.utcnow() - first_joined).days
            embed.add_field(
                name="📅 Tage auf dem Server",
                value=f"{days_on_server:,}",
                inline=True
            )
        
        # Add current voice channel if applicable
        if hasattr(user, 'voice') and user.voice and user.voice.channel:
            embed.add_field(
                name="🔊 Aktueller Sprachkanal",
                value=user.voice.channel.name,
                inline=True
            )
        
        embed.set_footer(text=f"ID: {user.id}")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='leaderboard', aliases=['lb', 'top'])
    async def leaderboard(self, ctx, category: str = 'messages'):
        """Zeigt die Rangliste für verschiedene Kategorien"""
        
        valid_categories = ['messages', 'voice', 'nachrichten', 'sprache']
        if category.lower() not in valid_categories:
            return await ctx.send("❌ Ungültige Kategorie! Verwende: messages/nachrichten oder voice/sprache")
        
        # Determine actual category
        if category.lower() in ['messages', 'nachrichten']:
            order_by = 'message_count'
            title = "💬 Nachrichten Rangliste"
            icon = "💬"
        else:
            order_by = 'voice_time_seconds'
            title = "🎤 Sprachkanal Rangliste"
            icon = "🎤"
        
        # Get top 10 users
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                f"""
                SELECT user_id, username, {order_by}
                FROM user_stats
                WHERE guild_id = ?
                ORDER BY {order_by} DESC
                LIMIT 10
                """,
                (ctx.guild.id,)
            )
            results = await cursor.fetchall()
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f"""
                        SELECT user_id, username, {order_by}
                        FROM user_stats
                        WHERE guild_id = %s
                        ORDER BY {order_by} DESC
                        LIMIT 10
                        """,
                        (ctx.guild.id,)
                    )
                    results = await cursor.fetchall()
        
        if not results:
            return await ctx.send("❌ Keine Daten verfügbar!")
        
        embed = discord.Embed(
            title=title,
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        for i, row in enumerate(results, 1):
            if self.db.db_type == 'sqlite':
                user_id, username, value = row['user_id'], row['username'], row[order_by]
            else:
                user_id, username, value = row
            
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            if order_by == 'voice_time_seconds':
                value_str = self.format_duration(value)
            else:
                value_str = f"{value:,}"
            
            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else username
            
            embed.add_field(
                name=f"{medal} {name}",
                value=f"{icon} {value_str}",
                inline=False
            )
        
        embed.set_footer(text=f"Server: {ctx.guild.name}")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Stats(bot))
