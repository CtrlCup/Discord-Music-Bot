import unittest

from cogs.settings import Settings


class TestSettingsPermissionGates(unittest.TestCase):
    """!settings ändert server-weite Konfiguration (u.a. wohin Songwechsel-Ankündigungen
    gehen) und darf daher nur von Mitgliedern mit 'Server verwalten' ausgeführt werden.
    Diese Tests stellen sicher, dass jeder Subcommand tatsächlich einen Permission-Check
    registriert hat - eine versehentlich entfernte @has_permissions-Zeile fällt hier auf."""

    def _assert_has_permission_check(self, command):
        self.assertTrue(
            len(command.checks) >= 1,
            f"Command '{command.qualified_name}' hat keinen Permission-Check registriert!"
        )

    def test_settings_group_default_is_gated(self):
        self._assert_has_permission_check(Settings.settings)

    def test_settings_show_is_gated(self):
        self._assert_has_permission_check(Settings.show)

    def test_settings_announce_is_gated(self):
        self._assert_has_permission_check(Settings.announce)

    def test_settings_announce_toggle_is_gated(self):
        self._assert_has_permission_check(Settings.announce_toggle)


if __name__ == '__main__':
    unittest.main()
