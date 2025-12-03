import discord
from discord.ext import commands
import yt_dlp
import asyncio
import logging
from typing import Optional
import re

logger = logging.getLogger('discord_bot.music')

# YouTube DL options
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': True
}

ffmpeg_options = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

ytdl = yt_dlp.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = data.get('requester')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False, requester=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))
        
        if 'entries' in data:
            # Take first item from a playlist
            data = data['entries'][0]
        
        filename = data['url'] if stream else ytdl.prepare_filename(data)
        data['requester'] = requester
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)

class MusicQueue:
    def __init__(self):
        self.queue = []
        self.current = None
        self.loop = False
        self.loop_queue = False
        
    def add(self, song):
        self.queue.append(song)
    
    def get_next(self):
        if self.loop and self.current:
            return self.current
        elif self.loop_queue and self.current:
            self.queue.append(self.current)
        
        if len(self.queue) > 0:
            self.current = self.queue.pop(0)
            return self.current
        return None
    
    def clear(self):
        self.queue = []
        self.current = None
    
    def shuffle(self):
        import random
        random.shuffle(self.queue)

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queues = {}
        
    def get_queue(self, guild_id):
        if guild_id not in self.music_queues:
            self.music_queues[guild_id] = MusicQueue()
        return self.music_queues[guild_id]
    
    async def play_next(self, ctx):
        """Play the next song in the queue"""
        queue = self.get_queue(ctx.guild.id)
        
        if ctx.voice_client and ctx.voice_client.is_connected():
            next_song = queue.get_next()
            if next_song:
                try:
                    player = await YTDLSource.from_url(next_song['url'], loop=self.bot.loop, stream=True, requester=next_song['requester'])
                    ctx.voice_client.play(player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop))
                    
                    embed = discord.Embed(
                        title="🎵 Jetzt spielt",
                        description=f"[{player.title}]({next_song['url']})",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="Angefordert von", value=next_song['requester'].mention)
                    if player.duration:
                        embed.add_field(name="Dauer", value=f"{player.duration // 60}:{player.duration % 60:02d}")
                    if player.thumbnail:
                        embed.set_thumbnail(url=player.thumbnail)
                    
                    await ctx.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error playing song: {e}")
                    await ctx.send(f"❌ Fehler beim Abspielen: {e}")
                    await self.play_next(ctx)
            else:
                # No more songs, leave after timeout
                await asyncio.sleep(300)  # 5 minutes timeout
                if ctx.voice_client and not ctx.voice_client.is_playing():
                    await ctx.voice_client.disconnect()
    
    def parse_url(self, query):
        """Parse and validate music URLs"""
        # YouTube patterns
        youtube_regex = r'(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)/.+'
        # Spotify pattern (note: requires additional handling)
        spotify_regex = r'(https?://)?(open\.)?spotify\.com/(track|playlist|album)/.+'
        # Deezer pattern (note: requires additional handling)  
        deezer_regex = r'(https?://)?(www\.)?deezer\.com/.+'
        
        if re.match(youtube_regex, query):
            return query, 'youtube'
        elif re.match(spotify_regex, query):
            return query, 'spotify'
        elif re.match(deezer_regex, query):
            return query, 'deezer'
        else:
            # Treat as search query for YouTube
            return f"ytsearch:{query}", 'search'
    
    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Spielt einen Song oder fügt ihn zur Warteschlange hinzu"""
        
        # Check if user is in voice channel
        if not ctx.author.voice:
            return await ctx.send("❌ Du musst in einem Sprachkanal sein!")
        
        # Join voice channel if not already connected
        if not ctx.voice_client:
            channel = ctx.author.voice.channel
            await channel.connect()
        elif ctx.voice_client.channel != ctx.author.voice.channel:
            return await ctx.send("❌ Ich bin bereits in einem anderen Sprachkanal!")
        
        url, source_type = self.parse_url(query)
        
        # Note: Spotify and Deezer require additional API setup
        if source_type in ['spotify', 'deezer']:
            await ctx.send(f"⚠️ {source_type.capitalize()} wird noch nicht vollständig unterstützt. Verwende YouTube/YouTube Music Links.")
            return
        
        async with ctx.typing():
            try:
                # Extract info without downloading
                data = await self.bot.loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
                
                if 'entries' in data:
                    # It's a playlist
                    entries = data['entries']
                    await ctx.send(f"📝 Füge {len(entries)} Songs zur Warteschlange hinzu...")
                    
                    for entry in entries:
                        if entry:
                            song_data = {
                                'url': f"https://www.youtube.com/watch?v={entry['id']}",
                                'title': entry.get('title', 'Unknown'),
                                'requester': ctx.author
                            }
                            self.get_queue(ctx.guild.id).add(song_data)
                else:
                    # Single song
                    song_data = {
                        'url': data.get('webpage_url', url),
                        'title': data.get('title', 'Unknown'),
                        'requester': ctx.author
                    }
                    self.get_queue(ctx.guild.id).add(song_data)
                    await ctx.send(f"✅ **{song_data['title']}** zur Warteschlange hinzugefügt!")
                
                # Start playing if nothing is playing
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                    
            except Exception as e:
                logger.error(f"Error processing play command: {e}")
                await ctx.send(f"❌ Fehler: {str(e)}")
    
    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stoppt die Musik und leert die Warteschlange"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        self.get_queue(ctx.guild.id).clear()
        ctx.voice_client.stop()
        await ctx.voice_client.disconnect()
        await ctx.send("⏹️ Musik gestoppt und Warteschlange geleert!")
    
    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pausiert die aktuelle Wiedergabe"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Wiedergabe pausiert!")
        else:
            await ctx.send("❌ Es läuft gerade keine Musik!")
    
    @commands.command(name='resume')
    async def resume(self, ctx):
        """Setzt die pausierte Wiedergabe fort"""
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Wiedergabe fortgesetzt!")
        else:
            await ctx.send("❌ Die Wiedergabe ist nicht pausiert!")
    
    @commands.command(name='skip', aliases=['next'])
    async def skip(self, ctx):
        """Überspringt den aktuellen Song"""
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ Song übersprungen!")
        else:
            await ctx.send("❌ Es läuft gerade keine Musik!")
    
    @commands.command(name='previous', aliases=['prev'])
    async def previous(self, ctx):
        """Spielt den vorherigen Song (wenn verfügbar)"""
        await ctx.send("⏮️ Previous-Funktion wird in einer zukünftigen Version hinzugefügt!")
    
    @commands.command(name='queue', aliases=['q'])
    async def queue(self, ctx):
        """Zeigt die aktuelle Warteschlange"""
        queue = self.get_queue(ctx.guild.id)
        
        if len(queue.queue) == 0:
            return await ctx.send("📭 Die Warteschlange ist leer!")
        
        embed = discord.Embed(
            title="🎵 Musik-Warteschlange",
            color=discord.Color.blue()
        )
        
        for i, song in enumerate(queue.queue[:10], 1):
            embed.add_field(
                name=f"{i}. {song['title'][:50]}",
                value=f"Angefordert von {song['requester'].mention}",
                inline=False
            )
        
        if len(queue.queue) > 10:
            embed.set_footer(text=f"... und {len(queue.queue) - 10} weitere Songs")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='volume', aliases=['vol'])
    async def volume(self, ctx, volume: int = None):
        """Ändert die Lautstärke (0-100)"""
        if not ctx.voice_client:
            return await ctx.send("❌ Ich bin in keinem Sprachkanal!")
        
        if volume is None:
            return await ctx.send(f"🔊 Aktuelle Lautstärke: {int(ctx.voice_client.source.volume * 100)}%")
        
        if not 0 <= volume <= 100:
            return await ctx.send("❌ Lautstärke muss zwischen 0 und 100 liegen!")
        
        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"🔊 Lautstärke auf {volume}% gesetzt!")

async def setup(bot):
    await bot.add_cog(Music(bot))
