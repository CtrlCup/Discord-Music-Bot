# 🤖 Discord Multi-Function Bot

Ein leistungsstarker Discord Bot mit Musik-Streaming und umfangreichen Statistik-Funktionen, entwickelt von **Gamerfreak_LP aka Alex**.

## ✨ Features

### 🎵 Musik-Bot
- **Multi-Plattform Support**: YouTube, YouTube Music (Spotify & Deezer in Entwicklung)
- **Warteschlangen-System**: Automatische Playlist-Verwaltung
- **Vollständige Kontrolle**: Play, Pause, Stop, Skip, Volume Control
- **Smart Search**: Direkte URLs oder Suchbegriffe verwenden

### 📊 Statistik-System
- **User Tracking**: Automatisches Tracking von Benutzeraktivitäten
- **Detaillierte Stats**: Nachrichten-Anzahl, Voice-Chat Zeit, Server-Beitritt
- **Leaderboards**: Top-Listen für verschiedene Kategorien
- **Persistente Speicherung**: MySQL/SQLite Datenbank-Support

### ℹ️ Weitere Features
- **Flexible Präfixe**: Befehle mit `!` oder `/`
- **Automatische Datenbank-Fallbacks**: Wechselt automatisch zu SQLite wenn MySQL nicht verfügbar
- **Umfangreiche Hilfe**: Detaillierte Befehlsübersicht mit `!info`

## 📋 Voraussetzungen

- Python 3.8 oder höher
- FFmpeg (für Musik-Wiedergabe)
- MySQL Server (optional, SQLite als Fallback)
- Discord Bot Token

## 🚀 Installation

### 1. Repository klonen
```bash
git clone https://github.com/yourusername/discord-bot.git
cd discord-bot
```

### 2. Virtuelle Umgebung erstellen (empfohlen)
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Abhängigkeiten installieren
```bash
pip install -r requirements.txt
```

### 4. FFmpeg installieren

#### Windows
1. Download von [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extrahieren und zum PATH hinzufügen

#### Linux
```bash
sudo apt-get update
sudo apt-get install ffmpeg
```

#### macOS
```bash
brew install ffmpeg
```

### 5. Bot konfigurieren
1. Kopiere `config.json` und passe die Werte an:
```json
{
    "bot": {
        "token": "DEIN_DISCORD_BOT_TOKEN",
        "prefix": ["!", "/"],
        "activity": "Listening to !info",
        "owner": "Dein Name"
    },
    "database": {
        "type": "mysql",
        "local": true,
        "host": "localhost",
        "port": 3306,
        "username": "root",
        "password": "dein_passwort",
        "database": "discord_bot_stats",
        "sqlite_path": "bot_database.db"
    }
}
```

### 6. Discord Bot erstellen
1. Gehe zu [Discord Developer Portal](https://discord.com/developers/applications)
2. Klicke auf "New Application"
3. Gib deinem Bot einen Namen
4. Gehe zu "Bot" im linken Menü
5. Klicke "Add Bot"
6. Kopiere den Token und füge ihn in `config.json` ein
7. Aktiviere folgende Intents:
   - Server Members Intent
   - Message Content Intent
   - Presence Intent

### 7. Bot zum Server einladen
1. Im Developer Portal, gehe zu "OAuth2" → "URL Generator"
2. Wähle Scopes: `bot` und `applications.commands`
3. Wähle benötigte Permissions:
   - Send Messages
   - Embed Links
   - Attach Files
   - Read Message History
   - Add Reactions
   - Connect
   - Speak
   - Use Voice Activity
   - Manage Messages
4. Kopiere die generierte URL und öffne sie im Browser

## 🎮 Bot starten

```bash
python bot.py
```

Der Bot sollte nun online sein und auf Befehle reagieren!

## 📝 Befehls-Übersicht

### 🎵 Musik-Befehle
| Befehl | Beschreibung |
|--------|-------------|
| `!play <link/suche>` | Spielt einen Song oder fügt ihn zur Warteschlange hinzu |
| `!stop` | Stoppt die Musik und leert die Warteschlange |
| `!pause` | Pausiert die aktuelle Wiedergabe |
| `!resume` | Setzt die pausierte Wiedergabe fort |
| `!skip` / `!next` | Überspringt den aktuellen Song |
| `!queue` / `!q` | Zeigt die aktuelle Warteschlange |
| `!volume <0-100>` | Ändert die Lautstärke |

### 📊 Statistik-Befehle
| Befehl | Beschreibung |
|--------|-------------|
| `!stats` | Zeigt deine eigenen Statistiken |
| `!stats <@user/name>` | Zeigt Statistiken eines anderen Benutzers |
| `!leaderboard <messages/voice>` | Zeigt die Top 10 Rangliste |

### ℹ️ System-Befehle
| Befehl | Beschreibung |
|--------|-------------|
| `!info` / `!help` | Zeigt alle verfügbaren Befehle |
| `!ping` | Zeigt die Bot-Latenz |
| `!uptime` | Zeigt die Betriebszeit des Bots |
| `!botinfo` | Zeigt technische Bot-Informationen |
| `!invite` | Zeigt den Einladungslink für den Bot |

## 🗂️ Projekt-Struktur

```
discord-bot/
├── bot.py              # Haupt-Bot-Datei
├── config.json         # Konfigurationsdatei
├── requirements.txt    # Python-Abhängigkeiten
├── .gitignore         # Git ignore Datei
├── README.md          # Diese Datei
├── cogs/              # Bot-Module
│   ├── music.py       # Musik-Funktionalität
│   ├── stats.py       # Statistik-System
│   └── info.py        # Info & Hilfe Befehle
└── utils/             # Hilfsfunktionen
    ├── database.py    # Datenbank-Verbindung
    └── db_operations.py # Datenbank-Operationen
```

## 🔧 Konfiguration

### Datenbank-Optionen

Der Bot unterstützt sowohl MySQL als auch SQLite:

- **MySQL** (empfohlen für Produktion):
  - Bessere Performance bei vielen Benutzern
  - Externe Backups möglich
  - Mehrere Bots können dieselbe Datenbank nutzen

- **SQLite** (Standard-Fallback):
  - Keine zusätzliche Installation nötig
  - Perfekt für kleine bis mittlere Server
  - Automatisch aktiviert wenn MySQL nicht verfügbar

### Anpassungen

Du kannst folgende Aspekte in `config.json` anpassen:
- Bot-Token und Präfixe
- Datenbank-Verbindung
- Standard-Lautstärke für Musik
- Maximale Warteschlangen-Größe
- Voice-Channel Timeout

## 🐛 Fehlerbehebung

### Bot reagiert nicht auf Befehle
- Stelle sicher, dass der Bot online ist
- Überprüfe, ob der Bot die nötigen Berechtigungen hat
- Kontrolliere die Präfixe in `config.json`

### Musik spielt nicht ab
- FFmpeg muss installiert und im PATH sein
- Überprüfe die Internet-Verbindung
- Stelle sicher, dass der Bot Sprach-Berechtigungen hat

### Datenbank-Fehler
- Bei MySQL: Überprüfe Verbindungsdaten
- Bot wechselt automatisch zu SQLite als Fallback
- Logs in `bot.log` überprüfen

## 📊 Performance-Tipps

- Nutze MySQL für Server mit >1000 Mitgliedern
- Aktiviere nur benötigte Features
- Regelmäßige Datenbank-Backups erstellen
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
