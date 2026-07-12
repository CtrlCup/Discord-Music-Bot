# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Local run (requires a filled .env, see below)
pip install -r requirements.txt
python bot.py

# Docker Compose (recommended)
docker compose build
docker compose up -d                       # SQLite (default)
docker compose --profile mysql up -d       # also starts the bundled MySQL container
docker compose logs -f bot

# Unit tests (run inside the built image so all deps are guaranteed present)
docker run --rm --entrypoint python discord-music-bot-bot -m unittest discover -s tests -v
```

There is a lightweight `unittest` suite under `tests/` covering the security-critical pieces (SSRF guard in `track_resolver`, OAuth `state` CSRF/replay protection, `!settings` permission gates, the SQL behind extended stats) plus in-memory-SQLite integration tests for `db_operations.py`. No linter/CI configuration exists. Beyond the test suite, verify behavior changes by starting the bot and checking `bot.log` / `docker compose logs -f bot`, since discord.py errors mostly surface at runtime (cog load failures, command errors) rather than at import time.

### Configuration

Everything lives in **`.env`** (gitignored; `.env.example` is the template) — there is no `config.json`. `bot.py::load_config()` builds the whole runtime config dict straight from environment variables (secrets like `DISCORD_BOT_TOKEN`/`DISCORD_OAUTH_CLIENT_SECRET`/`SPOTIFY_CLIENT_SECRET`, DB connection settings, and non-secret tunables like `BOT_PREFIX`, `MUSIC_DEFAULT_STREAM_URL`, `RADIO_STREAMS` (a JSON array, see `.env.example`), `NOTIFICATIONS_SONG_CHANGE_DEFAULT_ENABLED`, `OAUTH_SCOPES`). Cogs still read this through the same nested `bot.config['music']['...']`/`bot.config['oauth']['...']` shape as before — only *how* the dict gets built changed, not its shape, so cog code didn't need to change when config.json was dropped. Only keys that are actually read somewhere in the code made it into `load_config()` — several `config.json` keys from the original template (`music.dj_role`, `vote_skip_percentage`, `features.premium.*`, `bot.owner`, ...) were never wired to real behavior and were intentionally not carried forward; check `load_config()` before assuming a setting exists.

`bot.py::_apply_env_overrides()` overlays `.env` values onto the parsed `config.json` dict at startup — env vars always win when set. Missing/invalid `config.json` still causes an immediate exit (`load_config()`).

## Architecture

**Cog loading is the source of truth for what's active.** `bot.py`'s `load_cogs()` hardcodes the list of cogs to load:

```python
cog_files = ['music_advanced', 'stats', 'statistics_advanced', 'playlists', 'info', 'account', 'settings']
```

`cogs/music.py` is a legacy/basic music implementation **not loaded** by the bot — `music_advanced.py` superseded it. `stats.py` (message/voice tracking, leaderboard) and `statistics_advanced.py` (music-listening stats) both load and coexist — they track different things, not duplicates. Don't assume a `cogs/*.py` file is live just because it exists; check the load list in `bot.py` first.

**Music playback** (`cogs/music_advanced.py` + `utils/music_utils.py` + `utils/track_resolver.py`):
- `GuildMusicState` (in `music_utils.py`) keys queues per-channel (`GuildMusicState.get_queue(channel_id)`), but a single bot connection can only ever be in **one voice channel per guild at a time** — this is a Discord platform limit (`VoiceChannel.connect()` raises `ClientException` if the guild already has an active voice connection elsewhere), not something this bot can work around. `get_voice_client_for_user()` in `music_advanced.py` checks `ctx.voice_client` first and returns a clear error if the bot is already active in a different channel of the same guild, rather than attempting (and crashing on) a second connection. Multiple *guilds* simultaneously each with their own voice channel works fine (`self.guild_states` is keyed per guild).
- `AdvancedMusicQueue` is the per-channel queue (supports move/remove/shuffle/loop).
- `YTDLSource` wraps yt-dlp + ffmpeg streaming for actual YouTube/YouTube Music playback; `ytdl` options control extraction.
- `utils/track_resolver.py` turns Spotify/Deezer track/album/playlist links into `ytsearchN:<artist> - <title>` queries *before* they reach yt-dlp — Spotify/Deezer are metadata-only (Client-Credentials / public REST API respectively), actual audio always comes from YouTube. `cogs/music_advanced.py::play()` calls `resolve()` first; a `None` return means "pass the query through unchanged" (plain YouTube URL/Music URL/text search).
- Internet radio: `!play` with no query, or `!radio play <name>`, adds a song dict with `is_stream=True` (see `_get_default_stream`/`_make_stream_song`/`_find_stream` in `music_advanced.py`). `play_next()` branches on `is_stream` to skip yt-dlp entirely and open the stream URL directly via `discord.FFmpegPCMAudio` (m3u/m3u8 links aren't yt-dlp extractors, but ffmpeg opens them natively). Streams have `duration=None` and no history entry.
- An empty-channel auto-disconnect loop (`check_empty_channels`, a `tasks.loop`, 2 min default via `music.empty_channel_timeout`) disconnects idle voice clients and clears that channel's queue (`state.cleanup_channel`).
- `_update_now_playing()` sets the bot's global Discord presence on every song start **and** posts a per-guild announcement embed if enabled (`guild_settings.announce_enabled`/`announce_channel_id`, managed via `cogs/settings.py`). Discord bots only have one *global* presence — with simultaneous playback across multiple guilds the Activity text reflects whichever song started most recently across all of them; the per-guild announce message is the reliable per-server source of truth.
- `InteractiveView` / `MusicControlView` are `discord.ui.View` button controls attached to now-playing/search messages.

**Database layer** (`utils/database.py` + `utils/db_operations.py`):
- `Database` abstracts SQLite (`aiosqlite`) vs MySQL (`aiomysql`) behind the same interface, auto-falling back to SQLite if MySQL is configured but unreachable or fails to init.
- Table schemas are defined **twice**, once per backend (`_create_tables_sqlite` / `_create_tables_mysql`) with different placeholder styles (`?` vs `%s`) and column types. `Database._migrate_existing_tables()` runs best-effort `ALTER TABLE ADD COLUMN` statements (ignoring "already exists" errors) so columns added after the initial release (e.g. `join_count`, `announce_channel_id`) reach already-existing local DB files too. When adding a column: extend both `CREATE TABLE` variants **and** add an `ALTER TABLE` line here.
- `db_operations.py` (`DatabaseOperations`) holds static helpers, always branching on `db.db_type` to pick the right SQL dialect. Prefer computing derived stats (main voice channel, average session length, voice co-presence overlap) from the existing `voice_sessions` rows at query time (see `get_main_channel`/`get_avg_session`/`get_top_companion`) rather than adding new denormalized/cached columns that need to be kept in sync.
- Cogs each define their own thin data-access methods against `self.bot.<db attribute>` (see `playlists.py`, `statistics_advanced.py`) rather than going through a shared repository layer — expect direct SQL in cogs, not just in `utils/`.

**OAuth2 account linking** (`utils/oauth_server.py` + `cogs/account.py`):
- `bot.py::setup_hook()` starts a small internal `aiohttp` web server (`start_oauth_server`, default port `8080`/`OAUTH_WEB_PORT`) handling `GET /oauth/callback`. It is not internet-facing on its own — the operator's existing reverse proxy forwards the public HTTPS redirect URI to this container/port.
- `!connect` (`cogs/account.py`) generates a random CSRF `state` stored in `bot.oauth_states` (in-memory, TTL-bound in `oauth_server.py`) mapped to the invoking user's ID, and DMs them the Discord authorize URL.
- The callback exchanges the code for tokens, then **re-verifies** via `GET /users/@me` that the account which actually completed the consent screen matches the user ID the `state` was issued for (prevents a forwarded/leaked link from linking someone else's tokens to the original caller's slot) before storing anything in `oauth_links`.
- `cogs/stats.py::_add_private_section()` is the only consumer: it is invoked **only when a user looks up their own `!stats`** (never for `target != None`), refreshes the access token via `refresh_access_token()` if expired, and shows fields not otherwise visible (exact account creation time, email, MFA status, locale, Nitro tier).
- `oauth_links` stores live access/refresh tokens — treat the DB (SQLite file or MySQL credentials) as sensitive accordingly.

**Cross-cutting**: cogs communicate mainly through the shared `Database` instance(s) attached to cogs at `cog_load()` (plus one dedicated `bot.oauth_db` for the account-linking feature, set up in `setup_hook()`), and through Discord's own event dispatch (`on_message`, `on_voice_state_update`, etc.) rather than direct cog-to-cog calls.
