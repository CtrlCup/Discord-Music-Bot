import re
import asyncio
import logging
import aiohttp
import spotipy
from urllib.parse import urlparse
from spotipy.oauth2 import SpotifyClientCredentials

logger = logging.getLogger('discord_bot.track_resolver')

SPOTIFY_RE = re.compile(r'open\.spotify\.com/(?:intl-\w+/)?(track|album|playlist)/([a-zA-Z0-9]+)')
DEEZER_RE = re.compile(r'deezer\.com/(?:\w+/)?(track|album|playlist)/(\d+)')
DEEZER_SHORTLINK_HOSTS = {'deezer.page.link', 'link.deezer.com'}

MAX_TRACKS = 50
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)


def _is_deezer_shortlink(query: str) -> bool:
    """Nur echte deezer.page.link-URLs folgen, nicht jede Eingabe, die den Substring enthält
    (verhindert SSRF über eine beliebige, vom Nutzer angegebene Ziel-URL)"""
    parsed = urlparse(query)
    return parsed.scheme in ('http', 'https') and parsed.netloc.lower() in DEEZER_SHORTLINK_HOSTS

_spotify_client = None


def _get_spotify_client(spotify_cfg: dict):
    """Lazily build a Spotify Client-Credentials client (server-to-server, no user login)"""
    global _spotify_client
    if _spotify_client is None:
        if not spotify_cfg.get('client_id') or not spotify_cfg.get('client_secret'):
            return None
        auth_manager = SpotifyClientCredentials(
            client_id=spotify_cfg['client_id'],
            client_secret=spotify_cfg['client_secret']
        )
        _spotify_client = spotipy.Spotify(auth_manager=auth_manager)
    return _spotify_client


def _spotify_query(track: dict) -> str:
    artists = ', '.join(a['name'] for a in track.get('artists', []))
    title = track.get('name', '')
    return f"ytsearch1:{artists} - {title}".strip()


def _deezer_query(track: dict) -> str:
    artist = track.get('artist', {}).get('name', '')
    title = track.get('title', '')
    return f"ytsearch1:{artist} - {title}".strip()


async def _resolve_deezer_shortlink(url: str) -> str:
    """Follow deezer.page.link redirects to get the canonical deezer.com URL"""
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url, allow_redirects=True) as resp:
                return str(resp.url)
    except Exception:
        logger.exception("Failed to resolve Deezer short link")
        return url


async def _resolve_spotify(spotify_cfg: dict, kind: str, item_id: str):
    sp = _get_spotify_client(spotify_cfg)
    if sp is None:
        logger.warning("Spotify-Link erkannt, aber kein SPOTIFY_CLIENT_ID/SECRET konfiguriert")
        return None

    loop = asyncio.get_event_loop()
    try:
        if kind == 'track':
            track = await loop.run_in_executor(None, sp.track, item_id)
            return [_spotify_query(track)]
        elif kind == 'album':
            results = await loop.run_in_executor(None, lambda: sp.album_tracks(item_id, limit=MAX_TRACKS))
            return [_spotify_query(t) for t in results['items']]
        else:  # playlist
            results = await loop.run_in_executor(None, lambda: sp.playlist_items(item_id, limit=MAX_TRACKS))
            tracks = [item['track'] for item in results['items'] if item.get('track')]
            return [_spotify_query(t) for t in tracks]
    except Exception:
        logger.exception("Spotify-Auflösung fehlgeschlagen")
        return None


async def _resolve_deezer(kind: str, item_id: str):
    url = f"https://api.deezer.com/{kind}/{item_id}"
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url) as resp:
                data = await resp.json()
    except Exception:
        logger.exception("Deezer-API-Anfrage fehlgeschlagen")
        return None

    if not data or data.get('error'):
        return None

    if kind == 'track':
        return [_deezer_query(data)]

    tracks = data.get('tracks', {}).get('data', [])[:MAX_TRACKS]
    return [_deezer_query(t) for t in tracks] if tracks else None


async def resolve(config: dict, query: str):
    """
    Löst Spotify-/Deezer-Links in eine Liste von 'ytsearchN:...'-Queries auf (Titel + Interpret,
    danach über yt-dlp wie eine normale Suche verarbeitet).
    Gibt None zurück, wenn die Eingabe unverändert an den bestehenden yt-dlp-Ablauf übergeben werden
    soll (YouTube/YouTube-Music-URL oder reine Textsuche).
    """
    if _is_deezer_shortlink(query):
        query = await _resolve_deezer_shortlink(query)

    spotify_match = SPOTIFY_RE.search(query)
    if spotify_match:
        kind, item_id = spotify_match.groups()
        spotify_cfg = config.get('spotify', {})
        if not spotify_cfg.get('client_id') or not spotify_cfg.get('client_secret'):
            raise ValueError("Spotify-Integration ist nicht konfiguriert (SPOTIFY_CLIENT_ID/SECRET fehlt in den Einstellungen).")
        res = await _resolve_spotify(spotify_cfg, kind, item_id)
        if res is None:
            raise ValueError("Konnte keine Songs zu diesem Spotify-Link finden (API-Abfrage fehlgeschlagen).")
        return res

    deezer_match = DEEZER_RE.search(query)
    if deezer_match:
        kind, item_id = deezer_match.groups()
        res = await _resolve_deezer(kind, item_id)
        if res is None:
            raise ValueError("Konnte keine Songs zu diesem Deezer-Link finden (API-Abfrage oder ID ungültig).")
        return res

    return None
