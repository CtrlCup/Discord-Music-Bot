import discord
from discord.ext import commands, tasks
import logging
import time
from datetime import datetime, timedelta
from typing import Optional
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.db_operations import DatabaseOperations
from utils.oauth_server import refresh_access_token, fetch_discord_user
from utils.permissions import is_user_check

logger = logging.getLogger('discord_bot.stats')

NITRO_TYPES = {0: 'Kein Nitro', 1: 'Nitro Classic', 2: 'Nitro', 3: 'Nitro Basic'}

LEADERBOARD_CATEGORIES = {
    'messages': {
        'label': 'Nachrichten',
        'emoji': '💬',
        'title': '💬 Nachrichten Rangliste',
        'description': 'Gesamtzahl aller im Server gesendeten Nachrichten pro Nutzer (seit Trackingbeginn).',
        'column': 'message_count',
    },
    'voice': {
        'label': 'Sprachzeit gesamt',
        'emoji': '🎤',
        'title': '🎤 Sprachkanal Rangliste',
        'description': 'Gesamte in Sprachkanälen verbrachte Zeit pro Nutzer (seit Trackingbeginn, über alle Kanäle summiert).',
        'column': 'voice_time_seconds',
    },
    'joins': {
        'label': 'Server-Beitritte',
        'emoji': '🚪',
        'title': '🚪 Server-Beitritte Rangliste',
        'description': 'Wie oft ein Nutzer dem Server insgesamt beigetreten ist (inkl. erneuter Beitritte nach Verlassen).',
        'column': 'join_count',
    },
    'longest_session': {
        'label': 'Längste Session',
        'emoji': '⏱️',
        'title': '⏱️ Längste Sprachkanal-Session',
        'description': 'Die am Stück längste Zeit in einem Sprachkanal pro Nutzer (einzelne Sitzung, nicht kumuliert).',
        'column': None,
    },
}

CATEGORY_ALIASES = {
    'messages': 'messages', 'nachrichten': 'messages',
    'voice': 'voice', 'sprache': 'voice',
    'joins': 'joins', 'beitritte': 'joins',
    'longest_session': 'longest_session', 'session': 'longest_session',
    'laengste': 'longest_session', 'längste': 'longest_session',
}


