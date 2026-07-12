import discord
from discord.ext import commands
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database

logger = logging.getLogger('discord_bot.statistics_advanced')

class StatisticsAdvanced(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        
    async def cog_load(self):
        """Initialize database when cog loads"""
        self.db = Database(self.bot.config)
        await self.db.initialize()
    
    async def get_top_songs(self, guild_id: int, days: int = 30, limit: int = 10) -> List[Dict]:
        """Get top played songs in the last X days"""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT song_title, song_url, COUNT(*) as play_count, 
                       SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END) as complete_plays
                FROM song_history
                WHERE guild_id = ? AND played_at > ?
                GROUP BY song_title, song_url
                ORDER BY play_count DESC
                LIMIT ?
                """,
                (guild_id, since_date, limit)
            )
            results = await cursor.fetchall()
            
            return [{
                'title': row['song_title'],
                'url': row['song_url'],
                'play_count': row['play_count'],
                'complete_plays': row['complete_plays']
            } for row in results]
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT song_title, song_url, COUNT(*) as play_count,
                               SUM(CASE WHEN skipped = FALSE THEN 1 ELSE 0 END) as complete_plays
                        FROM song_history
                        WHERE guild_id = %s AND played_at > %s
                        GROUP BY song_title, song_url
                        ORDER BY play_count DESC
                        LIMIT %s
                        """,
                        (guild_id, since_date, limit)
                    )
                    results = await cursor.fetchall()
                    
                    return [{
                        'title': row[0],
                        'url': row[1],
                        'play_count': row[2],
                        'complete_plays': row[3]
                    } for row in results]
    
    async def get_user_music_stats(self, guild_id: int, user_id: int, days: int = 30) -> Dict:
        """Get music statistics for a specific user"""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        if self.db.db_type == 'sqlite':
            # Total songs played
            cursor = await self.db.connection.execute(
                """
                SELECT COUNT(*) as total_plays,
                       SUM(CASE WHEN skipped = 0 THEN 1 ELSE 0 END) as complete_plays,
                       SUM(song_duration) as total_duration
                FROM song_history
                WHERE guild_id = ? AND user_id = ? AND played_at > ?
                """,
                (guild_id, user_id, since_date)
            )
            stats = await cursor.fetchone()
            
            # Top songs
            cursor = await self.db.connection.execute(
                """
                SELECT song_title, COUNT(*) as play_count
                FROM song_history
                WHERE guild_id = ? AND user_id = ? AND played_at > ?
                GROUP BY song_title
                ORDER BY play_count DESC
                LIMIT 5
                """,
                (guild_id, user_id, since_date)
            )
            top_songs = await cursor.fetchall()
            
            # Most active hours
            cursor = await self.db.connection.execute(
                """
                SELECT strftime('%H', played_at) as hour, COUNT(*) as plays
                FROM song_history
                WHERE guild_id = ? AND user_id = ? AND played_at > ?
                GROUP BY hour
                ORDER BY plays DESC
                LIMIT 1
                """,
                (guild_id, user_id, since_date)
            )
            peak_hour = await cursor.fetchone()
            
            return {
                'total_plays': stats['total_plays'] or 0,
                'complete_plays': stats['complete_plays'] or 0,
                'total_duration': stats['total_duration'] or 0,
                'top_songs': [{'title': row['song_title'], 'count': row['play_count']} for row in top_songs],
                'peak_hour': peak_hour['hour'] if peak_hour else None
            }
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Total songs played
                    await cursor.execute(
                        """
                        SELECT COUNT(*) as total_plays,
                               SUM(CASE WHEN skipped = FALSE THEN 1 ELSE 0 END) as complete_plays,
                               SUM(song_duration) as total_duration
                        FROM song_history
                        WHERE guild_id = %s AND user_id = %s AND played_at > %s
                        """,
                        (guild_id, user_id, since_date)
                    )
                    stats = await cursor.fetchone()
                    
                    # Top songs
                    await cursor.execute(
                        """
                        SELECT song_title, COUNT(*) as play_count
                        FROM song_history
                        WHERE guild_id = %s AND user_id = %s AND played_at > %s
                        GROUP BY song_title
                        ORDER BY play_count DESC
                        LIMIT 5
                        """,
                        (guild_id, user_id, since_date)
                    )
                    top_songs = await cursor.fetchall()
                    
                    # Most active hours
                    await cursor.execute(
                        """
                        SELECT HOUR(played_at) as hour, COUNT(*) as plays
                        FROM song_history
                        WHERE guild_id = %s AND user_id = %s AND played_at > %s
                        GROUP BY hour
                        ORDER BY plays DESC
                        LIMIT 1
                        """,
                        (guild_id, user_id, since_date)
                    )
                    peak_hour = await cursor.fetchone()
                    
                    return {
                        'total_plays': stats[0] or 0,
                        'complete_plays': stats[1] or 0,
                        'total_duration': stats[2] or 0,
                        'top_songs': [{'title': row[0], 'count': row[1]} for row in top_songs],
                        'peak_hour': peak_hour[0] if peak_hour else None
                    }
    
    async def get_server_music_stats(self, guild_id: int, days: int = 30) -> Dict:
        """Get music statistics for the entire server"""
        since_date = datetime.utcnow() - timedelta(days=days)
        
        if self.db.db_type == 'sqlite':
            # Total stats
            cursor = await self.db.connection.execute(
                """
                SELECT COUNT(*) as total_plays,
                       COUNT(DISTINCT user_id) as unique_listeners,
                       SUM(song_duration) as total_duration,
                       COUNT(DISTINCT song_title) as unique_songs
                FROM song_history
                WHERE guild_id = ? AND played_at > ?
                """,
                (guild_id, since_date)
            )
            stats = await cursor.fetchone()
            
            # Most active DJ
            cursor = await self.db.connection.execute(
                """
                SELECT user_id, COUNT(*) as play_count
                FROM song_history
                WHERE guild_id = ? AND played_at > ?
                GROUP BY user_id
                ORDER BY play_count DESC
                LIMIT 1
                """,
                (guild_id, since_date)
            )
            top_dj = await cursor.fetchone()
            
            return {
                'total_plays': stats['total_plays'] or 0,
                'unique_listeners': stats['unique_listeners'] or 0,
                'total_duration': stats['total_duration'] or 0,
                'unique_songs': stats['unique_songs'] or 0,
                'top_dj_id': top_dj['user_id'] if top_dj else None,
                'top_dj_plays': top_dj['play_count'] if top_dj else 0
            }
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Total stats
                    await cursor.execute(
                        """
                        SELECT COUNT(*) as total_plays,
                               COUNT(DISTINCT user_id) as unique_listeners,
                               SUM(song_duration) as total_duration,
                               COUNT(DISTINCT song_title) as unique_songs
                        FROM song_history
                        WHERE guild_id = %s AND played_at > %s
                        """,
                        (guild_id, since_date)
                    )
                    stats = await cursor.fetchone()
                    
                    # Most active DJ
                    await cursor.execute(
                        """
                        SELECT user_id, COUNT(*) as play_count
                        FROM song_history
                        WHERE guild_id = %s AND played_at > %s
                        GROUP BY user_id
                        ORDER BY play_count DESC
                        LIMIT 1
                        """,
                        (guild_id, since_date)
                    )
                    top_dj = await cursor.fetchone()
                    
                    return {
                        'total_plays': stats[0] or 0,
                        'unique_listeners': stats[1] or 0,
                        'total_duration': stats[2] or 0,
                        'unique_songs': stats[3] or 0,
                        'top_dj_id': top_dj[0] if top_dj else None,
                        'top_dj_plays': top_dj[1] if top_dj else 0
                    }
    
    def format_duration(self, seconds):
        """Format duration in seconds to readable string"""
        if not seconds:
            return "0 Minuten"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        parts = []
        if hours > 0:
            parts.append(f"{hours} Stunde{'n' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} Minute{'n' if minutes != 1 else ''}")
        
        return " ".join(parts) if parts else "0 Minuten"
    
    @commands.command(name='musicstats')
    async def music_stats(self, ctx, target: Optional[discord.Member] = None, days: int = 30):
        """Zeigt Musik-Statistiken für einen Benutzer oder dich selbst"""
        
        user = target or ctx.author
        stats = await self.get_user_music_stats(ctx.guild.id, user.id, days)
        
        embed = discord.Embed(
            title=f"🎵 Musik-Statistiken für {user.display_name}",
            description=f"Zeitraum: Letzte {days} Tage",
            color=discord.Color.purple(),
            timestamp=datetime.utcnow()
        )
        
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        
        # General stats
        embed.add_field(
            name="📊 Allgemein",
            value=f"**Songs gespielt:** {stats['total_plays']}\n"
                  f"**Vollständig gehört:** {stats['complete_plays']}\n"
                  f"**Gesamtdauer:** {self.format_duration(stats['total_duration'])}",
            inline=False
        )
        
        # Top songs
        if stats['top_songs']:
            top_songs_text = "\n".join([
                f"**{i+1}.** {song['title'][:30]} ({song['count']}x)"
                for i, song in enumerate(stats['top_songs'][:5])
            ])
            embed.add_field(
                name="🎵 Top Songs",
                value=top_songs_text,
                inline=False
            )
        
        # Additional info
        skip_rate = ((stats['total_plays'] - stats['complete_plays']) / stats['total_plays'] * 100) if stats['total_plays'] > 0 else 0
        peak_hour_line = f"**Aktivste Stunde:** {stats['peak_hour']}:00 Uhr" if stats['peak_hour'] else "Keine Stunden-Daten"
        embed.add_field(
            name="📈 Weitere Infos",
            value=f"**Skip-Rate:** {skip_rate:.1f}%\n{peak_hour_line}",
            inline=False
        )
        
        embed.set_footer(text=f"Angefordert von {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.command(name='topsongs')
    async def top_songs(self, ctx, days: int = 30):
        """Zeigt die meistgespielten Songs auf dem Server"""
        
        songs = await self.get_top_songs(ctx.guild.id, days)
        
        if not songs:
            return await ctx.send(f"❌ Keine Songs in den letzten {days} Tagen gespielt!")
        
        embed = discord.Embed(
            title=f"🎵 Top 10 Songs - {ctx.guild.name}",
            description=f"Meistgespielte Songs der letzten {days} Tage",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        
        for i, song in enumerate(songs[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            skip_rate = ((song['play_count'] - song['complete_plays']) / song['play_count'] * 100)
            
            embed.add_field(
                name=f"{medal} {song['title'][:50]}",
                value=f"**Plays:** {song['play_count']} | **Skip-Rate:** {skip_rate:.1f}%",
                inline=False
            )
        
        embed.set_footer(text=f"Angefordert von {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.command(name='servermusicstats')
    async def server_music_stats(self, ctx, days: int = 30):
        """Zeigt Server-weite Musik-Statistiken"""
        
        stats = await self.get_server_music_stats(ctx.guild.id, days)
        
        embed = discord.Embed(
            title=f"🎵 Server Musik-Statistiken",
            description=f"**{ctx.guild.name}** - Letzte {days} Tage",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )
        
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        
        embed.add_field(
            name="📊 Übersicht",
            value=f"**Total gespielt:** {stats['total_plays']} Songs\n"
                  f"**Unique Hörer:** {stats['unique_listeners']}\n"
                  f"**Unique Songs:** {stats['unique_songs']}\n"
                  f"**Gesamtdauer:** {self.format_duration(stats['total_duration'])}",
            inline=False
        )
        
        # Top DJ
        if stats['top_dj_id']:
            top_dj = ctx.guild.get_member(stats['top_dj_id'])
            if top_dj:
                embed.add_field(
                    name="🎧 Top DJ",
                    value=f"{top_dj.mention} mit **{stats['top_dj_plays']}** Songs",
                    inline=False
                )
        
        # Average stats
        if stats['total_plays'] > 0:
            avg_per_day = stats['total_plays'] / days
            avg_duration = stats['total_duration'] / stats['total_plays']
            
            embed.add_field(
                name="📈 Durchschnitt",
                value=f"**Songs pro Tag:** {avg_per_day:.1f}\n"
                      f"**Ø Song-Dauer:** {self.format_duration(int(avg_duration))}",
                inline=False
            )
        
        embed.set_footer(text=f"Angefordert von {ctx.author}")
        await ctx.send(embed=embed)
    
    @commands.command(name='listening')
    async def listening_activity(self, ctx, member: Optional[discord.Member] = None):
        """Zeigt aktuelle Spotify/Discord Aktivität"""
        
        user = member or ctx.author
        
        # Check for Spotify activity
        spotify = discord.utils.find(lambda a: isinstance(a, discord.Spotify), user.activities)
        
        if spotify:
            embed = discord.Embed(
                title=f"🎵 {user.display_name} hört gerade Spotify",
                color=spotify.color
            )
            
            embed.add_field(name="🎵 Song", value=spotify.title, inline=False)
            embed.add_field(name="🎤 Künstler", value=", ".join(spotify.artists), inline=False)
            embed.add_field(name="💿 Album", value=spotify.album, inline=False)
            
            # Duration
            duration = spotify.duration
            current = datetime.utcnow() - spotify.start
            progress = int((current.total_seconds() / duration.total_seconds()) * 20)
            bar = '█' * progress + '░' * (20 - progress)
            
            current_str = f"{int(current.total_seconds()) // 60}:{int(current.total_seconds()) % 60:02d}"
            duration_str = f"{duration.seconds // 60}:{duration.seconds % 60:02d}"
            
            embed.add_field(
                name="⏱️ Fortschritt",
                value=f"`{bar}`\n{current_str} / {duration_str}",
                inline=False
            )
            
            if spotify.album_cover_url:
                embed.set_thumbnail(url=spotify.album_cover_url)
            
            await ctx.send(embed=embed)
        else:
            # Check for other activities
            activity = discord.utils.find(lambda a: a.type == discord.ActivityType.listening, user.activities)
            
            if activity:
                embed = discord.Embed(
                    title=f"🎵 {user.display_name} hört gerade",
                    description=f"**{activity.name}**",
                    color=discord.Color.blue()
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ {user.display_name} hört gerade nichts!")

async def setup(bot):
    await bot.add_cog(StatisticsAdvanced(bot))
