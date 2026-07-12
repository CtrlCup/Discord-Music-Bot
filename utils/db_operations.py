import aiomysql
from datetime import datetime
from typing import Optional, Dict, Any, List

class DatabaseOperations:
    """Database operations for user statistics"""
    
    @staticmethod
    async def update_user_stats(db, user_id: int, guild_id: int, username: str, event_type: str, **kwargs):
        """Update user statistics based on event type"""
        now = datetime.utcnow()
        
        if db.db_type == 'sqlite':
            conn = db.connection
            
            # Check if user exists
            cursor = await conn.execute(
                "SELECT * FROM user_stats WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            )
            user_exists = await cursor.fetchone()
            
            if not user_exists:
                # Create new user record
                await conn.execute(
                    """
                    INSERT INTO user_stats (user_id, guild_id, username, first_joined, last_seen)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, guild_id, username, now, now)
                )
            
            # Update based on event type
            if event_type == 'message':
                await conn.execute(
                    """
                    UPDATE user_stats 
                    SET message_count = message_count + 1, last_seen = ?
                    WHERE user_id = ? AND guild_id = ?
                    """,
                    (now, user_id, guild_id)
                )
                
                # Log message
                await conn.execute(
                    """
                    INSERT INTO message_log (user_id, guild_id, channel_id, message_time, message_length)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, guild_id, kwargs.get('channel_id'), now, kwargs.get('message_length', 0))
                )
            
            elif event_type == 'server_join':
                await conn.execute(
                    """
                    UPDATE user_stats
                    SET join_count = join_count + 1, last_seen = ?
                    WHERE user_id = ? AND guild_id = ?
                    """,
                    (now, user_id, guild_id)
                )

            elif event_type == 'voice_join':
                # Create voice session
                await conn.execute(
                    """
                    INSERT INTO voice_sessions (user_id, guild_id, channel_id, join_time)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, guild_id, kwargs.get('channel_id'), now)
                )

            elif event_type == 'voice_leave':
                # Update voice session
                cursor = await conn.execute(
                    """
                    SELECT id, join_time FROM voice_sessions 
                    WHERE user_id = ? AND guild_id = ? AND leave_time IS NULL
                    ORDER BY join_time DESC LIMIT 1
                    """,
                    (user_id, guild_id)
                )
                session = await cursor.fetchone()
                
                if session:
                    join_time = datetime.fromisoformat(str(session['join_time']))
                    duration = int((now - join_time).total_seconds())
                    
                    await conn.execute(
                        """
                        UPDATE voice_sessions 
                        SET leave_time = ?, duration_seconds = ?
                        WHERE id = ?
                        """,
                        (now, duration, session['id'])
                    )
                    
                    # Update total voice time
                    await conn.execute(
                        """
                        UPDATE user_stats 
                        SET voice_time_seconds = voice_time_seconds + ?, last_seen = ?
                        WHERE user_id = ? AND guild_id = ?
                        """,
                        (duration, now, user_id, guild_id)
                    )
            
            await conn.commit()
            
        else:  # MySQL
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # Check if user exists
                    await cursor.execute(
                        "SELECT * FROM user_stats WHERE user_id = %s AND guild_id = %s",
                        (user_id, guild_id)
                    )
                    user_exists = await cursor.fetchone()
                    
                    if not user_exists:
                        # Create new user record
                        await cursor.execute(
                            """
                            INSERT INTO user_stats (user_id, guild_id, username, first_joined, last_seen)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (user_id, guild_id, username, now, now)
                        )
                    
                    # Update based on event type
                    if event_type == 'message':
                        await cursor.execute(
                            """
                            UPDATE user_stats 
                            SET message_count = message_count + 1, last_seen = %s
                            WHERE user_id = %s AND guild_id = %s
                            """,
                            (now, user_id, guild_id)
                        )
                        
                        # Log message
                        await cursor.execute(
                            """
                            INSERT INTO message_log (user_id, guild_id, channel_id, message_time, message_length)
                            VALUES (%s, %s, %s, %s, %s)
                            """,
                            (user_id, guild_id, kwargs.get('channel_id'), now, kwargs.get('message_length', 0))
                        )
                    
                    elif event_type == 'server_join':
                        await cursor.execute(
                            """
                            UPDATE user_stats
                            SET join_count = join_count + 1, last_seen = %s
                            WHERE user_id = %s AND guild_id = %s
                            """,
                            (now, user_id, guild_id)
                        )

                    elif event_type == 'voice_join':
                        # Create voice session
                        await cursor.execute(
                            """
                            INSERT INTO voice_sessions (user_id, guild_id, channel_id, join_time)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (user_id, guild_id, kwargs.get('channel_id'), now)
                        )

                    elif event_type == 'voice_leave':
                        # Update voice session
                        await cursor.execute(
                            """
                            SELECT id, join_time FROM voice_sessions 
                            WHERE user_id = %s AND guild_id = %s AND leave_time IS NULL
                            ORDER BY join_time DESC LIMIT 1
                            """,
                            (user_id, guild_id)
                        )
                        session = await cursor.fetchone()
                        
                        if session:
                            duration = int((now - session[1]).total_seconds())
                            
                            await cursor.execute(
                                """
                                UPDATE voice_sessions 
                                SET leave_time = %s, duration_seconds = %s
                                WHERE id = %s
                                """,
                                (now, duration, session[0])
                            )
                            
                            # Update total voice time
                            await cursor.execute(
                                """
                                UPDATE user_stats 
                                SET voice_time_seconds = voice_time_seconds + %s, last_seen = %s
                                WHERE user_id = %s AND guild_id = %s
                                """,
                                (duration, now, user_id, guild_id)
                            )
    
    @staticmethod
    async def get_user_stats(db, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Get user statistics"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                """
                SELECT * FROM user_stats 
                WHERE user_id = ? AND guild_id = ?
                """,
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            
            if row:
                return {
                    'user_id': row['user_id'],
                    'guild_id': row['guild_id'],
                    'username': row['username'],
                    'first_joined': row['first_joined'],
                    'last_seen': row['last_seen'],
                    'message_count': row['message_count'],
                    'voice_time_seconds': row['voice_time_seconds'],
                    'total_time_seconds': row['total_time_seconds'],
                    'join_count': row['join_count']
                }
        else:  # MySQL
            async with db.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM user_stats 
                        WHERE user_id = %s AND guild_id = %s
                        """,
                        (user_id, guild_id)
                    )
                    return await cursor.fetchone()
        
        return None
    
    @staticmethod
    async def search_user_by_name(db, username: str, guild_id: int) -> Optional[Dict[str, Any]]:
        """Search for a user by username in a specific guild"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                """
                SELECT * FROM user_stats 
                WHERE LOWER(username) LIKE ? AND guild_id = ?
                ORDER BY last_seen DESC
                LIMIT 1
                """,
                (f'%{username.lower()}%', guild_id)
            )
            row = await cursor.fetchone()
            
            if row:
                return {
                    'user_id': row['user_id'],
                    'guild_id': row['guild_id'],
                    'username': row['username'],
                    'first_joined': row['first_joined'],
                    'last_seen': row['last_seen'],
                    'message_count': row['message_count'],
                    'voice_time_seconds': row['voice_time_seconds'],
                    'total_time_seconds': row['total_time_seconds'],
                    'join_count': row['join_count']
                }
        else:  # MySQL
            async with db.pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cursor:
                    await cursor.execute(
                        """
                        SELECT * FROM user_stats 
                        WHERE LOWER(username) LIKE %s AND guild_id = %s
                        ORDER BY last_seen DESC
                        LIMIT 1
                        """,
                        (f'%{username.lower()}%', guild_id)
                    )
                    return await cursor.fetchone()

        return None

    @staticmethod
    async def get_main_channel(db, user_id: int, guild_id: int) -> Optional[int]:
        """Get the voice channel a user has spent the most time in"""
        query_sqlite = """
            SELECT channel_id, SUM(duration_seconds) as total
            FROM voice_sessions
            WHERE user_id = ? AND guild_id = ? AND leave_time IS NOT NULL
            GROUP BY channel_id
            ORDER BY total DESC
            LIMIT 1
        """
        query_mysql = query_sqlite.replace('?', '%s')

        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(query_sqlite, (user_id, guild_id))
            row = await cursor.fetchone()
            return row['channel_id'] if row else None
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_mysql, (user_id, guild_id))
                    row = await cursor.fetchone()
                    return row[0] if row else None

    @staticmethod
    async def get_avg_session(db, user_id: int, guild_id: int) -> Optional[float]:
        """Get the average voice session length (seconds) for a user"""
        query_sqlite = """
            SELECT AVG(duration_seconds) as avg_duration
            FROM voice_sessions
            WHERE user_id = ? AND guild_id = ? AND leave_time IS NOT NULL
        """
        query_mysql = query_sqlite.replace('?', '%s')

        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(query_sqlite, (user_id, guild_id))
            row = await cursor.fetchone()
            return row['avg_duration'] if row and row['avg_duration'] is not None else None
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(query_mysql, (user_id, guild_id))
                    row = await cursor.fetchone()
                    return row[0] if row and row[0] is not None else None

    @staticmethod
    async def get_top_companion(db, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Find the user this person has spent the most overlapping voice time with"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                """
                SELECT b.user_id AS companion_id,
                       SUM(
                           MAX(0,
                               (julianday(MIN(COALESCE(a.leave_time, CURRENT_TIMESTAMP), COALESCE(b.leave_time, CURRENT_TIMESTAMP)))
                                - julianday(MAX(a.join_time, b.join_time))) * 86400
                           )
                       ) AS total_overlap
                FROM voice_sessions a
                JOIN voice_sessions b
                    ON a.channel_id = b.channel_id AND a.guild_id = b.guild_id AND b.user_id != a.user_id
                WHERE a.user_id = ? AND a.guild_id = ?
                GROUP BY b.user_id
                ORDER BY total_overlap DESC
                LIMIT 1
                """,
                (user_id, guild_id)
            )
            row = await cursor.fetchone()
            if row and row['total_overlap']:
                return {'user_id': row['companion_id'], 'overlap_seconds': int(row['total_overlap'])}
            return None
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT b.user_id AS companion_id,
                               SUM(
                                   GREATEST(0,
                                       TIMESTAMPDIFF(SECOND,
                                           GREATEST(a.join_time, b.join_time),
                                           LEAST(COALESCE(a.leave_time, NOW()), COALESCE(b.leave_time, NOW()))
                                       )
                                   )
                               ) AS total_overlap
                        FROM voice_sessions a
                        JOIN voice_sessions b
                            ON a.channel_id = b.channel_id AND a.guild_id = b.guild_id AND b.user_id != a.user_id
                        WHERE a.user_id = %s AND a.guild_id = %s
                        GROUP BY b.user_id
                        ORDER BY total_overlap DESC
                        LIMIT 1
                        """,
                        (user_id, guild_id)
                    )
                    row = await cursor.fetchone()
                    if row and row[1]:
                        return {'user_id': row[0], 'overlap_seconds': int(row[1])}
                    return None

    @staticmethod
    async def get_longest_session_leaderboard(db, guild_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Top-Nutzer nach der längsten einzelnen (zusammenhängenden) Sprachkanal-Session,
        im Gegensatz zu user_stats.voice_time_seconds (das die kumulierte Gesamtzeit ist)"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                """
                SELECT v.user_id AS user_id,
                       COALESCE(u.username, 'Unbekannt') AS username,
                       MAX(v.duration_seconds) AS max_session
                FROM voice_sessions v
                LEFT JOIN user_stats u ON u.user_id = v.user_id AND u.guild_id = v.guild_id
                WHERE v.guild_id = ? AND v.leave_time IS NOT NULL
                GROUP BY v.user_id
                ORDER BY max_session DESC
                LIMIT ?
                """,
                (guild_id, limit)
            )
            rows = await cursor.fetchall()
            return [{'user_id': row['user_id'], 'username': row['username'], 'value': row['max_session']} for row in rows]
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        SELECT v.user_id AS user_id,
                               COALESCE(u.username, 'Unbekannt') AS username,
                               MAX(v.duration_seconds) AS max_session
                        FROM voice_sessions v
                        LEFT JOIN user_stats u ON u.user_id = v.user_id AND u.guild_id = v.guild_id
                        WHERE v.guild_id = %s AND v.leave_time IS NOT NULL
                        GROUP BY v.user_id
                        ORDER BY max_session DESC
                        LIMIT %s
                        """,
                        (guild_id, limit)
                    )
                    rows = await cursor.fetchall()
                    return [{'user_id': row[0], 'username': row[1], 'value': row[2]} for row in rows]

    @staticmethod
    async def get_guild_settings(db, guild_id: int) -> Dict[str, Any]:
        """Get announce settings for a guild (defaults if no row exists yet)"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                "SELECT announce_channel_id, announce_enabled FROM guild_settings WHERE guild_id = ?",
                (guild_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {'announce_channel_id': row['announce_channel_id'], 'announce_enabled': bool(row['announce_enabled'])}
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT announce_channel_id, announce_enabled FROM guild_settings WHERE guild_id = %s",
                        (guild_id,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        return {'announce_channel_id': row[0], 'announce_enabled': bool(row[1])}

        return {'announce_channel_id': None, 'announce_enabled': None}

    @staticmethod
    async def set_guild_setting(db, guild_id: int, **fields):
        """Create/update a guild_settings row, updating only the given keyword fields
        (allowed: announce_channel_id, announce_enabled)"""
        allowed = {'announce_channel_id', 'announce_enabled'}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return

        if db.db_type == 'sqlite':
            await db.connection.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
            )
            set_clause = ", ".join(f"{key} = ?" for key in updates)
            await db.connection.execute(
                f"UPDATE guild_settings SET {set_clause} WHERE guild_id = ?",
                (*updates.values(), guild_id)
            )
            await db.connection.commit()
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "INSERT IGNORE INTO guild_settings (guild_id) VALUES (%s)", (guild_id,)
                    )
                    set_clause = ", ".join(f"{key} = %s" for key in updates)
                    await cursor.execute(
                        f"UPDATE guild_settings SET {set_clause} WHERE guild_id = %s",
                        (*updates.values(), guild_id)
                    )

    @staticmethod
    async def upsert_oauth_link(db, user_id: int, access_token: str, refresh_token: str,
                                 expires_at: datetime, scope: str):
        """Store or replace a user's OAuth2 link"""
        if db.db_type == 'sqlite':
            await db.connection.execute(
                """
                INSERT INTO oauth_links (user_id, access_token, refresh_token, expires_at, scope)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    access_token = excluded.access_token,
                    refresh_token = excluded.refresh_token,
                    expires_at = excluded.expires_at,
                    scope = excluded.scope
                """,
                (user_id, access_token, refresh_token, expires_at, scope)
            )
            await db.connection.commit()
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        """
                        INSERT INTO oauth_links (user_id, access_token, refresh_token, expires_at, scope)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            access_token = VALUES(access_token),
                            refresh_token = VALUES(refresh_token),
                            expires_at = VALUES(expires_at),
                            scope = VALUES(scope)
                        """,
                        (user_id, access_token, refresh_token, expires_at, scope)
                    )

    @staticmethod
    async def get_oauth_link(db, user_id: int) -> Optional[Dict[str, Any]]:
        """Get a user's stored OAuth2 tokens, if linked"""
        if db.db_type == 'sqlite':
            cursor = await db.connection.execute(
                "SELECT access_token, refresh_token, expires_at, scope FROM oauth_links WHERE user_id = ?",
                (user_id,)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    'access_token': row['access_token'],
                    'refresh_token': row['refresh_token'],
                    'expires_at': row['expires_at'],
                    'scope': row['scope']
                }
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute(
                        "SELECT access_token, refresh_token, expires_at, scope FROM oauth_links WHERE user_id = %s",
                        (user_id,)
                    )
                    row = await cursor.fetchone()
                    if row:
                        return {
                            'access_token': row[0],
                            'refresh_token': row[1],
                            'expires_at': row[2],
                            'scope': row[3]
                        }

        return None

    @staticmethod
    async def delete_oauth_link(db, user_id: int):
        """Remove a user's stored OAuth2 link"""
        if db.db_type == 'sqlite':
            await db.connection.execute("DELETE FROM oauth_links WHERE user_id = ?", (user_id,))
            await db.connection.commit()
        else:
            async with db.pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    await cursor.execute("DELETE FROM oauth_links WHERE user_id = %s", (user_id,))