class LeaderboardView(discord.ui.View):
    """Buttons zum Umschalten zwischen den Leaderboard-Kategorien, ohne den Befehl neu einzugeben"""

    def __init__(self, cog: 'Stats', guild: discord.Guild, active_category: str, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild = guild
        for key, info in LEADERBOARD_CATEGORIES.items():
            button = discord.ui.Button(
                label=info['label'],
                emoji=info['emoji'],
                style=discord.ButtonStyle.primary if key == active_category else discord.ButtonStyle.secondary,
                custom_id=f'leaderboard:{key}'
            )
            button.callback = self._make_callback(key)
            self.add_item(button)

    def _make_callback(self, category: str):
        async def callback(interaction: discord.Interaction):
            embed = await self.cog.build_leaderboard_embed(self.guild, category)
            if embed is None:
                return await interaction.response.send_message("❌ Keine Daten verfügbar!", ephemeral=True)
            await interaction.response.edit_message(
                embed=embed, view=LeaderboardView(self.cog, self.guild, category)
            )
        return callback

class Stats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        self.voice_states = {}  # Track voice channel join times
        self.update_online_time.start()
    
    async def cog_load(self):
        """Retrieve the shared database instance from the bot"""
        self.db = self.bot.db
    
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
    
    async def _add_private_section(self, embed: discord.Embed, user):
        """Fügt private, per !connect freigeschaltete Profildaten hinzu (nur für den eigenen Discord-Account)"""
        oauth_db = getattr(self.bot, 'oauth_db', None)
        if oauth_db is None:
            return

        link = await DatabaseOperations.get_oauth_link(oauth_db, user.id)
        if not link:
            embed.add_field(
                name="🔒 Private Details",
                value="Verknüpfe dein Konto mit `!connect`, um zusätzliche Details freizuschalten.",
                inline=False
            )
            return

        access_token = link['access_token']
        expires_at = link['expires_at']
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        if expires_at <= datetime.utcnow():
            try:
                token_data = await refresh_access_token(self.bot.config['oauth'], link['refresh_token'])
                new_expires_at = datetime.utcfromtimestamp(time.time() + token_data.get('expires_in', 604800))
                await DatabaseOperations.upsert_oauth_link(
                    oauth_db, user.id,
                    token_data['access_token'], token_data['refresh_token'],
                    new_expires_at, token_data.get('scope', '')
                )
                access_token = token_data['access_token']
            except Exception:
                logger.exception(f"Konnte OAuth-Token für Nutzer {user.id} nicht erneuern")
                embed.add_field(
                    name="🔒 Private Details",
                    value="Verknüpfung abgelaufen. Bitte `!connect` erneut ausführen.",
                    inline=False
                )
                return

        try:
            discord_user = await fetch_discord_user(access_token)
        except Exception:
            logger.exception(f"Konnte Discord-Profildaten für Nutzer {user.id} nicht laden")
            return

        lines = []
        if discord_user.get('email'):
            lines.append(f"✉️ E-Mail: {discord_user['email']}")
        lines.append(f"🔐 MFA aktiviert: {'Ja' if discord_user.get('mfa_enabled') else 'Nein'}")
        if discord_user.get('locale'):
            lines.append(f"🌐 Sprache: {discord_user['locale']}")
        lines.append(f"💎 {NITRO_TYPES.get(discord_user.get('premium_type', 0), 'Unbekannt')}")

        embed.add_field(name="🔒 Private Details (via !connect)", value="\n".join(lines), inline=False)

    def _find_shared_guild(self, user: discord.abc.User) -> Optional[discord.Guild]:
        """Findet einen Server, auf dem sowohl der Bot als auch der Nutzer Mitglied sind
        (für !stats per Bot-Direktnachricht, wo es kein ctx.guild gibt)"""
        for guild in self.bot.guilds:
            if guild.get_member(user.id):
                return guild
        return None

    @commands.hybrid_command(name='stats')
    @is_user_check()
    async def stats(self, ctx, *, target: Optional[str] = None):
        """Zeigt Statistiken eines Benutzers an (wird immer per Direktnachricht verschickt)"""
        is_dm = ctx.guild is None

        if is_dm:
            if target is not None:
                return await ctx.send("❌ Per Direktnachricht kannst du nur deine eigenen Stats abrufen (ohne Zielangabe).")
            guild = self._find_shared_guild(ctx.author)
            if guild is None:
                return await ctx.send("❌ Wir teilen keinen gemeinsamen Server, auf dem ich Statistiken für dich erfasst habe.")
        else:
            guild = ctx.guild

        if target is None:
            # Show own stats
            user = ctx.author
            stats = await DatabaseOperations.get_user_stats(self.db, user.id, guild.id)
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
                    user = guild.get_member(user_id)
                except ValueError:
                    # Try to find by name
                    user = discord.utils.find(lambda m: m.name.lower() == target.lower() or str(m).lower() == target.lower(), guild.members)

            if user:
                stats = await DatabaseOperations.get_user_stats(self.db, user.id, guild.id)
            else:
                # Search in database by name
                stats = await DatabaseOperations.search_user_by_name(self.db, target, guild.id)
                if stats:
                    # Try to get the member object
                    user = guild.get_member(stats['user_id'])
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

        # Discord-ID und Konto-Erstellungsdatum stecken direkt in der Snowflake-ID und sind damit
        # öffentlich für jeden berechenbar - kein !connect nötig
        account_created = discord.utils.snowflake_time(user.id)
        embed.add_field(name="🆔 Discord-ID", value=str(user.id), inline=True)
        embed.add_field(
            name="📅 Konto erstellt am",
            value=account_created.strftime("%d.%m.%Y %H:%M"),
            inline=True
        )

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

        embed.add_field(
            name="🚪 Server-Beitritte",
            value=f"{stats.get('join_count', 0):,}",
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

        main_channel_id = await DatabaseOperations.get_main_channel(self.db, user.id, guild.id)
        if main_channel_id:
            main_channel = guild.get_channel(main_channel_id)
            embed.add_field(
                name="🔊 Hauptkanal",
                value=main_channel.name if main_channel else f"Kanal {main_channel_id}",
                inline=True
            )

        avg_session = await DatabaseOperations.get_avg_session(self.db, user.id, guild.id)
        if avg_session:
            embed.add_field(
                name="⏱️ Ø Sprachkanal-Session",
                value=self.format_duration(int(avg_session)),
                inline=True
            )

        companion = await DatabaseOperations.get_top_companion(self.db, guild.id, user.id)
        if companion:
            companion_member = guild.get_member(companion['user_id'])
            companion_name = companion_member.mention if companion_member else f"<@{companion['user_id']}>"
            embed.add_field(
                name="🧑‍🤝‍🧑 Häufigster Begleiter",
                value=f"{companion_name} ({self.format_duration(companion['overlap_seconds'])})",
                inline=True
            )

        # Add current voice channel if applicable
        if hasattr(user, 'voice') and user.voice and user.voice.channel:
            embed.add_field(
                name="🔊 Aktueller Sprachkanal",
                value=user.voice.channel.name,
                inline=True
            )

        # Private Zusatzdaten (nur bei eigenen Stats UND nur wenn direkt per Bot-DM angefragt -
        # aus einem oeffentlichen Kanal heraus bleiben sie auch in der Direktnachricht aussen vor)
        if target is None and is_dm:
            await self._add_private_section(embed, user)

        embed.set_footer(text=f"ID: {user.id}")

        if is_dm:
            await ctx.send(embed=embed)
            return

        try:
            await ctx.author.send(embed=embed)
            await ctx.send("📬 Ich habe dir die Stats per Direktnachricht geschickt!")
        except discord.Forbidden:
            await ctx.send(
                "⚠️ Ich konnte dir keine Direktnachricht senden (DMs geschlossen?). "
                "Bitte aktiviere DMs von Servermitgliedern und versuche es erneut."
            )
    
    async def _get_leaderboard_rows(self, guild_id: int, category: str):
        """Gibt eine Liste von {'user_id', 'username', 'value'} für die gegebene Kategorie zurück"""
        column = LEADERBOARD_CATEGORIES[category]['column']

        if column is None:  # longest_session hat eine eigene Query (siehe db_operations)
            return await DatabaseOperations.get_longest_session_leaderboard(self.db, guild_id)

        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                f"""
                SELECT user_id, username, {column}
                FROM user_stats
                WHERE guild_id = ?
                ORDER BY {column} DESC
                LIMIT 10
                """,
                (guild_id,)
            )
            rows = await cursor.fetchall()
            return [{'user_id': row['user_id'], 'username': row['username'], 'value': row[column]} for row in rows]
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        f"""
                        SELECT user_id, username, {column}
                        FROM user_stats
                        WHERE guild_id = %s
                        ORDER BY {column} DESC
                        LIMIT 10
                        """,
                        (guild_id,)
                    )
                    rows = await cursor.fetchall()
                    return [{'user_id': row[0], 'username': row[1], 'value': row[2]} for row in rows]

    async def build_leaderboard_embed(self, guild: discord.Guild, category: str) -> Optional[discord.Embed]:
        """Baut das Leaderboard-Embed für eine Kategorie - wird sowohl vom !leaderboard-Befehl
        als auch von den Umschalt-Buttons in LeaderboardView genutzt"""
        info = LEADERBOARD_CATEGORIES[category]
        rows = await self._get_leaderboard_rows(guild.id, category)
        if not rows:
            return None

        embed = discord.Embed(
            title=info['title'],
            description=info['description'],
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        for i, row in enumerate(rows, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."

            if category in ('voice', 'longest_session'):
                value_str = self.format_duration(row['value'])
            else:
                value_str = f"{row['value']:,}"

            member = guild.get_member(row['user_id'])
            name = member.display_name if member else row['username']

            embed.add_field(
                name=f"{medal} {name}",
                value=f"{info['emoji']} {value_str}",
                inline=False
            )

        embed.set_footer(text=f"Server: {guild.name}")
        return embed

    @commands.hybrid_command(name='leaderboard', aliases=['lb', 'top'])
    @is_user_check()
    async def leaderboard(self, ctx, category: str = 'messages'):
        """Zeigt die Rangliste für verschiedene Kategorien (Buttons zum Umschalten inklusive)"""
        resolved = CATEGORY_ALIASES.get(category.lower())
        if resolved is None:
            return await ctx.send(
                "❌ Ungültige Kategorie! Verfügbar: messages/nachrichten, voice/sprache, "
                "joins/beitritte, longest_session/session"
            )

        embed = await self.build_leaderboard_embed(ctx.guild, resolved)
        if embed is None:
            return await ctx.send("❌ Keine Daten verfügbar!")

        await ctx.send(embed=embed, view=LeaderboardView(self, ctx.guild, resolved))

async def setup(bot):
    await bot.add_cog(Stats(bot))
