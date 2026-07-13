#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import sys

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
        
    docker_compose_changed = False
    other_changed = []
    
    for line in status_lines:
        # state shows status like " M", "M ", etc.
        filepath = line[3:]
        if 'docker-compose.yml' in filepath:
            docker_compose_changed = True
        else:
            other_changed.append(filepath)
            
    if docker_compose_changed:
        print_colored("⚠️ Du hast lokale Änderungen an 'docker-compose.yml' vorgenommen.", "yellow")
        print("Dies führt bei 'git pull' zu Konflikten, falls sich die Datei auf GitHub geändert hat.")
        print_colored("Lösung für konfliktfreie Updates:", "bold")
        print("  1. Kopiere deine Anpassungen in 'docker-compose.override.yml' (Vorlage siehe 'docker-compose.override.yml.example').")
        print("  2. Setze 'docker-compose.yml' in den Originalzustand zurück:")
        print_colored("     git restore docker-compose.yml", "blue")
        print("Danach läuft 'git pull' reibungslos durch und deine Anpassungen bleiben in der Override-Datei aktiv.")
        
    if other_changed:
        print("\nWeitere geänderte Dateien:")
        for path in other_changed:
            print(f"  - {path}")
            
    return not docker_compose_changed

def run_pull():
    print_colored("\n--- ⬇️ Hole Updates von GitHub ---", "blue")
    try:
        print("Hole neueste Änderungen von GitHub...")
        subprocess.run(['git', 'fetch'], check=True)
        
        # Check if we have changes in docker-compose.yml that would conflict
        git_status = get_git_status()
        if git_status:
            for line in git_status:
                if 'docker-compose.yml' in line:
                    print_colored("❌ Update abgebrochen! Lokale Änderungen an 'docker-compose.yml' verhindern ein sauberes Pull.", "red")
                    print("Bitte verschiebe deine Änderungen zuerst in 'docker-compose.override.yml'.")
                    return
        
        print("Führe 'git pull' aus...")
        subprocess.run(['git', 'pull'], check=True)
        print_colored("✅ Repository erfolgreich aktualisiert!", "green")
    except subprocess.CalledProcessError as e:
        print_colored(f"❌ Fehler bei der Git-Operation: {e}", "red")

def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'pull':
        run_pull()
        check_env()
        check_git()
    else:
        # Default: Check status
        env_ok = check_env()
        git_ok = check_git()
        
        print_colored("\n--- 💡 Hilfe / Anleitung ---", "blue")
        print("Verwendung:")
        print("  python3 update_helper.py         - Führt Status-Checks durch (empfohlen)")
        print("  python3 update_helper.py pull    - Holt Updates von GitHub und prüft danach die Konfiguration")
        
        if not env_ok or not git_ok:
            print_colored("\nBitte behebe die obigen Warnungen, um spätere Update-Konflikte zu vermeiden.", "yellow")

if __name__ == '__main__':
    main()
