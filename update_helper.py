#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys
import shutil

def print_colored(text, color):
    colors = {
        'red': '\033[91m',
        'green': '\033[92m',
        'yellow': '\033[93m',
        'blue': '\033[94m',
        'bold': '\033[1m',
        'reset': '\033[0m'
    }
    # Check if stdout is a tty (supports colors)
    if sys.stdout.isatty():
        print(f"{colors.get(color, '')}{text}{colors['reset']}")
    else:
        print(text)

def parse_env(filepath):
    env = {}
    if not os.path.exists(filepath):
        return env
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env

def get_file_version(filepath):
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if first_line.startswith('# Version:'):
                return first_line.split(':', 1)[1].strip()
    except Exception:
        pass
    return None

def get_git_status():
    try:
        # Run git status --porcelain to see changes
        res = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
        return res.stdout.strip().split('\n')
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

def check_env():
    print_colored("\n--- 🔍 Überprüfe .env Konfiguration ---", "blue")
    if not os.path.exists('.env'):
        print_colored("❌ Keine .env-Datei gefunden!", "red")
        print("Erstelle eine Kopie von .env.example als .env und passe diese an.")
        return False
    
    example_env = parse_env('.env.example')
    local_env = parse_env('.env')
    
    missing_keys = []
    for key in example_env:
        if key not in local_env:
            missing_keys.append(key)
            
    if missing_keys:
        print_colored("⚠️ Folgende Variablen fehlen in deiner .env (neu in .env.example):", "yellow")
        for key in missing_keys:
            print(f"  - {key}")
        print("\nBitte füge diese Variablen zu deiner `.env` hinzu.")
        return False
    else:
        print_colored("✅ Deine .env ist aktuell! Alle Variablen aus .env.example sind vorhanden.", "green")
        return True

def check_versions():
    """Vergleicht die lokalen .env/docker-compose.yml gegen die aktuell erwarteten
    Template-Versionen. Die "aktuell erwarteten" Versionen stehen zusammen mit
    BOT_VERSION zentral in static.env (ENV_TEMPLATE_VERSION/COMPOSE_TEMPLATE_VERSION),
    statt verstreut in den Kopfzeilen von .env.example/docker-compose.yml.example -
    so lassen sich alle drei Versionsnummern an einer Stelle prüfen."""
    print_colored("\n--- 📝 Überprüfe Datei-Versionen ---", "blue")

    static = parse_env('static.env')

    # Check .env
    example_env_ver = static.get('ENV_TEMPLATE_VERSION')
    local_env_ver = get_file_version('.env')

    env_ok = True
    if example_env_ver:
        if not local_env_ver:
            print_colored(f"⚠️ Deine .env hat keine Versionsangabe (Aktuelle Vorlage: v{example_env_ver}).", "yellow")
            print("  Es wird empfohlen, die Version zu prüfen und ggf. neue Einstellungen zu übernehmen.")
            env_ok = False
        elif local_env_ver != example_env_ver:
            print_colored(f"⚠️ Deine .env (v{local_env_ver}) weicht von der Vorlage .env.example (v{example_env_ver}) ab!", "yellow")
            print("  Es wurden möglicherweise neue Variablen hinzugefügt. Überprüfe die Änderungen in .env.example.")
            env_ok = False
        else:
            print_colored(f"✅ .env Version ist aktuell (v{local_env_ver})", "green")

    # Check docker-compose.yml
    if not os.path.exists('docker-compose.yml'):
        print_colored("❌ Keine docker-compose.yml gefunden!", "red")
        print("  Bitte erstelle eine Kopie von docker-compose.yml.example als docker-compose.yml.")
        return False

    example_compose_ver = static.get('COMPOSE_TEMPLATE_VERSION')
    local_compose_ver = get_file_version('docker-compose.yml')

    compose_ok = True
    if example_compose_ver:
        if not local_compose_ver:
            print_colored(f"⚠️ Deine docker-compose.yml hat keine Versionsangabe (Aktuelle Vorlage: v{example_compose_ver}).", "yellow")
            print("  Es wird empfohlen, die Vorlage auf Änderungen zu überprüfen.")
            compose_ok = False
        elif local_compose_ver != example_compose_ver:
            print_colored(f"⚠️ Deine docker-compose.yml (v{local_compose_ver}) weicht von der Vorlage docker-compose.yml.example (v{example_compose_ver}) ab!", "yellow")
            print("  Bitte prüfe, ob sich an den Service-Definitionen in der Vorlage etwas geändert hat.")
            compose_ok = False
        else:
            print_colored(f"✅ docker-compose.yml Version ist aktuell (v{local_compose_ver})", "green")
    return env_ok and compose_ok

