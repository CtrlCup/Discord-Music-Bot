# 🤖 Discord Multi-Function Bot

Ein leistungsstarker Discord Bot mit Musik-Streaming, Internet-Radio, umfangreichen Statistik-Funktionen und optionaler Konto-Verknüpfung, entwickelt von **Gamerfreak_LP aka Alex**.

## ✨ Features

### 🎵 Musik-Bot
- **Multi-Plattform Support**: YouTube, YouTube Music, Spotify und Deezer (Links werden über die jeweilige API aufgelöst und dann via YouTube abgespielt)
- **Internet-Radio**: `!play` ohne Angabe spielt einen konfigurierbaren Standard-Stream; weitere Sender lassen sich in der `.env` hinzufügen (`!radio list` / `!radio play <name>`)
- **Warteschlangen-System**: Ansehen, hinzufügen, entfernen, verschieben, mischen, komplett leeren
- **Vollständige Kontrolle**: Play, Pause, Stop, Skip, Previous, Loop, Volume Control
- **Songwechsel-Ankündigungen**: Postet bei jedem Songwechsel eine Nachricht in einen konfigurierbaren Kanal (pro Server an-/abschaltbar) und zeigt den Titel als Bot-Aktivität an

### 📊 Statistik-System
- **User Tracking**: Nachrichten, Sprachkanal-Zeit, Server-Beitritte, Hauptkanal, Ø Session-Länge, häufigster "Begleiter" im Sprachkanal
- **Leaderboards**: Nachrichten, Sprachzeit gesamt, Server-Beitritte, längste einzelne Sprachkanal-Session — umschaltbar per Buttons unter der Rangliste
- **Private Profildetails**: Mit `!connect` kann sich ein Nutzer per Discord-Login verknüpfen und bekommt in seinen *eigenen* `!stats` zusätzliche, sonst nicht sichtbare Daten (exaktes Kontoerstellungsdatum, E-Mail, MFA-Status, Nitro-Status) — nur für sich selbst, nie für andere
- **Persistente Speicherung**: MySQL oder SQLite

### ℹ️ Weitere Features
- **Flexible Präfixe**: Befehle mit `!` oder `/`
- **Automatische Datenbank-Fallbacks**: Wechselt automatisch zu SQLite, wenn MySQL nicht verfügbar ist
- **Server-Einstellungen**: `!settings` (nur für Mitglieder mit "Server verwalten") steuert Ankündigungskanal/-toggle pro Server
- **Umfangreiche Hilfe**: Detaillierte Befehlsübersicht mit `!info`

## 📋 Voraussetzungen

