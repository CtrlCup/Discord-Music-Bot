import discord
import yt_dlp
import asyncio
import logging
from datetime import datetime
import random
from typing import Optional, Dict, List

logger = logging.getLogger('discord_bot.music_utils')

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
    'extract_flat': 'in_playlist'
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
        self.webpage_url = data.get('webpage_url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.requester = data.get('requester')
        self.start_time = datetime.utcnow()

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

class AdvancedMusicQueue:
    """Advanced queue management with history and loop support"""
    
    def __init__(self):
        self.queue = []
        self.history = []
        self.current = None
        self.loop = False
        self.loop_queue = False
        self.position = 0
        
    def add(self, song, position=None):
        """Add song at specific position or at the end"""
        if position is not None and 0 <= position <= len(self.queue):
            self.queue.insert(position, song)
        else:
            self.queue.append(song)
    
    def remove(self, index):
        """Remove song at specific index"""
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None
    
    def move(self, from_index, to_index):
        """Move song from one position to another"""
        if 0 <= from_index < len(self.queue) and 0 <= to_index <= len(self.queue):
            song = self.queue.pop(from_index)
            self.queue.insert(to_index, song)
            return True
        return False
    
    def get_next(self):
        """Get next song considering loop settings"""
        if self.current:
            self.history.append(self.current)
            # Keep history limited
            if len(self.history) > 50:
                self.history.pop(0)
        
        if self.loop and self.current:
            return self.current
        elif self.loop_queue and self.current:
            self.queue.append(self.current)
        
        if len(self.queue) > 0:
            self.current = self.queue.pop(0)
            return self.current
        return None
    
    def get_previous(self):
        """Get previous song from history"""
        if len(self.history) > 0:
            if self.current:
                self.queue.insert(0, self.current)
            self.current = self.history.pop()
            return self.current
        return None
    
    def clear(self):
        """Clear queue but keep history"""
        self.queue = []
        self.current = None
    
    def shuffle(self):
        """Shuffle the queue"""
        random.shuffle(self.queue)
    
    def to_list(self):
        """Get queue as list for display"""
        return self.queue.copy()

class GuildMusicState:
    """Manages music state for a specific guild"""
    
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.voice_clients = {}  # channel_id: voice_client
        self.queues = {}  # channel_id: AdvancedMusicQueue
        self.now_playing_messages = {}  # channel_id: message
        self.empty_timers = {}  # channel_id: asyncio.Task
        self.skip_votes = {}  # channel_id: set(user_ids)
        self.dj_role = None
        self.volume = 0.5
        
    def get_queue(self, channel_id):
        if channel_id not in self.queues:
            self.queues[channel_id] = AdvancedMusicQueue()
        return self.queues[channel_id]
    
    def cleanup_channel(self, channel_id):
        """Clean up resources for a specific channel"""
        if channel_id in self.queues:
            del self.queues[channel_id]
        if channel_id in self.now_playing_messages:
            del self.now_playing_messages[channel_id]
        if channel_id in self.skip_votes:
            del self.skip_votes[channel_id]
        if channel_id in self.empty_timers:
            self.empty_timers[channel_id].cancel()
            del self.empty_timers[channel_id]

class InteractiveView(discord.ui.View):
    """Interactive buttons for playlist selection"""
    
    def __init__(self, ctx, timeout=60):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.value = None
    
    @discord.ui.button(label='Nur dieser Song', style=discord.ButtonStyle.primary, emoji='🎵')
    async def single_song(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Nur der Anforderer kann diese Auswahl treffen!", ephemeral=True)
            return
        await interaction.response.defer()
        self.value = 'single'
        self.stop()
    
    @discord.ui.button(label='Ganze Playlist', style=discord.ButtonStyle.success, emoji='📃')
    async def whole_playlist(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Nur der Anforderer kann diese Auswahl treffen!", ephemeral=True)
            return
        await interaction.response.defer()
        self.value = 'playlist'
        self.stop()
    
    @discord.ui.button(label='Abbrechen', style=discord.ButtonStyle.danger, emoji='❌')
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Nur der Anforderer kann diese Auswahl treffen!", ephemeral=True)
            return
        await interaction.response.defer()
        self.value = 'cancel'
        self.stop()

class MusicControlView(discord.ui.View):
    """Music control buttons"""
    
    def __init__(self, cog, ctx):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx
    
    @discord.ui.button(emoji='⏮️', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # Call cog's previous method
        ctx_command = await self.cog.bot.get_context(interaction.message)
        await self.cog.previous(ctx_command)
    
    @discord.ui.button(emoji='⏸️', style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            button.emoji = '▶️'
        elif vc and vc.is_paused():
            vc.resume()
            button.emoji = '⏸️'
        await interaction.message.edit(view=self)
    
    @discord.ui.button(emoji='⏹️', style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx_command = await self.cog.bot.get_context(interaction.message)
        await self.cog.stop(ctx_command)
    
    @discord.ui.button(emoji='⏭️', style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx_command = await self.cog.bot.get_context(interaction.message)
        await self.cog.skip(ctx_command)
    
    @discord.ui.button(emoji='🔀', style=discord.ButtonStyle.secondary)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        ctx_command = await self.cog.bot.get_context(interaction.message)
        await self.cog.shuffle(ctx_command)
