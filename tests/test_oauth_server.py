import time
import unittest
from types import SimpleNamespace

from utils.oauth_server import create_state, _pop_valid_state, STATE_TTL_SECONDS


def make_fake_bot():
    return SimpleNamespace(oauth_states={})


class TestOAuthStateCSRFProtection(unittest.TestCase):
    """!connect bindet den OAuth-Callback per 'state' an genau den Discord-User, der den Befehl
    ausgeführt hat - diese Tests stellen sicher, dass ein state weder erraten noch zweimal
    verwendet werden kann (Replay) und nach Ablauf nicht mehr akzeptiert wird."""

    def test_state_resolves_to_the_correct_user(self):
        bot = make_fake_bot()
        state = create_state(bot, user_id=42)
        self.assertEqual(_pop_valid_state(bot, state), 42)

    def test_state_can_only_be_used_once(self):
        bot = make_fake_bot()
        state = create_state(bot, user_id=42)
        self.assertEqual(_pop_valid_state(bot, state), 42)
        # Zweite Verwendung desselben Links (z.B. abgefangen/weitergeleitet) muss fehlschlagen
        self.assertIsNone(_pop_valid_state(bot, state))

    def test_unknown_state_is_rejected(self):
        bot = make_fake_bot()
        self.assertIsNone(_pop_valid_state(bot, "not-a-real-state"))

    def test_expired_state_is_rejected(self):
        bot = make_fake_bot()
        state = create_state(bot, user_id=42)
        # Manuell in die Vergangenheit verschieben, um den TTL-Ablauf zu simulieren
        user_id, _ = bot.oauth_states[state]
        bot.oauth_states[state] = (user_id, time.time() - STATE_TTL_SECONDS - 1)
        self.assertIsNone(_pop_valid_state(bot, state))

    def test_states_are_unique_and_not_guessable_short(self):
        bot = make_fake_bot()
        states = {create_state(bot, user_id=1) for _ in range(50)}
        self.assertEqual(len(states), 50)
        self.assertTrue(all(len(s) >= 24 for s in states))


if __name__ == '__main__':
    unittest.main()