def get_upstream_branch():
    try:
        res = subprocess.run(['git', 'rev-parse', '--abbrev-ref', '@{u}'], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        return 'origin/main'

def get_remote_bot_version(upstream):
    try:
        res = subprocess.run(['git', 'show', f'{upstream}:static.env'], capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                if key.strip() == 'BOT_VERSION':
                    return val.strip()
    except Exception:
        pass
    return None

def check_bot_version():
    print_colored("\n--- 🤖 Überprüfe Bot-Version ---", "blue")
    
    # Check static.env for local version
    local_static = parse_env('static.env')
    local_ver = local_static.get('BOT_VERSION')
    
    if not local_ver:
        print_colored("⚠️ Lokale Bot-Version konnte nicht aus static.env gelesen werden.", "yellow")
        return False
        
    upstream = get_upstream_branch()
    
    # Remote version from Git
    # First, let's fetch to ensure we have the latest info
    try:
        subprocess.run(['git', 'fetch'], capture_output=True, timeout=5, check=False)
    except Exception:
        pass
        
    remote_ver = get_remote_bot_version(upstream)
    
    if not remote_ver:
        print(f"Deine Version: v{local_ver}")
        print_colored("⚠️ Aktuelle Version auf GitHub konnte nicht ermittelt werden (Prüfe Internetverbindung/Git).", "yellow")
        return True
        
    if local_ver != remote_ver:
        print_colored(f"📢 Update verfügbar! Deine Version: v{local_ver} | Aktuelle Version: v{remote_ver}", "yellow")
        print("  Führe 'python3 update_helper.py pull' aus, um das Update zu installieren.")
        return False
    else:
        print_colored(f"✅ Bot-Version ist aktuell (v{local_ver})", "green")
        return True

def check_git():
    print_colored("\n--- 🐙 Überprüfe Git-Status ---", "blue")
    status_lines = get_git_status()
    if status_lines is None:
        print("Git ist auf diesem System nicht konfiguriert oder dies ist kein Git-Repository.")
        return True
    
    status_lines = [line for line in status_lines if line] # filter empty lines
    if not status_lines:
        print_colored("✅ Keine lokalen Änderungen vorhanden. Bereit zum Aktualisieren.", "green")
        return True
        
    other_changed = []
    for line in status_lines:
        filepath = line[3:]
        other_changed.append(filepath)
        
    if other_changed:
        print("Lokale Änderungen oder unversionierte Dateien:")
        for path in other_changed:
            print(f"  - {path}")
            
    return True

def run_pull():
    print_colored("\n--- ⬇️ Hole Updates von GitHub ---", "blue")
    try:
        print("Hole neueste Änderungen von GitHub...")
        subprocess.run(['git', 'fetch'], check=True)
        
        # Falls docker-compose.yml noch im Git-Index des lokalen Repos liegt,
        # könnte es beim pullen gelöscht/überschrieben werden.
        # Wir sichern es präventiv als Backup und stellen es danach wieder her.
        backup_created = False
        if os.path.exists('docker-compose.yml'):
            res = subprocess.run(['git', 'ls-files', 'docker-compose.yml'], capture_output=True, text=True)
            if res.stdout.strip():
                print_colored("⚠️ docker-compose.yml wird lokal noch von Git getrackt und wird beim Pull entfernt.", "yellow")
                print("  Erstelle Sicherheitskopie: docker-compose.yml.backup")
                shutil.copy('docker-compose.yml', 'docker-compose.yml.backup')
                backup_created = True
        
        print("Führe 'git pull' aus...")
        subprocess.run(['git', 'pull'], check=True)
        
        if backup_created:
            print_colored("✅ Pull abgeschlossen. Restauriere deine docker-compose.yml aus dem Backup...", "green")
            shutil.move('docker-compose.yml.backup', 'docker-compose.yml')
            # Aus Git-Index entfernen, da es jetzt ignoriert sein sollte
            subprocess.run(['git', 'rm', '--cached', 'docker-compose.yml'], capture_output=True)
            
        print_colored("✅ Repository erfolgreich aktualisiert!", "green")
    except subprocess.CalledProcessError as e:
        print_colored(f"❌ Fehler bei der Git-Operation: {e}", "red")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'pull':
        run_pull()
        check_env()
        check_versions()
        check_bot_version()
        check_git()
    else:
        # Default: Check status
        env_ok = check_env()
        ver_ok = check_versions()
        bot_ok = check_bot_version()
        git_ok = check_git()
        
        print_colored("\n--- 💡 Hilfe / Anleitung ---", "blue")
        print("Verwendung:")
        print("  python3 update_helper.py         - Führt Status-Checks durch (empfohlen)")
        print("  python3 update_helper.py pull    - Holt Updates von GitHub und prüft danach die Konfiguration")
        
        if not env_ok or not ver_ok or not bot_ok or not git_ok:
            print_colored("\nBitte behebe die obigen Warnungen, um einen reibungslosen Betrieb zu gewährleisten.", "yellow")

if __name__ == '__main__':
    main()
