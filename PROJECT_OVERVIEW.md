# Project Overview: Discord Music Bot

## 📝 Project Overview & Purpose
This is a feature-rich, self-hosted Discord bot that handles music streaming (from YouTube, YouTube Music, Spotify, and Deezer), internet radio streams, user activity statistics tracking (messages, voice session durations, joins, etc.), and optional account linking (`!connect`) via an OAuth2 web server flow. It persists stats in SQLite or MariaDB (MySQL-compatible) databases.

## 🛠 Tech Stack
- **Language**: Python 3
- **Framework**: `discord.py` (v2.x)
- **APIs & Libraries**:
  - `yt-dlp` / `PyNaCl` (Music playback/streaming)
  - `psutil` (System resources monitoring)
  - `python-dotenv` (Configuration loading)
  - `aiomysql` (Async MySQL connection)
  - `aiohttp` (Async HTTP client/webserver)
- **Database**: SQLite or MariaDB/MySQL
- **Containerization**: Docker & Docker Compose

## 📂 Folder Structure & Key Files
- `bot.py`: The main entry point of the Discord Bot. Loads configurations from `.env` and initializes cogs.
- `Dockerfile` & `docker-compose.yml`: Docker configuration files for running the bot and MariaDB.
- `.env` & `.env.example`: Configuration and environment variables files.
- `requirements.txt`: Python package dependencies.
- `cogs/`:
  - `music_advanced.py`: Advanced music streaming, queue management, loop, and radio player commands.
  - `stats.py`: Statistics tracking commands and rendering personal/server stats.
  - `statistics_advanced.py`: Advanced music statistics (listening habits).
  - `playlists.py`: User custom playlists & favorites management.
  - `account.py`: Commands for `!connect` / `!disconnect` (linking Discord account to stats database via OAuth2).
  - `settings.py`: Guild-specific settings (e.g. announcement channel and toggles).
  - `info.py`: Help commands, bot status/ping, and invite links.
- `utils/`:
  - `database.py`: Database connection abstraction layer (SQLite & MySQL).
  - `db_operations.py`: Implementation of SQL operations for statistics tracking.
  - `music_utils.py`: Utilities for music queue and streaming (e.g., YTDLSource).
  - `track_resolver.py`: API resolver for Spotify/Deezer to YouTube search.
  - `oauth_server.py`: Internally run webserver handling Discord OAuth2 redirection callbacks.
- `tests/`: Unittest suite verifying various security features (SSRF, CSRF, Replays, Permissions).

## 🚀 Main Entry Points & Core Logic
1. **Startup**: Run `python bot.py` to start the bot. It loads environmental settings, connects to the database (with fallback logic), initializes the OAuth2 server if required, loads cogs, and synchronizes slash commands with Discord.
2. **Music Flow**: Music requests go through `cogs/music_advanced.py` using `utils/music_utils.py` and `utils/track_resolver.py` to fetch audio streams from YouTube/YTDL.
3. **Stats Logging**: User events (message sent, voice channel join/leave) are logged to the database via `cogs/stats.py` using functions in `utils/db_operations.py`.
