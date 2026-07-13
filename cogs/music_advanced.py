import discord
from discord.ext import commands, tasks
import asyncio
import logging
from typing import Optional
from datetime import datetime, timedelta
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.music_utils import YTDLSource, AdvancedMusicQueue, GuildMusicState, InteractiveView, MusicControlView, ytdl, ffmpeg_options, resolve_stream_url
from utils.database import Database
from utils.db_operations import DatabaseOperations
from utils import track_resolver

logger = logging.getLogger('discord_bot.music_advanced')

class MusicAdvanced(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_states = {}
        self.db = None
        self.check_empty_channels.start()
        
    async def cog_load(self):
        """Retrieve the shared database instance from the bot"""
        self.db = self.bot.db
    
    def cog_unload(self):
        """Clean up when cog unloads"""
        self.check_empty_channels.cancel()
        for state in self.guild_states.values():
            for task in state.empty_timers.values():
                task.cancel()
    
    def get_guild_state(self, guild_id) -> GuildMusicState:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = GuildMusicState(guild_id)
        return self.guild_states[guild_id]

    def _get_radio_streams(self):
        return self.bot.config.get('music', {}).get('radio_streams', [])

    def _find_stream(self, name: str):
        for stream in self._get_radio_streams():
            if stream['name'].lower() == name.lower():
                return stream
        return None

    def _get_default_stream(self):
        url = self.bot.config.get('music', {}).get('default_stream_url')
        for stream in self._get_radio_streams():
            if stream['url'] == url:
                return stream
        return {'name': 'default', 'title': 'Radio-Stream', 'url': url}

    def _make_stream_song(self, stream: dict, requester):
        return {
            'url': stream['url'],
            'title': stream['title'],
            'duration': None,
            'requester': requester,
            'is_stream': True
        }

    def _format_elapsed(self, song: dict) -> str:
        """Formatiert die seit Wiedergabestart vergangene Zeit (funktioniert auch für Radiosender
        ohne bekannte Gesamtdauer, da start_time bei jedem Songstart in play_next() gesetzt wird)"""
        start_time = song.get('start_time')
        if not start_time:
            return ''
        elapsed = int((datetime.utcnow() - start_time).total_seconds())
        return f"{elapsed // 60}:{elapsed % 60:02d}"

    async def _update_now_playing(self, guild, title):
        """Setzt die Bot-Activity und postet - falls aktiviert - eine Songwechsel-Ankündigung.
        Hinweis: Discord erlaubt Bots nur eine globale Presence, bei gleichzeitiger Wiedergabe
        auf mehreren Servern zeigt sie daher immer nur den zuletzt gestarteten Song."""
        try:
            await self.bot.change_presence(
                activity=discord.Activity(type=discord.ActivityType.listening, name=title)
            )
        except Exception:
            logger.exception("Presence-Update fehlgeschlagen")

        try:
            guild_settings = await DatabaseOperations.get_guild_settings(self.db, guild.id)
            enabled = guild_settings.get('announce_enabled')
            if enabled is None:
                enabled = self.bot.config.get('notifications', {}).get('song_change_default_enabled', True)
            channel_id = guild_settings.get('announce_channel_id')
            if enabled and channel_id:
                channel = guild.get_channel(channel_id)
                if channel:
                    embed = discord.Embed(
                        title="🎵 Jetzt läuft",
                        description=f"**{title}**",
                        color=discord.Color.blue()
                    )
                    await channel.send(embed=embed)
        except Exception:
            logger.exception("Songwechsel-Ankündigung fehlgeschlagen")
    
    @tasks.loop(minutes=1)
    async def check_empty_channels(self):
        """Check for empty voice channels and start disconnect timers"""
        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                if self.bot.user in [m for m in vc.members]:
                    # Bot is in this channel
                    if len(vc.members) == 1:  # Only bot
                        state = self.get_guild_state(guild.id)
                        if vc.id not in state.empty_timers:
                            # Start timer
                            timeout = self.bot.config['music'].get('empty_channel_timeout', 300)
                            state.empty_timers[vc.id] = asyncio.create_task(
                                self._disconnect_after_timeout(guild.id, vc.id, timeout)
                            )
                    else:
                        # Channel has other members, cancel timer if exists
                        state = self.get_guild_state(guild.id)
                        if vc.id in state.empty_timers:
                            state.empty_timers[vc.id].cancel()
                            del state.empty_timers[vc.id]
    
    async def _disconnect_after_timeout(self, guild_id, channel_id, timeout):
        """Disconnect from channel after timeout"""
        await asyncio.sleep(timeout)
        guild = self.bot.get_guild(guild_id)
        if guild:
            vc = guild.get_channel(channel_id)
            if vc and vc.guild.voice_client and vc.guild.voice_client.channel.id == channel_id:
                await vc.guild.voice_client.disconnect()
                state = self.get_guild_state(guild_id)
                state.cleanup_channel(channel_id)
    
    @check_empty_channels.before_loop
    async def before_check_empty_channels(self):
        await self.bot.wait_until_ready()
    
    async def track_song_play(self, guild_id, user_id, song_title, song_url, duration, skipped=False):
        """Track song play in database"""
        try:
            if self.db.db_type == 'sqlite':
                await self.db.connection.execute(
                    """
                    INSERT INTO song_history (guild_id, user_id, song_title, song_url, song_duration, skipped)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (guild_id, user_id, song_title, song_url, duration, skipped)
                )
                await self.db.connection.commit()
            else:
                async with self.db.pool.acquire() as conn:
                    async with conn.cursor() as cursor:
                        await cursor.execute(
                            """
                            INSERT INTO song_history (guild_id, user_id, song_title, song_url, song_duration, skipped)
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """,
                            (guild_id, user_id, song_title, song_url, duration, skipped)
                        )
        except Exception as e:
            logger.error(f"Error tracking song play: {e}")
    
    async def get_voice_client_for_user(self, ctx):
        """Get or create voice client for user's channel.
        Discord erlaubt einem einzelnen Bot-Konto pro Server (Guild) nur eine einzige aktive
        Sprachverbindung gleichzeitig - das ist eine Plattform-Grenze, kein Detail dieses Bots.
        Ist der Bot bereits in einem anderen Kanal desselben Servers, wird das hier klar
        zurückgemeldet statt zu versuchen, eine zweite (unmögliche) Verbindung aufzubauen."""
        if not ctx.author.voice:
            await ctx.send("❌ Du musst in einem Sprachkanal sein!")
            return None

        user_channel = ctx.author.voice.channel
        state = self.get_guild_state(ctx.guild.id)

        if ctx.voice_client:
            if ctx.voice_client.channel != user_channel:
                await ctx.send(
                    f"❌ Ich bin gerade schon in **{ctx.voice_client.channel.name}** aktiv. "
                    "Ein Bot-Konto kann pro Server nur in einem Sprachkanal gleichzeitig sein "
                    "(Grenze von Discord selbst) - tritt dem Kanal bei oder warte, bis ich dort fertig bin."
                )
                return None
            return ctx.voice_client

        vc = await user_channel.connect()
        state.voice_clients[user_channel.id] = vc
        return vc
    
    async def play_next(self, ctx, voice_channel_id):
        """Play the next song in the queue for a specific channel"""
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(voice_channel_id)
        
        if voice_channel_id not in state.voice_clients:
            return
        
        vc = state.voice_clients[voice_channel_id]
        
        if vc and vc.is_connected():
            next_song = queue.get_next()
            if next_song:
                next_song['start_time'] = datetime.utcnow()
                try:
                    if next_song.get('is_stream'):
                        stream_url = await resolve_stream_url(next_song['url'])
                        source = discord.PCMVolumeTransformer(
                            discord.FFmpegPCMAudio(stream_url, **ffmpeg_options),
                            volume=state.volume
                        )
                        vc.play(
                            source,
                            after=lambda e: asyncio.run_coroutine_threadsafe(
                                self.play_next(ctx, voice_channel_id),
                                self.bot.loop
                            )
                        )

                        embed = discord.Embed(
                            title="📻 Jetzt spielt",
                            description=f"**{next_song['title']}**",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="Angefordert von", value=next_song['requester'].mention)

                        view = MusicControlView(self, ctx)
                        msg = await ctx.send(embed=embed, view=view)
                        state.now_playing_messages[voice_channel_id] = msg

                        await self._update_now_playing(ctx.guild, next_song['title'])
                        return

                    # Track song play
                    await self.track_song_play(
                        ctx.guild.id,
                        next_song['requester'].id,
                        next_song['title'],
                        next_song['url'],
                        next_song.get('duration', 0)
                    )

                    player = await YTDLSource.from_url(
                        next_song['url'],
                        loop=self.bot.loop,
                        stream=True,
                        requester=next_song['requester']
                    )

                    vc.play(
                        player,
                        after=lambda e: asyncio.run_coroutine_threadsafe(
                            self.play_next(ctx, voice_channel_id),
                            self.bot.loop
                        )
                    )

                    # Create now playing embed with controls
                    embed = discord.Embed(
                        title="🎵 Jetzt spielt",
                        description=f"[{player.title}]({next_song['url']})",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Angefordert von", value=next_song['requester'].mention)
                    if player.duration:
                        embed.add_field(name="Dauer", value=f"{player.duration // 60}:{player.duration % 60:02d}")
                    embed.add_field(name="Warteschlange", value=f"{len(queue.queue)} Songs")
                    if player.thumbnail:
                        embed.set_thumbnail(url=player.thumbnail)

                    # Send with music controls
                    view = MusicControlView(self, ctx)
                    msg = await ctx.send(embed=embed, view=view)
                    state.now_playing_messages[voice_channel_id] = msg

                    await self._update_now_playing(ctx.guild, player.title)

                except Exception as e:
                    logger.error(f"Error playing song: {e}")
                    await ctx.send(f"❌ Fehler beim Abspielen: {e}")
                    await self.play_next(ctx, voice_channel_id)
            else:
                # No more songs, wait before disconnecting
                timeout = self.bot.config['music'].get('timeout', 300)
                await asyncio.sleep(timeout)
                if vc and not vc.is_playing() and len(queue.queue) == 0:
                    await vc.disconnect()
                    state.cleanup_channel(voice_channel_id)
    
    @commands.hybrid_command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str = None):
        """Spielt einen Song/Link (YouTube, Spotify, Deezer) oder ohne Angabe den Standard-Radiostream"""
        vc = await self.get_voice_client_for_user(ctx)
        if not vc:
            return

        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(vc.channel.id)

        if query is None:
            stream = self._get_default_stream()
            if not stream.get('url'):
                return await ctx.send("❌ Kein Standard-Stream konfiguriert und keine Suchanfrage angegeben!")
            queue.add(self._make_stream_song(stream, ctx.author))
            await ctx.send(f"📻 **{stream['title']}** zur Warteschlange hinzugefügt!")
            if not vc.is_playing() and not vc.is_paused():
                await self.play_next(ctx, vc.channel.id)
            return

        async with ctx.typing():
            try:
                # Spotify-/Deezer-Links vorab in YouTube-Suchqueries auflösen
                resolved_queries = await track_resolver.resolve(self.bot.config, query)
                if resolved_queries is not None:
                    if not resolved_queries:
                        return await ctx.send("❌ Konnte keine Songs zu diesem Link finden.")

                    added = 0
                    last_title = None
                    for resolved_query in resolved_queries:
                        try:
                            entry_data = await self.bot.loop.run_in_executor(
                                None, lambda q=resolved_query: ytdl.extract_info(q, download=False)
                            )
                            entry = entry_data['entries'][0] if 'entries' in entry_data else entry_data
                            if not entry:
                                continue
                            song_data = {
                                'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                'title': entry.get('title', 'Unknown'),
                                'duration': entry.get('duration'),
                                'requester': ctx.author
                            }
                            queue.add(song_data)
                            added += 1
                            last_title = song_data['title']
                        except Exception:
                            logger.exception(f"Fehler beim Auflösen von {resolved_query}")

                    if added == 0:
                        await ctx.send("❌ Konnte keine Songs zu diesem Link finden.")
                        return
                    elif added == 1:
                        await ctx.send(f"✅ **{last_title}** zur Warteschlange hinzugefügt!")
                    else:
                        await ctx.send(f"✅ {added} Songs zur Warteschlange hinzugefügt!")

                    if not vc.is_playing() and not vc.is_paused():
                        await self.play_next(ctx, vc.channel.id)
                    return

                # Extract info
                data = await self.bot.loop.run_in_executor(
                    None, lambda: ytdl.extract_info(query, download=False)
                )

                if 'entries' in data:
                    # It's a playlist
                    entries = data['entries']
                    
                    # Ask user for selection
                    embed = discord.Embed(
                        title="📃 Playlist erkannt!",
                        description=f"Playlist: **{data.get('title', 'Unknown')}**\nAnzahl Songs: **{len(entries)}**",
                        color=discord.Color.blue()
                    )
                    embed.add_field(
                        name="Was möchtest du tun?",
                        value="Wähle eine Option:",
                        inline=False
                    )
                    
                    view = InteractiveView(ctx)
                    msg = await ctx.send(embed=embed, view=view)
                    
                    await view.wait()
                    
                    if view.value == 'cancel':
                        await msg.edit(content="❌ Abgebrochen!", embed=None, view=None)
                        return
                    elif view.value == 'single':
                        # Add only first song
                        if entries and entries[0]:
                            entry = entries[0]
                            song_data = {
                                'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                'title': entry.get('title', 'Unknown'),
                                'duration': entry.get('duration'),
                                'requester': ctx.author
                            }
                            queue.add(song_data)
                            await msg.edit(
                                content=f"✅ **{song_data['title']}** zur Warteschlange hinzugefügt!",
                                embed=None, view=None
                            )
                    else:  # playlist
                        # Add all songs
                        await msg.edit(
                            content=f"📝 Füge {len(entries)} Songs zur Warteschlange hinzu...",
                            embed=None, view=None
                        )
                        
                        added = 0
                        for entry in entries:
                            if entry:
                                song_data = {
                                    'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                    'title': entry.get('title', 'Unknown'),
                                    'duration': entry.get('duration'),
                                    'requester': ctx.author
                                }
                                queue.add(song_data)
                                added += 1
                        
                        await msg.edit(content=f"✅ {added} Songs zur Warteschlange hinzugefügt!")
                else:
                    # Single song
                    song_data = {
                        'url': data.get('webpage_url', query),
                        'title': data.get('title', 'Unknown'),
                        'duration': data.get('duration'),
                        'requester': ctx.author
                    }
                    queue.add(song_data)
                    await ctx.send(f"✅ **{song_data['title']}** zur Warteschlange hinzugefügt!")
                
                # Start playing if nothing is playing
                if not vc.is_playing() and not vc.is_paused():
                    await self.play_next(ctx, vc.channel.id)
                    
            except Exception as e:
                logger.error(f"Error processing play command: {e}")
                await ctx.send(f"❌ Fehler: {str(e)}")

    @commands.hybrid_group(name='radio', invoke_without_command=True)
    async def radio(self, ctx):
        """Zeigt die verfügbaren Internet-Radiosender (siehe auch `!radio play <name>`)"""
        await ctx.invoke(self.radio_list)

    @radio.command(name='list')
    async def radio_list(self, ctx):
        """Zeigt alle konfigurierten Radiosender"""
        streams = self._get_radio_streams()

        embed = discord.Embed(title="📻 Verfügbare Radiosender", color=discord.Color.blue())
        if streams:
            text = "\n".join(f"**{s['name']}** – {s['title']}" for s in streams)
            embed.add_field(name="Sender", value=text, inline=False)
        else:
            embed.add_field(name="Sender", value="Keine Sender konfiguriert.", inline=False)

        embed.add_field(
            name="Verwendung",
            value="`!play` ohne Angabe – spielt den Standard-Stream\n"
                  "`!radio play <name>` – spielt einen bestimmten Sender",
            inline=False
        )
        await ctx.send(embed=embed)

    @radio.command(name='play')
    async def radio_play(self, ctx, name: str):
        """Spielt einen konfigurierten Radiosender"""
        stream = self._find_stream(name)
        if not stream:
            return await ctx.send(f"❌ Unbekannter Sender `{name}`. Nutze `!radio list` für eine Übersicht.")

        vc = await self.get_voice_client_for_user(ctx)
        if not vc:
            return

        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(vc.channel.id)
        queue.add(self._make_stream_song(stream, ctx.author))
        await ctx.send(f"📻 **{stream['title']}** zur Warteschlange hinzugefügt!")

        if not vc.is_playing() and not vc.is_paused():
            await self.play_next(ctx, vc.channel.id)

    @commands.hybrid_command(name='queue', aliases=['q', 'list'])
    async def queue_command(self, ctx, page: int = 1):
        """Zeigt die aktuelle Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)

        if not queue.current and len(queue.queue) == 0:
            return await ctx.send("📭 Es läuft nichts und die Warteschlange ist leer!")

        items_per_page = 10
        pages = max(1, (len(queue.queue) - 1) // items_per_page + 1)
        
        if page < 1 or page > pages:
            page = 1
        
        start = (page - 1) * items_per_page
        end = start + items_per_page
        
        embed = discord.Embed(
            title=f"🎵 Musik-Warteschlange (Seite {page}/{pages})",
            color=discord.Color.blue()
        )
        
        # Current song
        if queue.current:
            elapsed = self._format_elapsed(queue.current)
            elapsed_text = f"\n⏱️ Läuft seit {elapsed}" if elapsed else ""
            embed.add_field(
                name="🎵 Aktuell",
                value=f"**{queue.current['title'][:50]}**\n{queue.current['requester'].mention}{elapsed_text}",
                inline=False
            )
        
        # Queue
        queue_list = queue.to_list()[start:end]
        if queue_list:
            queue_text = ""
            for i, song in enumerate(queue_list, start=start+1):
                queue_text += f"**{i}.** {song['title'][:50]}\n"
                queue_text += f"   ↳ {song['requester'].mention}\n"
            
            embed.add_field(
                name="📃 Warteschlange",
                value=queue_text[:1024],
                inline=False
            )
        
        # Footer info
        total_duration = sum(s.get('duration', 0) for s in queue.queue if s.get('duration'))
        embed.set_footer(
            text=f"Gesamt: {len(queue.queue)} Songs | "
                 f"Dauer: {total_duration // 60}:{total_duration % 60:02d} | "
                 f"Loop: {'🔁' if queue.loop else '❌'} | "
                 f"Loop Queue: {'🔁' if queue.loop_queue else '❌'}"
        )
        
        await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='remove', aliases=['rm'])
    async def remove(self, ctx, position: int):
        """Entfernt einen Song aus der Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        removed = queue.remove(position - 1)
        if removed:
            await ctx.send(f"✅ **{removed['title']}** aus der Warteschlange entfernt!")
        else:
            await ctx.send("❌ Ungültige Position!")
    
    @commands.hybrid_command(name='clear')
    async def clear(self, ctx):
        """Leert die gesamte Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        queue.clear()
        await ctx.send("🗑️ Warteschlange geleert!")
    
    @commands.hybrid_command(name='move')
    async def move(self, ctx, from_pos: int, to_pos: int):
        """Verschiebt einen Song in der Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        if queue.move(from_pos - 1, to_pos - 1):
            await ctx.send(f"✅ Song von Position {from_pos} nach {to_pos} verschoben!")
        else:
            await ctx.send("❌ Ungültige Positionen!")
    
    @commands.hybrid_command(name='shuffle')
    async def shuffle(self, ctx):
        """Mischt die Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        queue.shuffle()
        await ctx.send("🔀 Warteschlange gemischt!")
    
    @commands.hybrid_command(name='loop')
    async def loop(self, ctx, mode: str = None):
        """Aktiviert/Deaktiviert Loop-Modus (song/queue/off)"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        if mode == 'song':
            queue.loop = True
            queue.loop_queue = False
            await ctx.send("🔂 Song-Loop aktiviert!")
        elif mode == 'queue':
            queue.loop = False
            queue.loop_queue = True
            await ctx.send("🔁 Queue-Loop aktiviert!")
        elif mode == 'off':
            queue.loop = False
            queue.loop_queue = False
            await ctx.send("➡️ Loop deaktiviert!")
        else:
            status = "Song-Loop" if queue.loop else "Queue-Loop" if queue.loop_queue else "Aus"
            await ctx.send(f"🔁 Loop-Status: **{status}**\nNutze `!loop song/queue/off`")
    
    @commands.hybrid_command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        """Zeigt den aktuell spielenden Song"""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ Es läuft gerade keine Musik!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        if queue.current:
            embed = discord.Embed(
                title="🎵 Aktuell spielt",
                description=f"**{queue.current['title']}**",
                color=discord.Color.blue()
            )
            embed.add_field(name="Angefordert von", value=queue.current['requester'].mention)

            # Progress bar (nur wenn Gesamtdauer bekannt ist - Radiosender haben keine)
            start_time = queue.current.get('start_time')
            if start_time:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                duration = queue.current.get('duration', 0)
                elapsed_str = f"{int(elapsed) // 60}:{int(elapsed) % 60:02d}"
                if duration and duration > 0:
                    progress = int((elapsed / duration) * 20)
                    bar = '█' * progress + '░' * (20 - progress)
                    duration_str = f"{duration // 60}:{duration % 60:02d}"
                    embed.add_field(
                        name="Fortschritt",
                        value=f"`{bar}`\n{elapsed_str} / {duration_str}",
                        inline=False
                    )
                else:
                    embed.add_field(name="⏱️ Läuft seit", value=elapsed_str, inline=False)

            await ctx.send(embed=embed)
    
    @commands.hybrid_command(name='skip', aliases=['next'])
    async def skip(self, ctx):
        """Überspringt den aktuellen Song"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            # Track as skipped
            state = self.get_guild_state(ctx.guild.id)
            queue = state.get_queue(ctx.voice_client.channel.id)
            if queue.current:
                await self.track_song_play(
                    ctx.guild.id,
                    queue.current['requester'].id,
                    queue.current['title'],
                    queue.current['url'],
                    queue.current.get('duration', 0),
                    skipped=True
                )
            
            ctx.voice_client.stop()
            await ctx.send("⏭️ Song übersprungen!")
        else:
            await ctx.send("❌ Es läuft gerade keine Musik!")
    
    @commands.hybrid_command(name='previous', aliases=['prev'])
    async def previous(self, ctx):
        """Spielt den vorherigen Song"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        state = self.get_guild_state(ctx.guild.id)
        queue = state.get_queue(ctx.voice_client.channel.id)
        
        previous_song = queue.get_previous()
        if previous_song:
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            await ctx.send(f"⏮️ Spiele vorherigen Song: **{previous_song['title']}**")
            # Will be played by play_next
        else:
            await ctx.send("❌ Kein vorheriger Song verfügbar!")
    
    @commands.hybrid_command(name='stop')
    async def stop(self, ctx):
        """Stoppt die Musik und leert die Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")

        state = self.get_guild_state(ctx.guild.id)
        # channel_id vorher sichern: ctx.voice_client ist eine "live" Property (liest bei jedem
        # Zugriff guild.voice_client neu) und wird nach disconnect() bereits None
        channel_id = ctx.voice_client.channel.id
        queue = state.get_queue(channel_id)
        queue.clear()

        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()

        # Clean up state
        if channel_id in state.voice_clients:
            del state.voice_clients[channel_id]
        state.cleanup_channel(channel_id)
        
        await ctx.send("⏹️ Musik gestoppt und Warteschlange geleert!")
    
    @commands.hybrid_command(name='pause')
    async def pause(self, ctx):
        """Pausiert die aktuelle Wiedergabe"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Wiedergabe pausiert!")
        else:
            await ctx.send("❌ Es läuft gerade keine Musik!")
    
    @commands.hybrid_command(name='resume')
    async def resume(self, ctx):
        """Setzt die pausierte Wiedergabe fort"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Wiedergabe fortgesetzt!")
        else:
            await ctx.send("❌ Die Wiedergabe ist nicht pausiert!")
    
    @commands.hybrid_command(name='volume', aliases=['vol'])
    async def volume(self, ctx, volume: int = None):
        """Ändert die Lautstärke (0-100)"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        if volume is None:
            if hasattr(ctx.voice_client.source, 'volume'):
                return await ctx.send(f"🔊 Aktuelle Lautstärke: {int(ctx.voice_client.source.volume * 100)}%")
            return await ctx.send("🔊 Aktuelle Lautstärke: 50%")
        
        if not 0 <= volume <= 100:
            return await ctx.send("❌ Lautstärke muss zwischen 0 und 100 liegen!")
        
        if hasattr(ctx.voice_client.source, 'volume'):
            ctx.voice_client.source.volume = volume / 100
        
        state = self.get_guild_state(ctx.guild.id)
        state.volume = volume / 100
        
        await ctx.send(f"🔊 Lautstärke auf {volume}% gesetzt!")

async def setup(bot):
    # Remove old music cog if exists
    if 'Music' in bot.cogs:
        await bot.remove_cog('Music')
    
    await bot.add_cog(MusicAdvanced(bot))
