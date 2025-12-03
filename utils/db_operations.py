from datetime import datetime
from typing import Optional, Dict, Any

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
                    'total_time_seconds': row['total_time_seconds']
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
                    'total_time_seconds': row['total_time_seconds']
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
