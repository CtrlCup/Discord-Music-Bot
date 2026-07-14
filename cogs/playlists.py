import discord
from discord.ext import commands
import logging
from typing import Optional, List, Dict
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.database import Database
from utils.permissions import is_user_check
from utils.music_utils import ytdl
from utils import track_resolver

logger = logging.getLogger('discord_bot.playlists')

class Playlists(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None
        
    async def cog_load(self):
        """Retrieve the shared database instance from the bot"""
        self.db = self.bot.db
    
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

    async def remove_song_from_playlist(self, playlist_id: int, position: int) -> bool:
        """Remove a song from a playlist and re-order the remaining songs"""
        try:
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    "DELETE FROM playlist_songs WHERE playlist_id = ? AND position = ?",
                    (playlist_id, position)
                )
                await self.db.connection.execute(
                    """
                    UPDATE playlist_songs
                    SET position = position - 1
                    WHERE playlist_id = ? AND position > ?
                    """,
                    (playlist_id, position)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "DELETE FROM playlist_songs WHERE playlist_id = %s AND position = %s",
                            (playlist_id, position)
                        )
                        await cursor.execute(
                            """
                            UPDATE playlist_songs
                            SET position = position - 1
                            WHERE playlist_id = %s AND position > %s
                            """,
                            (playlist_id, position)
                        )
            return True
        except Exception as e:
            logger.error(f"Error removing song from playlist: {e}")
            return False

    async def get_public_playlist_by_name(self, guild_id: int, name: str) -> Optional[Dict]:
        """Get a public playlist by name in a guild"""
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT * FROM playlists
                WHERE guild_id = ? AND name = ? AND is_public = 1
                """,
                (guild_id, name)
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
                        WHERE guild_id = %s AND name = %s AND is_public = 1
                        """,
                        (guild_id, name)
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

    async def toggle_playlist_public(self, playlist_id: int, current_public: bool) -> bool:
        """Toggle the public status of a playlist"""
        try:
            new_val = 0 if current_public else 1
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    "UPDATE playlists SET is_public = ? WHERE id = ?",
                    (new_val, playlist_id)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            "UPDATE playlists SET is_public = %s WHERE id = %s",
                            (new_val, playlist_id)
                        )
            return True
        except Exception as e:
            logger.error(f"Error toggling playlist visibility: {e}")
            return False

    async def search_public_playlists(self, guild_id: int, query: str) -> List[Dict]:
        """Search public playlists in a guild"""
        like_query = f"%{query}%"
        if self.db.db_type == 'sqlite':
            cursor = await self.db.connection.execute(
                """
                SELECT p.*, COUNT(ps.id) as song_count
                FROM playlists p
                LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id
                WHERE p.guild_id = ? AND p.is_public = 1 AND (p.name LIKE ? OR p.description LIKE ?)
                GROUP BY p.id
                ORDER BY p.created_at DESC
                """,
                (guild_id, like_query, like_query)
            )
            rows = await cursor.fetchall()
            return [{
                'id': row['id'],
                'user_id': row['user_id'],
                'name': row['name'],
                'description': row['description'],
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
                        WHERE p.guild_id = %s AND p.is_public = 1 AND (p.name LIKE %s OR p.description LIKE %s)
                        GROUP BY p.id
                        ORDER BY p.created_at DESC
                        """,
                        (guild_id, like_query, like_query)
                    )
                    rows = await cursor.fetchall()
                    return [{
                        'id': row[0],
                        'user_id': row[1],
                        'name': row[3],
                        'description': row[4],
                        'song_count': row[9],
                        'play_count': row[8]
                    } for row in rows]

    @commands.hybrid_group(name='playlist', aliases=['pl'], invoke_without_command=True)
    @is_user_check()
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

    @playlist.command(name='add')
    async def playlist_add(self, ctx, playlist_name: str, *, query: str):
        """Fügt einen oder mehrere Songs zu einer Playlist hinzu"""
        playlist = await self.get_playlist(ctx.author.id, ctx.guild.id, playlist_name)
        if not playlist:
            return await ctx.send("❌ Playlist nicht gefunden!")
        
        async with ctx.typing():
            try:
                resolved_queries = await track_resolver.resolve(self.bot.config, query)
                if resolved_queries is not None:
                    if not resolved_queries:
                        return await ctx.send("❌ Konnte keine Songs zu diesem Link finden.")
                    added = 0
                    failed_songs = []
                    for resolved_query in resolved_queries:
                        display_name = resolved_query
                        if display_name.startswith("ytsearch1:"):
                            display_name = display_name[len("ytsearch1:"):]
                        
                        try:
                            entry_data = await self.bot.loop.run_in_executor(
                                None, lambda q=resolved_query: ytdl.extract_info(q, download=False)
                            )
                            entry = entry_data['entries'][0] if 'entries' in entry_data and entry_data['entries'] else entry_data
                            if not entry:
                                failed_songs.append(display_name)
                                continue
                            title = entry.get('title', 'Unknown')
                            url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                            duration = entry.get('duration')
                            if await self.add_song_to_playlist(playlist['id'], title, url, duration):
                                added += 1
                            else:
                                failed_songs.append(display_name)
                        except Exception:
                            logger.exception(f"Fehler beim Auflösen/Hinzufügen von {resolved_query}")
                            failed_songs.append(display_name)
                    
                    if added == 0:
                        await ctx.send("❌ Konnte keine Songs zur Playlist hinzufügen.")
                    elif added == 1:
                        await ctx.send(f"✅ Song wurde zur Playlist **{playlist_name}** hinzugefügt!")
                    else:
                        await ctx.send(f"✅ {added} Songs wurden zur Playlist **{playlist_name}** hinzugefügt!")

                    if failed_songs:
                        failed_str = ", ".join(f"**{s}**" for s in failed_songs[:10])
                        if len(failed_songs) > 10:
                            failed_str += f" und {len(failed_songs) - 10} weitere"
                        await ctx.send(f"⚠️ Folgende Songs konnten auf YouTube nicht gefunden werden: {failed_str}")
                else:
                    entry_data = await self.bot.loop.run_in_executor(
                        None, lambda: ytdl.extract_info(query, download=False)
                    )
                    entry = entry_data['entries'][0] if 'entries' in entry_data else entry_data
                    if not entry:
                        return await ctx.send("❌ Song konnte nicht gefunden/aufgelöst werden.")

                    title = entry.get('title', 'Unknown')
                    url = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
                    duration = entry.get('duration')

                    success = await self.add_song_to_playlist(playlist['id'], title, url, duration)
                    if success:
                        await ctx.send(f"✅ **{title}** wurde zur Playlist **{playlist_name}** hinzugefügt!")
                    else:
                        await ctx.send("❌ Fehler beim Hinzufügen des Songs zur Playlist.")
            except Exception as e:
                logger.exception("Fehler beim Hinzufügen zur Playlist")
                await ctx.send(f"❌ Fehler: {e}")

    @playlist.command(name='remove')
    async def playlist_remove(self, ctx, playlist_name: str, position: int):
        """Entfernt einen Song an einer bestimmten Position aus der Playlist"""
        playlist = await self.get_playlist(ctx.author.id, ctx.guild.id, playlist_name)
        if not playlist:
            return await ctx.send("❌ Playlist nicht gefunden!")
        
        songs = await self.get_playlist_songs(playlist['id'])
        if position < 1 or position > len(songs):
            return await ctx.send(f"❌ Ungültige Position. Die Playlist hat {len(songs)} Songs.")
        
        target_song = songs[position - 1]
        success = await self.remove_song_from_playlist(playlist['id'], position)
        if success:
            await ctx.send(f"✅ **{target_song['title']}** wurde aus Playlist **{playlist_name}** entfernt!")
        else:
            await ctx.send("❌ Fehler beim Entfernen des Songs!")

    @playlist.command(name='play')
    async def playlist_play(self, ctx, *, name: str):
        """Spielt alle Songs einer Playlist ab (fügt sie der Warteschlange hinzu)"""
        playlist = await self.get_playlist(ctx.author.id, ctx.guild.id, name)
        if not playlist:
            playlist = await self.get_public_playlist_by_name(ctx.guild.id, name)
            if not playlist:
                return await ctx.send("❌ Playlist nicht gefunden!")
        
        songs = await self.get_playlist_songs(playlist['id'])
        if not songs:
            return await ctx.send("❌ Diese Playlist ist leer!")
        
        music_cog = self.bot.get_cog('MusicAdvanced')
        if not music_cog:
            return await ctx.send("❌ Musik-System nicht verfügbar!")
        
        vc = await music_cog.get_voice_client_for_user(ctx)
        if not vc:
            return
        
        state = music_cog.get_guild_state(ctx.guild.id)
        queue = state.get_queue(vc.channel.id)
        
        added = 0
        for song in songs:
            song_data = {
                'url': song['url'],
                'title': song['title'],
                'duration': song['duration'],
                'requester': ctx.author
            }
            queue.add(song_data)
            added += 1
        
        await ctx.send(f"✅ {added} Songs aus Playlist **{name}** zur Warteschlange hinzugefügt!")
        if not vc.is_playing() and not vc.is_paused():
            await music_cog.play_next(ctx, vc.channel.id)

    @playlist.command(name='public')
    async def playlist_public(self, ctx, *, name: str):
        """Schaltet die Playlist zwischen öffentlich und privat um"""
        playlist = await self.get_playlist(ctx.author.id, ctx.guild.id, name)
        if not playlist:
            return await ctx.send("❌ Playlist nicht gefunden!")
        
        success = await self.toggle_playlist_public(playlist['id'], playlist['is_public'])
        if success:
            status_str = "öffentlich 🔓" if not playlist['is_public'] else "privat 🔒"
            await ctx.send(f"✅ Playlist **{name}** ist jetzt {status_str}!")
        else:
            await ctx.send("❌ Fehler beim Ändern der Sichtbarkeit!")

    @playlist.command(name='search')
    async def playlist_search(self, ctx, *, query: str):
        """Sucht nach öffentlichen Playlists"""
        playlists = await self.search_public_playlists(ctx.guild.id, query)
        if not playlists:
            return await ctx.send("❌ Keine öffentlichen Playlists gefunden, die deiner Suchanfrage entsprechen.")
        
        embed = discord.Embed(
            title="🔍 Suchergebnisse für öffentliche Playlists",
            color=discord.Color.blue()
        )
        
        for i, pl in enumerate(playlists[:10], 1):
            owner = ctx.guild.get_member(pl['user_id'])
            owner_name = owner.display_name if owner else f"User ID: {pl['user_id']}"
            desc = pl['description'] or "Keine Beschreibung"
            embed.add_field(
                name=f"{i}. {pl['name']} (von {owner_name})",
                value=f"{pl['song_count']} Songs | {pl['play_count']} Plays\n*{desc}*",
                inline=False
            )
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='favorite', aliases=['fav'])
    @is_user_check()
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
    
    @commands.hybrid_command(name='favorites', aliases=['favs'])
    @is_user_check()
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