- [Docker](https://docs.docker.com/get-docker/) und Docker Compose (empfohlener Betrieb)
- Discord Bot Token
- Optional: Spotify-Developer-App (für Spotify-Links), eigene Domain + Reverse-Proxy (für `!connect`)

## 🚀 Installation (Docker Compose)

### 1. Repository klonen
```bash
git clone https://github.com/yourusername/discord-bot.git
cd discord-bot
```

### 2. `.env` anlegen
```bash
cp .env.example .env
```
Trage mindestens `DISCORD_BOT_TOKEN` ein (siehe unten, wie man einen Bot erstellt). Alle Einstellungen des Bots — Secrets **und** normale Einstellungen wie Präfix, Radiosender, Standard-Lautstärke-Verhalten etc. — kommen ausschließlich aus dieser `.env`-Datei; es gibt keine separate `config.json`. Details zu jedem Wert stehen als Kommentar in `.env.example`.

### 3. Discord Bot erstellen
1. Gehe zum [Discord Developer Portal](https://discord.com/developers/applications) → "New Application"
2. Gehe zu "Bot" → "Reset Token" → Token in `.env` als `DISCORD_BOT_TOKEN` eintragen
3. Aktiviere unter "Privileged Gateway Intents":
   - Server Members Intent
   - Message Content Intent
   - Presence Intent
4. Unter "OAuth2" findest du die **Client ID** (= Application ID) und kannst ein **Client Secret** erzeugen — beides in `.env` als `DISCORD_OAUTH_CLIENT_ID`/`DISCORD_OAUTH_CLIENT_SECRET` eintragen (nur nötig, wenn du `!connect` nutzen willst, siehe unten)

### 4. Bot zum Server einladen
1. Discord Developer Portal → "OAuth2" → "URL Generator"
2. Scopes: `bot` und `applications.commands`
3. Permissions: Send Messages, Embed Links, Read Message History, Add Reactions, Connect, Speak, Use Voice Activity, Manage Messages
4. Generierte URL im Browser öffnen und Server auswählen

### 5. Starten
```bash
docker compose build

# Mit SQLite (Standard, keine weitere Einrichtung nötig)
docker compose up -d

# Alternativ mit dem mitgelieferten MySQL-Container (DB_TYPE=mysql in der .env setzen)
docker compose --profile mysql up -d

docker compose logs -f bot
```

Der Bot sollte nun online sein und auf Befehle reagieren.

## 🎧 Spotify-Unterstützung einrichten (optional)

Spotify liefert nur Metadaten (Titel/Interpret), die eigentliche Wiedergabe läuft über YouTube:

1. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) → App erstellen
2. Client ID/Secret in `.env` als `SPOTIFY_CLIENT_ID`/`SPOTIFY_CLIENT_SECRET` eintragen
3. Die im Spotify-Dashboard geforderte Redirect-URI wird nicht genutzt (der Bot verwendet nur den Client-Credentials-Flow) — ein Platzhalterwert reicht aus

Ohne diese Angaben funktionieren YouTube/YouTube Music/Deezer-Links weiterhin normal; Spotify-Links liefern dann eine Fehlermeldung.

## 🔒 `!connect` einrichten: Domain & Reverse-Proxy (optional)

`!connect` schaltet in den *eigenen* `!stats` zusätzliche, per Discord-Login bestätigte Profildaten frei. Dafür braucht Discord eine öffentlich erreichbare HTTPS-Adresse für den OAuth2-Callback. Der Bot selbst bringt dafür nur einen einfachen internen Webserver mit (Port `8080`/`OAUTH_WEB_PORT`, standardmäßig nur an `127.0.0.1` des Docker-Hosts gebunden, siehe `docker-compose.yml`) — die öffentliche HTTPS-Seite übernimmt dein eigener Reverse-Proxy.

### Schritt 1: DNS
Lege einen A/AAAA-Eintrag an, der z. B. `bot.deinedomain.de` auf die öffentliche IP deines Servers zeigt.

### Schritt 2: Discord Developer Portal
Unter "OAuth2" → "Redirects" die exakt gleiche URL eintragen, die du in `.env` unter `DISCORD_OAUTH_REDIRECT_URI` hinterlegst, z. B.:
```
https://bot.deinedomain.de/oauth/callback
```

### Schritt 3: Reverse-Proxy konfigurieren

**Traefik (Beispiel mit dem File-Provider, funktioniert unabhängig davon, ob Traefik selbst containerisiert läuft):**

Statische Traefik-Konfiguration (`traefik.yml`) muss den File-Provider aktiviert haben:
```yaml
providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true

entryPoints:
  websecure:
    address: ":443"

certificatesResolvers:
  letsencrypt:
    acme:
      email: deine@email.de
      storage: /etc/traefik/acme.json
      httpChallenge:
        entryPoint: web
```

Dynamische Konfiguration, z. B. `/etc/traefik/dynamic/musicbot.yml`:
```yaml
http:
  routers:
    musicbot-oauth:
      rule: "Host(`bot.deinedomain.de`) && PathPrefix(`/oauth`)"
      entryPoints:
        - websecure
      service: musicbot-oauth
      tls:
        certResolver: letsencrypt

  services:
    musicbot-oauth:
      loadBalancer:
        servers:
          - url: "http://127.0.0.1:8080"
```

Läuft Traefik selbst als Docker-Container im selben Docker-Netzwerk wie der Bot, geht es alternativ auch ganz ohne dynamische Datei, direkt über Labels in der `docker-compose.yml` des Bots:
```yaml
services:
  bot:
    # ... restliche Konfiguration ...
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.musicbot-oauth.rule=Host(`bot.deinedomain.de`) && PathPrefix(`/oauth`)"
      - "traefik.http.routers.musicbot-oauth.entrypoints=websecure"
      - "traefik.http.routers.musicbot-oauth.tls.certresolver=letsencrypt"
      - "traefik.http.services.musicbot-oauth.loadbalancer.server.port=8080"
    networks:
      - traefik-public

networks:
  traefik-public:
    external: true
```
In diesem Fall zusätzlich das `ports:`-Mapping für den `bot`-Service in `docker-compose.yml` entfernen (Traefik erreicht den Container direkt über das gemeinsame Docker-Netzwerk) und stattdessen den Service ins `traefik-public`-Netzwerk hängen.

**Caddy (einfachste Variante, holt/erneuert das TLS-Zertifikat automatisch ohne weitere Konfiguration):**

Läuft Caddy direkt auf dem Host (nicht containerisiert), reicht ein `Caddyfile`:
```
bot.deinedomain.de {
    handle /oauth/* {
        reverse_proxy 127.0.0.1:8080
    }
}
```
Danach `caddy reload` (bzw. den Caddy-Dienst neu laden) — mehr ist nicht nötig, Caddy besorgt sich das Zertifikat beim ersten Start selbstständig.

Läuft Caddy stattdessen als eigener Docker-Container, entweder das `Caddyfile` per Volume einbinden:
```yaml
services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data

volumes:
  caddy_data:
```
und im `Caddyfile` `reverse_proxy 127.0.0.1:8080` durch die Docker-interne Adresse ersetzen (z. B. `reverse_proxy bot:8080`, sofern Caddy im selben Docker-Netzwerk wie der `bot`-Service hängt) — oder komplett auf Labels umsteigen, falls du ohnehin `caddy-docker-proxy` statt eines statischen `Caddyfile` einsetzt.

**nginx (Kurzfassung, falls weder Traefik noch Caddy verwendet werden):**
```nginx
server {
    listen 443 ssl;
    server_name bot.deinedomain.de;

    ssl_certificate     /etc/letsencrypt/live/bot.deinedomain.de/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.deinedomain.de/privkey.pem;

    location /oauth/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
    }
}
```

Ohne eingerichteten Reverse-Proxy funktioniert der Rest des Bots (Musik, Radio, Stats, Leaderboard, Settings) uneingeschränkt weiter — nur `!connect` zeigt dann keine funktionierende öffentliche Adresse.

## 📝 Befehls-Übersicht

### 🎵 Musik & Radio
| Befehl | Beschreibung |
|--------|-------------|
| `!play <link/suche>` | Spielt YouTube/YouTube Music/Spotify/Deezer oder fügt zur Warteschlange hinzu |
| `!play` (ohne Angabe) | Spielt den Standard-Radiostream |
| `!radio list` | Zeigt alle konfigurierten Radiosender |
| `!radio play <name>` | Spielt einen bestimmten Radiosender |
| `!stop` / `!pause` / `!resume` | Wiedergabesteuerung |
| `!skip` / `!next` · `!previous` / `!prev` | Song überspringen / vorherigen Song spielen |
| `!queue` / `!q` | Zeigt die Warteschlange inkl. aktuell laufendem Song und Laufzeit |
| `!remove <position>` · `!move <von> <nach>` · `!clear` · `!shuffle` | Warteschlange bearbeiten |
| `!loop <song/queue/off>` | Loop-Modus |
| `!nowplaying` / `!np` | Aktueller Song inkl. Fortschritt/Laufzeit |
| `!volume <0-100>` | Lautstärke |

### 📊 Statistik
| Befehl | Beschreibung |
|--------|-------------|
| `!stats [@user/name]` | Eigene oder fremde Statistiken (private Zusatzdaten nur bei eigener Abfrage, siehe `!connect`) |
| `!leaderboard [messages/voice/joins/longest_session]` | Rangliste mit Buttons zum Umschalten zwischen den Kategorien |
| `!connect` / `!disconnect` | Konto verknüpfen/trennen für private Profildetails |

### ⚙️ Einstellungen (nur Mitglieder mit "Server verwalten")
| Befehl | Beschreibung |
|--------|-------------|
| `!settings show` | Aktuelle Server-Einstellungen |
| `!settings announce #kanal` | Ankündigungskanal für Songwechsel setzen |
| `!settings announce_toggle on/off` | Songwechsel-Ankündigungen an-/ausschalten |

### ℹ️ System
| Befehl | Beschreibung |
|--------|-------------|
| `!info` / `!help` | Zeigt alle verfügbaren Befehle |
| `!ping` · `!uptime` · `!botinfo` · `!invite` | Bot-Status und Einladungslink |

## 🗂️ Projekt-Struktur

```
discord-bot/
├── bot.py                    # Bot-Einstiegspunkt, lädt Konfiguration aus .env
├── Dockerfile
├── docker-compose.yml
├── .env.example               # Vorlage für alle Einstellungen/Secrets
├── requirements.txt
├── cogs/
│   ├── music_advanced.py     # Musik, Radio, Warteschlange
│   ├── stats.py              # Statistiken, Leaderboard, private Profildetails
│   ├── statistics_advanced.py # Musik-Hörgewohnheiten
│   ├── playlists.py          # Nutzer-Playlists & Favoriten
│   ├── account.py            # !connect / !disconnect (OAuth2)
│   ├── settings.py           # Server-Einstellungen (Ankündigungen)
│   └── info.py                # Hilfe & System-Befehle
├── utils/
│   ├── database.py           # SQLite/MySQL-Abstraktion
│   ├── db_operations.py      # SQL-Queries
│   ├── music_utils.py        # Queue, YTDLSource, Stream-Auflösung
│   ├── track_resolver.py     # Spotify/Deezer -> YouTube-Suche
│   └── oauth_server.py       # Interner Webserver für den OAuth2-Callback
└── tests/                    # unittest-Suite (siehe unten)
```

## 🧪 Tests

```bash
docker run --rm --entrypoint python discord-music-bot-bot -m unittest discover -s tests -v
```

Deckt u. a. den SSRF-Schutz der Deezer-Link-Auflösung, die CSRF/Replay-Absicherung des `!connect`-OAuth-Flows, die Permission-Gates von `!settings` und die SQL-Queries hinter den erweiterten Statistiken ab (letztere gegen eine echte In-Memory-SQLite-DB).

## 🔧 Konfiguration

Alles läuft über `.env` (siehe `.env.example` für alle verfügbaren Variablen und Erklärungen):
- **Secrets/Verbindung**: `DISCORD_BOT_TOKEN`, `DISCORD_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI`, `SPOTIFY_CLIENT_ID/SECRET`, `DB_TYPE` + MySQL-Zugangsdaten
- **Bot-Verhalten**: `BOT_PREFIX`, `BOT_DISPLAY_NAME`, `BOT_ACTIVITY`
- **Musik/Radio**: `MUSIC_DEFAULT_STREAM_URL`, `RADIO_STREAMS` (JSON-Liste), `MUSIC_EMPTY_CHANNEL_TIMEOUT`, `MUSIC_TIMEOUT`, `MUSIC_MULTI_CHANNEL_SUPPORT`
- **Sonstiges**: `PLAYLISTS_MAX_PER_USER`, `NOTIFICATIONS_SONG_CHANGE_DEFAULT_ENABLED`, `OAUTH_SCOPES`

### Datenbank-Optionen

- **SQLite** (Standard): keine zusätzliche Installation, ideal für kleine bis mittlere Server
- **MySQL**: `DB_TYPE=mysql` in `.env` setzen und `docker compose --profile mysql up -d` verwenden; bei Nichterreichbarkeit fällt der Bot automatisch auf SQLite zurück

## 🐛 Fehlerbehebung

### Bot reagiert nicht auf Befehle
- `docker compose logs -f bot` auf Fehler prüfen
- Bot-Berechtigungen auf dem Server kontrollieren
- Präfix in `.env` (`BOT_PREFIX`) kontrollieren

### Musik/Radio spielt nicht ab
- Logs auf ffmpeg-Fehlermeldungen prüfen (`docker compose logs bot`)
- Sicherstellen, dass der Bot "Speak"-Rechte im jeweiligen Sprachkanal hat
- Lokale Lautstärke des Bots bei dir (Rechtsklick auf den Bot im Sprachkanal) prüfen

### `!connect` funktioniert nicht
- `DISCORD_OAUTH_CLIENT_ID/SECRET/REDIRECT_URI` in `.env` gesetzt?
- Redirect-URI im Discord Developer Portal identisch zu `.env` hinterlegt?
- Reverse-Proxy erreicht den internen Webserver auf Port `8080`? (siehe Abschnitt oben)

### Datenbank-Fehler
- Bei MySQL: Verbindungsdaten in `.env` prüfen
- Bot wechselt automatisch zu SQLite als Fallback
- Logs in `bot.log` / `docker compose logs bot` prüfen

## 📊 Performance-Tipps

- Nutze MySQL für Server mit >1000 Mitgliedern
- Regelmäßige Datenbank-Backups erstellen (`./data/bot_database.db` bzw. das `mysql_data`-Volume)
- Bot-Logs regelmäßig leeren

## 🤝 Beitragen

Contributions sind willkommen! Bitte erstelle einen Pull Request oder öffne ein Issue für Verbesserungsvorschläge.

## 📜 Lizenz

Dieses Projekt ist unter der MIT Lizenz lizenziert.

## 👨‍💻 Autor

**Gamerfreak_LP aka Alex**

## 🙏 Danksagungen

- Discord.py Community
- yt-dlp Entwickler
- Alle Tester und Nutzer

## 📞 Support

Bei Fragen oder Problemen:
- Öffne ein Issue auf GitHub
- Nutze den `!info` Befehl im Bot

---

⭐ Wenn dir dieses Projekt gefällt, gib ihm einen Stern auf GitHub!
