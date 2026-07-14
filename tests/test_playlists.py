import unittest
from utils.database import Database
from cogs.playlists import Playlists
from types import SimpleNamespace

GUILD_ID = 1000
USER_A = 111
USER_B = 222

def make_test_config():
    return {
        'database': {
            'type': 'sqlite',
            'local': True,
            'sqlite_path': ':memory:',
        }
    }

class TestPlaylistsCog(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = Database(make_test_config())
        await self.db.initialize()
        
        self.bot = SimpleNamespace(db=self.db, config={
            'features': {
                'playlists': {
                    'max_playlists_per_user': 5
                }
            }
        })
        self.cog = Playlists(self.bot)
        await self.cog.cog_load()

    async def asyncTearDown(self):
        if self.db.connection:
            await self.db.connection.close()

    async def test_create_and_get_playlists(self):
        # Create playlist
        success = await self.cog.create_playlist(USER_A, GUILD_ID, "My Favs", "Some description")
        self.assertTrue(success)

        # Get playlist
        playlist = await self.cog.get_playlist(USER_A, GUILD_ID, "My Favs")
        self.assertIsNotNone(playlist)
        self.assertEqual(playlist['name'], "My Favs")
        self.assertEqual(playlist['description'], "Some description")
        self.assertFalse(playlist['is_public'])

        # Get user playlists
        user_playlists = await self.cog.get_user_playlists(USER_A, GUILD_ID)
        self.assertEqual(len(user_playlists), 1)
        self.assertEqual(user_playlists[0]['name'], "My Favs")

    async def test_add_and_remove_songs_from_playlist(self):
        await self.cog.create_playlist(USER_A, GUILD_ID, "My Favs")
        playlist = await self.cog.get_playlist(USER_A, GUILD_ID, "My Favs")
        playlist_id = playlist['id']

        # Add songs
        success1 = await self.cog.add_song_to_playlist(playlist_id, "Song A", "https://youtube.com/a", 180)
        success2 = await self.cog.add_song_to_playlist(playlist_id, "Song B", "https://youtube.com/b", 200)
        self.assertTrue(success1)
        self.assertTrue(success2)

        songs = await self.cog.get_playlist_songs(playlist_id)
        self.assertEqual(len(songs), 2)
        self.assertEqual(songs[0]['title'], "Song A")
        self.assertEqual(songs[0]['position'], 1)
        self.assertEqual(songs[1]['title'], "Song B")
        self.assertEqual(songs[1]['position'], 2)

        # Remove first song
        remove_success = await self.cog.remove_song_from_playlist(playlist_id, 1)
        self.assertTrue(remove_success)

        # Check remaining song has been re-indexed to position 1
        songs = await self.cog.get_playlist_songs(playlist_id)
        self.assertEqual(len(songs), 1)
        self.assertEqual(songs[0]['title'], "Song B")
        self.assertEqual(songs[0]['position'], 1)

    async def test_toggle_public_and_search(self):
        await self.cog.create_playlist(USER_A, GUILD_ID, "Shared List", "Cool party tunes")
        playlist = await self.cog.get_playlist(USER_A, GUILD_ID, "Shared List")
        playlist_id = playlist['id']

        # By default not public
        self.assertFalse(playlist['is_public'])

        # Toggle to public
        toggle_success = await self.cog.toggle_playlist_public(playlist_id, playlist['is_public'])
        self.assertTrue(toggle_success)

        playlist = await self.cog.get_playlist(USER_A, GUILD_ID, "Shared List")
        self.assertTrue(playlist['is_public'])

        # Search public playlists
        results = await self.cog.search_public_playlists(GUILD_ID, "party")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['name'], "Shared List")

        # Search non-matching query
        results = await self.cog.search_public_playlists(GUILD_ID, "sad")
        self.assertEqual(len(results), 0)

if __name__ == '__main__':
    unittest.main()
