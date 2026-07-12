import time
import secrets
import logging
from datetime import datetime
from aiohttp import web, ClientSession, ClientTimeout

from utils.db_operations import DatabaseOperations

logger = logging.getLogger('discord_bot.oauth_server')

STATE_TTL_SECONDS = 600
REQUEST_TIMEOUT = ClientTimeout(total=10)

TOKEN_URL = 'https://discord.com/api/oauth2/token'
USER_URL = 'https://discord.com/api/users/@me'

SUCCESS_PAGE = """<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Verknüpfung erfolgreich</title></head>
<body style="font-family: sans-serif; text-align: center; padding-top: 10vh;">
<h1>✅ Verknüpfung erfolgreich!</h1>
<p>Du kannst dieses Fenster jetzt schließen und zu Discord zurückkehren.</p>
</body></html>"""


def _prune_expired_states(bot):
    """Drop expired state entries, e.g. from !connect runs that were never completed"""
    now = time.time()
    expired = [s for s, (_, created_at) in bot.oauth_states.items() if now - created_at > STATE_TTL_SECONDS]
    for s in expired:
        del bot.oauth_states[s]


def create_state(bot, user_id: int) -> str:
    """Generate a short-lived CSRF state token tied to the Discord user who ran !connect"""
    _prune_expired_states(bot)
    state = secrets.token_urlsafe(24)
    bot.oauth_states[state] = (user_id, time.time())
    return state


def _pop_valid_state(bot, state: str):
    entry = bot.oauth_states.pop(state, None)
    if not entry:
        return None
    user_id, created_at = entry
    if time.time() - created_at > STATE_TTL_SECONDS:
        return None
    return user_id


async def _exchange_code(oauth_cfg: dict, code: str) -> dict:
    data = {
        'client_id': oauth_cfg['client_id'],
        'client_secret': oauth_cfg['client_secret'],
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': oauth_cfg['redirect_uri'],
    }
    async with ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.post(TOKEN_URL, data=data) as resp:
            resp.raise_for_status()
            return await resp.json()


async def refresh_access_token(oauth_cfg: dict, refresh_token: str) -> dict:
    data = {
        'client_id': oauth_cfg['client_id'],
        'client_secret': oauth_cfg['client_secret'],
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
    }
    async with ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.post(TOKEN_URL, data=data) as resp:
            resp.raise_for_status()
            return await resp.json()


async def fetch_discord_user(access_token: str) -> dict:
    async with ClientSession(timeout=REQUEST_TIMEOUT) as session:
        async with session.get(USER_URL, headers={'Authorization': f'Bearer {access_token}'}) as resp:
            resp.raise_for_status()
            return await resp.json()


def _make_callback_handler(bot):
    async def callback(request: web.Request) -> web.Response:
        error = request.query.get('error')
        if error:
            return web.Response(text="Autorisierung abgebrochen.", status=400)

        code = request.query.get('code')
        state = request.query.get('state')
        if not code or not state:
            return web.Response(text="Fehlende Parameter.", status=400)

        user_id = _pop_valid_state(bot, state)
        if user_id is None:
            return web.Response(
                text="Ungültiger oder abgelaufener Link. Bitte führe `!connect` erneut aus.",
                status=400
            )

        try:
            token_data = await _exchange_code(bot.config['oauth'], code)
        except Exception:
            logger.exception("OAuth token exchange failed")
            return web.Response(text="Fehler beim Verbinden mit Discord. Bitte erneut versuchen.", status=502)

        # Der Login-Link ist an eine bestimmte Discord-User-ID gebunden (state -> user_id aus !connect).
        # Zusätzlich prüfen wir, dass der Account, der den Consent-Screen bestätigt hat, wirklich
        # dieser Nutzer ist - sonst könnte ein weitergeleiteter/kopierter Link fremde Tokens auf das
        # Konto des ursprünglichen Aufrufers schreiben.
        try:
            authorized_user = await fetch_discord_user(token_data['access_token'])
        except Exception:
            logger.exception("Failed to verify authorized Discord user")
            return web.Response(text="Fehler beim Verifizieren des Discord-Kontos.", status=502)

        if str(authorized_user.get('id')) != str(user_id):
            logger.warning(
                f"OAuth state/user mismatch: state issued for {user_id}, "
                f"authorized by {authorized_user.get('id')}"
            )
            return web.Response(
                text="Dieser Link wurde für einen anderen Discord-Account erstellt. "
                     "Bitte führe `!connect` mit dem Account aus, den du verknüpfen möchtest.",
                status=403
            )

        expires_at = datetime.utcfromtimestamp(time.time() + token_data.get('expires_in', 604800))
        await DatabaseOperations.upsert_oauth_link(
            bot.oauth_db,
            user_id,
            token_data['access_token'],
            token_data['refresh_token'],
            expires_at,
            token_data.get('scope', '')
        )
        logger.info(f"OAuth link stored for user {user_id}")

        return web.Response(text=SUCCESS_PAGE, content_type='text/html')

    return callback


async def start_oauth_server(bot) -> web.AppRunner:
    """Start the internal aiohttp server that handles the OAuth2 callback"""
    app = web.Application()
    app.router.add_get('/oauth/callback', _make_callback_handler(bot))

    runner = web.AppRunner(app)
    await runner.setup()
    port = bot.config['oauth'].get('web_port', 8080)
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"OAuth callback server listening on 0.0.0.0:{port}")
    return runner
