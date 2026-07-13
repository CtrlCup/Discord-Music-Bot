import asyncio
import aiomysql
import aiosqlite
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger('discord_bot.database')

class Database:
    def __init__(self, config):
        self.config = config['database']
        self.connection = None
        self.pool = None
        self.db_type = self.config['type']
        
    async def initialize(self):
        """Initialize database connection and create tables"""
        try:
            if self.db_type == 'mysql' and self.config['local'] and not await self._check_mysql_available():
                logger.info("MySQL lokal nicht erreichbar, verwende stattdessen SQLite...")
                self.db_type = 'sqlite'

            if self.db_type == 'sqlite':
                await self._init_sqlite()
            else:
                await self._init_mysql()
            
            await self._create_tables()
            await self._migrate_existing_tables()
            logger.info(f"Database initialized successfully using {self.db_type}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            # Fallback to SQLite if MySQL fails
            if self.db_type == 'mysql':
                logger.info("Falling back to SQLite...")
                self.db_type = 'sqlite'
                await self._init_sqlite()
                await self._create_tables()
                await self._migrate_existing_tables()

    async def _migrate_existing_tables(self):
        """Best-effort ALTER TABLE for columns added after the initial release (ignores 'already exists' errors)"""
        alter_statements = [
            "ALTER TABLE user_stats ADD COLUMN join_count INTEGER DEFAULT 0",
            "ALTER TABLE guild_settings ADD COLUMN announce_channel_id INTEGER",
            "ALTER TABLE guild_settings ADD COLUMN announce_enabled BOOLEAN DEFAULT 1",
            "ALTER TABLE guild_settings ADD COLUMN user_role_id BIGINT",
            "ALTER TABLE guild_settings ADD COLUMN supporter_role_id BIGINT",
            "ALTER TABLE guild_settings ADD COLUMN admin_role_id BIGINT",
        ]

        if self.db_type == 'sqlite':
            for stmt in alter_statements:
                try:
                    await self.connection.execute(stmt)
                except Exception:
                    pass  # column already exists
            await self.connection.commit()
        else:
            async with self.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    for stmt in alter_statements:
                        try:
                            await cursor.execute(stmt)
                        except Exception:
                            pass  # column already exists
    
    async def _check_mysql_available(self):
        """Check if MySQL is available"""
        try:
            conn = await aiomysql.connect(
                host=self.config['host'],
                port=self.config['port'],
                user=self.config['username'],
                password=self.config['password']
            )
            await conn.ensure_closed()
            return True
        except Exception:
            return False
    
    async def _init_sqlite(self):
        """Initialize SQLite connection"""
        self.connection = await aiosqlite.connect(self.config.get('sqlite_path', 'bot_database.db'))
        self.connection.row_factory = aiosqlite.Row
    
    async def _init_mysql(self):
        """Initialize MySQL connection pool"""
        self.pool = await aiomysql.create_pool(
            host=self.config['host'],
            port=self.config['port'],
            user=self.config['username'],
            password=self.config['password'],
            db=self.config['database'],
            autocommit=True,
            minsize=1,
            maxsize=10
        )
    
    async def _create_tables(self):
        """Create necessary tables"""
        if self.db_type == 'sqlite':
            await self._create_tables_sqlite()
        else:
            await self._create_tables_mysql()
    
    async def _create_tables_sqlite(self):
        """Create SQLite tables"""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                first_joined TIMESTAMP,
                last_seen TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                voice_time_seconds INTEGER DEFAULT 0,
                total_time_seconds INTEGER DEFAULT 0,
                join_count INTEGER DEFAULT 0,
                UNIQUE(user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS voice_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                join_time TIMESTAMP NOT NULL,
                leave_time TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_length INTEGER
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS song_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                song_duration INTEGER,
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                listening_duration INTEGER DEFAULT 0,
                skipped BOOLEAN DEFAULT 0
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                is_public BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                play_count INTEGER DEFAULT 0,
                UNIQUE(user_id, guild_id, name)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS playlist_songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                song_duration INTEGER,
                position INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS favorite_songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                song_title TEXT NOT NULL,
                song_url TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                play_count INTEGER DEFAULT 0,
                UNIQUE(user_id, guild_id, song_url)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dj_roles (
                guild_id INTEGER PRIMARY KEY,
                role_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                default_volume REAL DEFAULT 0.5,
                auto_play BOOLEAN DEFAULT 0,
                announce_songs BOOLEAN DEFAULT 1,
                allow_duplicates BOOLEAN DEFAULT 1,
                max_song_duration INTEGER DEFAULT 3600,
                announce_channel_id INTEGER,
                announce_enabled BOOLEAN DEFAULT 1,
                user_role_id INTEGER,
                supporter_role_id INTEGER,
                admin_role_id INTEGER,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS oauth_links (
                user_id INTEGER PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                scope TEXT,
                linked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_user_guild ON user_stats(user_id, guild_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_voice_user ON voice_sessions(user_id, guild_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_message_user ON message_log(user_id, guild_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_song_history ON song_history(guild_id, user_id, played_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_playlists_user ON playlists(user_id, guild_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_favorites ON favorite_songs(user_id, guild_id)
            """
        ]
        
        for query in queries:
            await self.connection.execute(query)
        await self.connection.commit()
    
    async def _create_tables_mysql(self):
        """Create MySQL tables"""
        queries = [
            f"""
            CREATE DATABASE IF NOT EXISTS {self.config['database']}
            """,
            f"""
            USE {self.config['database']}
            """,
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id BIGINT,
                guild_id BIGINT NOT NULL,
                username VARCHAR(255) NOT NULL,
                first_joined DATETIME,
                last_seen DATETIME,
                message_count INT DEFAULT 0,
                voice_time_seconds INT DEFAULT 0,
                total_time_seconds INT DEFAULT 0,
                join_count INT DEFAULT 0,
                PRIMARY KEY (user_id, guild_id),
                INDEX idx_user_guild (user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS voice_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                join_time DATETIME NOT NULL,
                leave_time DATETIME,
                duration_seconds INT DEFAULT 0,
                INDEX idx_voice_user (user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS message_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                message_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                message_length INT,
                INDEX idx_message_user (user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS song_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                song_title VARCHAR(500) NOT NULL,
                song_url VARCHAR(500) NOT NULL,
                song_duration INT,
                played_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                listening_duration INT DEFAULT 0,
                skipped BOOLEAN DEFAULT FALSE,
                INDEX idx_song_history (guild_id, user_id, played_at)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS playlists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                is_public BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                play_count INT DEFAULT 0,
                UNIQUE KEY unique_playlist (user_id, guild_id, name),
                INDEX idx_playlists_user (user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS playlist_songs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                playlist_id INT NOT NULL,
                song_title VARCHAR(500) NOT NULL,
                song_url VARCHAR(500) NOT NULL,
                song_duration INT,
                position INT NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                INDEX idx_playlist_songs (playlist_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS favorite_songs (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                song_title VARCHAR(500) NOT NULL,
                song_url VARCHAR(500) NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                play_count INT DEFAULT 0,
                UNIQUE KEY unique_favorite (user_id, guild_id, song_url),
                INDEX idx_favorites (user_id, guild_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS dj_roles (
                guild_id BIGINT PRIMARY KEY,
                role_id BIGINT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id BIGINT PRIMARY KEY,
                default_volume FLOAT DEFAULT 0.5,
                auto_play BOOLEAN DEFAULT FALSE,
                announce_songs BOOLEAN DEFAULT TRUE,
                allow_duplicates BOOLEAN DEFAULT TRUE,
                max_song_duration INT DEFAULT 3600,
                announce_channel_id BIGINT,
                announce_enabled BOOLEAN DEFAULT TRUE,
                user_role_id BIGINT,
                supporter_role_id BIGINT,
                admin_role_id BIGINT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS oauth_links (
                user_id BIGINT PRIMARY KEY,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                scope VARCHAR(255),
                linked_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        ]
        
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cursor:
                for query in queries:
                    await cursor.execute(query)
