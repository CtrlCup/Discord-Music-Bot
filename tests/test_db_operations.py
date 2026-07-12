import unittest
from datetime import datetime, timedelta

from utils.database import Database
from utils.db_operations import DatabaseOperations

GUILD_ID = 1000
USER_A = 111
USER_B = 222
CHANNEL_ID = 555


def make_test_config():
    return {
        'database': {
            'type': 'sqlite',
            'local': True,
            'sqlite_path': ':memory:',
        }
    }


class TestDatabaseOperations(unittest.IsolatedAsyncioTestCase):
    """Exercises the actual SQL (against a real in-memory SQLite DB) behind the
    security/stats-critical DatabaseOperations helpers - catches SQL syntax errors
    and logic bugs that a mock could hide."""

    async def asyncSetUp(self):
        self.db = Database(make_test_config())
        await self.db.initialize()

    async def asyncTearDown(self):
        await self.db.connection.close()

    async def test_join_count_increments_on_each_server_join_event(self):
        await DatabaseOperations.update_user_stats(
            self.db, USER_A, GUILD_ID, "Alex", 'server_join'
        )
        await DatabaseOperations.update_user_stats(
            self.db, USER_A, GUILD_ID, "Alex", 'server_join'
        )
        stats = await DatabaseOperations.get_user_stats(self.db, USER_A, GUILD_ID)
        self.assertEqual(stats['join_count'], 2)

    async def test_message_count_increments(self):
        await DatabaseOperations.update_user_stats(
            self.db, USER_A, GUILD_ID, "Alex", 'message', channel_id=CHANNEL_ID, message_length=10
        )
        await DatabaseOperations.update_user_stats(
            self.db, USER_A, GUILD_ID, "Alex", 'message', channel_id=CHANNEL_ID, message_length=5
        )
        stats = await DatabaseOperations.get_user_stats(self.db, USER_A, GUILD_ID)
        self.assertEqual(stats['message_count'], 2)

    async def test_guild_settings_defaults_then_upsert(self):
        defaults = await DatabaseOperations.get_guild_settings(self.db, GUILD_ID)
        self.assertIsNone(defaults['announce_channel_id'])
        self.assertIsNone(defaults['announce_enabled'])

        await DatabaseOperations.set_guild_setting(self.db, GUILD_ID, announce_channel_id=CHANNEL_ID)
        await DatabaseOperations.set_guild_setting(self.db, GUILD_ID, announce_enabled=False)

        updated = await DatabaseOperations.get_guild_settings(self.db, GUILD_ID)
        self.assertEqual(updated['announce_channel_id'], CHANNEL_ID)
        self.assertFalse(updated['announce_enabled'])

    async def test_oauth_link_roundtrip_and_delete(self):
        expires_at = datetime.utcnow() + timedelta(days=7)
        await DatabaseOperations.upsert_oauth_link(
            self.db, USER_A, "access-token-1", "refresh-token-1", expires_at, "identify email"
        )
        link = await DatabaseOperations.get_oauth_link(self.db, USER_A)
        self.assertEqual(link['access_token'], "access-token-1")
        self.assertEqual(link['refresh_token'], "refresh-token-1")

        # Re-linking (e.g. token refresh) must replace, not duplicate
        await DatabaseOperations.upsert_oauth_link(
            self.db, USER_A, "access-token-2", "refresh-token-2", expires_at, "identify email"
        )
        link = await DatabaseOperations.get_oauth_link(self.db, USER_A)
        self.assertEqual(link['access_token'], "access-token-2")

        await DatabaseOperations.delete_oauth_link(self.db, USER_A)
        self.assertIsNone(await DatabaseOperations.get_oauth_link(self.db, USER_A))

    async def _insert_voice_session(self, user_id, channel_id, join_time, leave_time):
        duration = int((leave_time - join_time).total_seconds())
        await self.db.connection.execute(
            """
            INSERT INTO voice_sessions (user_id, guild_id, channel_id, join_time, leave_time, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, GUILD_ID, channel_id, join_time, leave_time, duration)
        )
        await self.db.connection.commit()

    async def test_main_channel_and_avg_session(self):
        base = datetime.utcnow()
        # User A: 10 min in channel 555, then 30 min in channel 999 -> main channel should be 999
        await self._insert_voice_session(USER_A, CHANNEL_ID, base, base + timedelta(minutes=10))
        await self._insert_voice_session(USER_A, 999, base, base + timedelta(minutes=30))

        main_channel = await DatabaseOperations.get_main_channel(self.db, USER_A, GUILD_ID)
        self.assertEqual(main_channel, 999)

        avg_session = await DatabaseOperations.get_avg_session(self.db, USER_A, GUILD_ID)
        self.assertAlmostEqual(avg_session, (600 + 1800) / 2, delta=1)

    async def test_top_companion_overlap(self):
        base = datetime.utcnow()
        # A and B are both in CHANNEL_ID from base to base+10min (fully overlapping)
        await self._insert_voice_session(USER_A, CHANNEL_ID, base, base + timedelta(minutes=10))
        await self._insert_voice_session(USER_B, CHANNEL_ID, base, base + timedelta(minutes=10))

        companion = await DatabaseOperations.get_top_companion(self.db, GUILD_ID, USER_A)
        self.assertIsNotNone(companion)
        self.assertEqual(companion['user_id'], USER_B)
        self.assertAlmostEqual(companion['overlap_seconds'], 600, delta=2)

    async def test_top_companion_none_when_never_together(self):
        base = datetime.utcnow()
        await self._insert_voice_session(USER_A, CHANNEL_ID, base, base + timedelta(minutes=10))
        companion = await DatabaseOperations.get_top_companion(self.db, GUILD_ID, USER_A)
        self.assertIsNone(companion)

    async def test_longest_session_leaderboard_picks_max_single_session(self):
        base = datetime.utcnow()
        # User A: two short sessions (5 min each) -> max should be 300s, not the 600s sum
        await self._insert_voice_session(USER_A, CHANNEL_ID, base, base + timedelta(minutes=5))
        await self._insert_voice_session(USER_A, CHANNEL_ID, base, base + timedelta(minutes=5))
        # User B: one long session (20 min) -> should rank first
        await self._insert_voice_session(USER_B, CHANNEL_ID, base, base + timedelta(minutes=20))

        rows = await DatabaseOperations.get_longest_session_leaderboard(self.db, GUILD_ID)
        self.assertEqual(rows[0]['user_id'], USER_B)
        self.assertAlmostEqual(rows[0]['value'], 1200, delta=2)

        user_a_row = next(r for r in rows if r['user_id'] == USER_A)
        self.assertAlmostEqual(user_a_row['value'], 300, delta=2)


if __name__ == '__main__':
    unittest.main()
