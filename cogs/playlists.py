import discord
from discord.ext import commands
import logging
from typing import Optional, List, Dict
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database

logger = logging.getLogger('discord_bot.playlists')

class Playlists(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        
    async def cog_load(self):
        """Initialize database when cog loads"""
        self.db = Database(self.bot.config)
        await self.db.initialize()
    
    async def create_playlist(self, user_id: int, guild_id: int, name: str, description: str = None, is_public: bool = False) -> bool:
        """Create a new playlist"""
        try:
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    """
                    INSERT INTO playlists (user_id, guild_id, name, description, is_public)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, guild_id, name, description, is_public)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            """
                            INSERT INTO playlists (user_id, guild_id, name, description, is_public)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (user_id, guild_id, name, description, is_public)
                        )
            return True
        except Exception as e:
            logger.error(f"Error creating playlist: {e}")
            return False
    
    async def get_playlist(self, user_id: int, guild_id: int, name: str) -> Optional[Dict]:
        """Get a specific playlist"""
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT * FROM playlists
                WHERE user_id = ? AND guild_id = ? AND name = ?
                """,
                (user_id, guild_id, name)
            )
            row = await cursor.fetchone()
            
            if row:
                return {
                    'id': row['id'],
                    'user_id': row['user_id'],
                    'guild_id': row['guild_id'],
                    'name': row['name'],
                    'description': row['description'],
                    'is_public': row['is_public'],
                    'created_at': row['created_at'],
                    'play_count': row['play_count']
                }
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM playlists
                        WHERE user_id = %s AND guild_id = %s AND name = %s
                        """,
                        (user_id, guild_id, name)
                    )
                    row = await cursor.fetchone()
                    
                    if row:
                        return {
                            'id': row[0],
                            'user_id': row[1],
                            'guild_id': row[2],
                            'name': row[3],
                            'description': row[4],
                            'is_public': row[5],
                            'created_at': row[6],
                            'play_count': row[8]
                        }
        return None
    
    async def get_user_playlists(self, user_id: int, guild_id: int) -> List[Dict]:
        """Get all playlists for a user"""
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT p.*, COUNT(ps.id) as song_count
                FROM playlists p
                LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id
                WHERE p.user_id = ? AND p.guild_id = ?
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """,
                (user_id, guild_id)
            )
            rows = await cursor.fetchall()
            
            return [{
                'id': row['id'],
                'name': row['name'],
                'description': row['description'],
                'is_public': row['is_public'],
                'song_count': row['song_count'],
                'play_count': row['play_count']
            } for row in rows]
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT p.*, COUNT(ps.id) as song_count
                        FROM playlists p
                        LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id
                        WHERE p.user_id = %s AND p.guild_id = %s
                        GROUP BY p.id
                        ORDER BY p.created_at DESC
                        """,
                        (user_id, guild_id)
                    )
                    rows = await cursor.fetchall()
                    
                    return [{
                        'id': row[0],
                        'name': row[3],
                        'description': row[4],
                        'is_public': row[5],
                        'song_count': row[9],
                        'play_count': row[8]
                    } for row in rows]
    
    async def add_song_to_playlist(self, playlist_id: int, title: str, url: str, duration: int = None) -> bool:
        """Add a song to a playlist"""
        try:
            if self.db.db_type == 'sqlite':
                # Get next position
                cursor = await self.db.connection.execute(
                    "SELECT MAX(position) as max_pos FROM playlist_songs WHERE playlist_id = ?",
                    (playlist_id,)
                )
                result = await cursor.fetchone()
                position = (result['max_pos'] or 0) + 1
                
                await self.db.connection.execute(
                    """
                    INSERT INTO playlist_songs (playlist_id, song_title, song_url, song_duration, position)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (playlist_id, title, url, duration, position)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        # Get next position
                        await cursor.execute(
                            "SELECT MAX(position) as max_pos FROM playlist_songs WHERE playlist_id = %s",
                            (playlist_id,)
                        )
                        result = await cursor.fetchone()
                        position = (result[0] or 0) + 1
                        
                        await cursor.execute(
                            """
                            INSERT INTO playlist_songs (playlist_id, song_title, song_url, song_duration, position)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (playlist_id, title, url, duration, position)
                        )
            return True
        except Exception as e:
            logger.error(f"Error adding song to playlist: {e}")
            return False
    
    async def get_playlist_songs(self, playlist_id: int) -> List[Dict]:
        """Get all songs in a playlist"""
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT * FROM playlist_songs
                WHERE playlist_id = ?
                ORDER BY position
                """,
                (playlist_id,)
            )
            rows = await cursor.fetchall()
            
            return [{
                'title': row['song_title'],
                'url': row['song_url'],
                'duration': row['song_duration'],
                'position': row['position']
            } for row in rows]
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM playlist_songs
                        WHERE playlist_id = %s
                        ORDER BY position
                        """,
                        (playlist_id,)
                    )
                    rows = await cursor.fetchall()
                    
                    return [{
                        'title': row[2],
                        'url': row[3],
                        'duration': row[4],
                        'position': row[5]
                    } for row in rows]
    
    async def delete_playlist(self, user_id: int, guild_id: int, name: str) -> bool:
        """Delete a playlist"""
        try:
            playlist = await self.get_playlist(user_id, guild_id, name)
            if not playlist:
                return False
            
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    "DELETE FROM playlists WHERE id = ?",
                    (playlist['id'],)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "DELETE FROM playlists WHERE id = %s",
                            (playlist['id'],)
                        )
            return True
        except Exception as e:
            logger.error(f"Error deleting playlist: {e}")
            return False
    
    async def add_favorite(self, user_id: int, guild_id: int, title: str, url: str) -> bool:
        """Add a song to favorites"""
        try:
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    """
                    INSERT INTO favorite_songs (user_id, guild_id, song_title, song_url)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, guild_id, song_url) DO UPDATE SET play_count = play_count + 1
                    """,
                    (user_id, guild_id, title, url)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            """
                            INSERT INTO favorite_songs (user_id, guild_id, song_title, song_url)
                            VALUES (%s, %s, %s, %s)
                            ON DUPLICATE KEY UPDATE play_count = play_count + 1
                            """,
                            (user_id, guild_id, title, url)
                        )
            return True
        except Exception as e:
            logger.error(f"Error adding favorite: {e}")
            return False
    
    async def get_favorites(self, user_id: int, guild_id: int) -> List[Dict]:
        """Get user's favorite songs"""
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT * FROM favorite_songs
                WHERE user_id = ? AND guild_id = ?
                ORDER BY added_at DESC
                LIMIT 20
                """,
                (user_id, guild_id)
            )
            rows = await cursor.fetchall()
            
            return [{
                'title': row['song_title'],
                'url': row['song_url'],
                'play_count': row['play_count']
            } for row in rows]
        else:
            async with self.db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM favorite_songs
                        WHERE user_id = %s AND guild_id = %s
                        ORDER BY added_at DESC
                        LIMIT 20
                        """,
                        (user_id, guild_id)
                    )
                    rows = await cursor.fetchall()
                    
                    return [{
                        'title': row[3],
                        'url': row[4],
                        'play_count': row[6]
                    } for row in rows]
    
    @commands.group(name='playlist', aliases=['pl'], invoke_without_command=True)
    async def playlist(self, ctx):
        """Playlist-Verwaltung"""
        embed = discord.Embed(
            title="📃 Playlist-Befehle",
            description="Verwalte deine persönlichen Playlists",
            color=discord.Color.blue()
        )
        
        commands_list = [
            "`!playlist create <name>` - Neue Playlist erstellen",
            "`!playlist list` - Deine Playlists anzeigen",
            "`!playlist show <name>` - Songs in Playlist anzeigen",
            "`!playlist add <playlist> <song>` - Song zu Playlist hinzufügen",
            "`!playlist remove <playlist> <position>` - Song aus Playlist entfernen",
            "`!playlist delete <name>` - Playlist löschen",
            "`!playlist play <name>` - Playlist abspielen",
            "`!playlist public <name>` - Playlist öffentlich/privat machen",
            "`!playlist search <query>` - Öffentliche Playlists suchen"
        ]
        
        embed.add_field(
            name="Verfügbare Befehle",
            value="\n".join(commands_list),
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @playlist.command(name='create')
    async def playlist_create(self, ctx, *, name: str):
        """Erstellt eine neue Playlist"""
        
        # Check playlist limit
        playlists = await self.get_user_playlists(ctx.author.id, ctx.guild.id)
        max_playlists = self.bot.config['features']['playlists']['max_playlists_per_user']
        
        if len(playlists) >= max_playlists:
            return await ctx.send(f"❌ Du hast bereits die maximale Anzahl von {max_playlists} Playlists erreicht!")
        
        # Check if name already exists
        existing = await self.get_playlist(ctx.author.id, ctx.guild.id, name)
        if existing:
            return await ctx.send("❌ Eine Playlist mit diesem Namen existiert bereits!")
        
        # Create playlist
        success = await self.create_playlist(ctx.author.id, ctx.guild.id, name)
        
        if success:
            await ctx.send(f"✅ Playlist **{name}** wurde erfolgreich erstellt!")
        else:
            await ctx.send("❌ Fehler beim Erstellen der Playlist!")
    
    @playlist.command(name='list')
    async def playlist_list(self, ctx, member: Optional[discord.Member] = None):
        """Zeigt deine oder öffentliche Playlists eines anderen Benutzers"""
        
        user = member or ctx.author
        is_own = user == ctx.author
        
        playlists = await self.get_user_playlists(user.id, ctx.guild.id)
        
        if not is_own:
            # Filter only public playlists
            playlists = [p for p in playlists if p['is_public']]
        
        if not playlists:
            if is_own:
                return await ctx.send("❌ Du hast noch keine Playlists!")
            else:
                return await ctx.send(f"❌ {user.display_name} hat keine öffentlichen Playlists!")
        
        embed = discord.Embed(
            title=f"📃 {'Deine' if is_own else f'{user.display_name}s'} Playlists",
            color=discord.Color.blue()
        )
        
        for i, pl in enumerate(playlists[:10], 1):
            visibility = "🔓 Öffentlich" if pl['is_public'] else "🔒 Privat"
            embed.add_field(
                name=f"{i}. {pl['name']}",
                value=f"{visibility} | {pl['song_count']} Songs | {pl['play_count']} Plays",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @playlist.command(name='show')
    async def playlist_show(self, ctx, *, name: str):
        """Zeigt die Songs in einer Playlist"""
        
        playlist = await self.get_playlist(ctx.author.id, ctx.guild.id, name)
        
        if not playlist:
            return await ctx.send("❌ Playlist nicht gefunden!")
        
        songs = await self.get_playlist_songs(playlist['id'])
        
        if not songs:
            return await ctx.send(f"📃 Playlist **{name}** ist leer!")
        
        embed = discord.Embed(
            title=f"📃 Playlist: {name}",
            description=playlist['description'] or "Keine Beschreibung",
            color=discord.Color.blue()
        )
        
        songs_text = ""
        for i, song in enumerate(songs[:20], 1):
            duration = f" ({song['duration'] // 60}:{song['duration'] % 60:02d})" if song['duration'] else ""
            songs_text += f"**{i}.** {song['title'][:40]}{duration}\n"
        
        embed.add_field(
            name=f"Songs ({len(songs)} gesamt)",
            value=songs_text[:1024],
            inline=False
        )
        
        if len(songs) > 20:
            embed.set_footer(text=f"... und {len(songs) - 20} weitere Songs")
        
        await ctx.send(embed=embed)
    
    @playlist.command(name='delete')
    async def playlist_delete(self, ctx, *, name: str):
        """Löscht eine Playlist"""
        
        success = await self.delete_playlist(ctx.author.id, ctx.guild.id, name)
        
        if success:
            await ctx.send(f"✅ Playlist **{name}** wurde gelöscht!")
        else:
            await ctx.send("❌ Playlist nicht gefunden oder Fehler beim Löschen!")
    
    @commands.command(name='favorite', aliases=['fav'])
    async def favorite(self, ctx):
        """Fügt den aktuellen Song zu deinen Favoriten hinzu"""
        
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ Es läuft gerade kein Song!")
        
        # Get current song from music cog
        music_cog = self.bot.get_cog('MusicAdvanced')
        if not music_cog:
            return await ctx.send("❌ Musik-System nicht verfügbar!")
        
        state = music_cog.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        if not queue.current:
            return await ctx.send("❌ Kein Song in der Warteschlange!")
        
        success = await self.add_favorite(
            ctx.author.id,
            ctx.guild.id,
            queue.current['title'],
            queue.current['url']
        )
        
        if success:
            await ctx.send(f"❤️ **{queue.current['title']}** zu deinen Favoriten hinzugefügt!")
        else:
            await ctx.send("❌ Fehler beim Hinzufügen zu Favoriten!")
    
    @commands.command(name='favorites', aliases=['favs'])
    async def favorites(self, ctx):
        """Zeigt deine Lieblingssongs"""
        
        favorites = await self.get_favorites(ctx.author.id, ctx.guild.id)
        
        if not favorites:
            return await ctx.send("❌ Du hast noch keine Favoriten!")
        
        embed = discord.Embed(
            title="❤️ Deine Lieblingssongs",
            color=discord.Color.red()
        )
        
        fav_text = ""
        for i, fav in enumerate(favorites[:10], 1):
            fav_text += f"**{i}.** {fav['title'][:50]}\n"
        
        embed.add_field(
            name=f"Top {min(10, len(favorites))} Favoriten",
            value=fav_text,
            inline=False
        )
        
        if len(favorites) > 10:
            embed.set_footer(text=f"... und {len(favorites) - 10} weitere Favoriten")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Playlists(bot))
