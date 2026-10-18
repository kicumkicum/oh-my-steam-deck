import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).parents[1] / "bin/control-home-media/scripts/steam-gamepad-shortcut.py"
SPEC = importlib.util.spec_from_file_location("steam_gamepad_shortcut", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SteamGamepadShortcutTests(unittest.TestCase):
    def test_xbox_button_order_does_not_include_analog_triggers(self):
        self.assertNotIn(MODULE.BTN_TL2, MODULE.SUPPORTED_KEYS)
        self.assertNotIn(MODULE.BTN_TR2, MODULE.SUPPORTED_KEYS)
        self.assertEqual(MODULE.SUPPORTED_KEYS.index(MODULE.BTN_MODE), 8)
        self.assertEqual(MODULE.SUPPORTED_KEYS.index(MODULE.BTN_THUMBR), 10)

    def test_guide_is_a_key_action(self):
        self.assertEqual(
            MODULE.parse_shortcut("home", profile="xbox360"),
            [(MODULE.EV_KEY, MODULE.BTN_MODE, 1, 0)],
        )

    def test_triggers_are_analog_axes(self):
        self.assertEqual(
            MODULE.parse_shortcut("lt+rt", profile="xbox360"),
            [
                (MODULE.EV_ABS, MODULE.ABS_Z, 255, 0),
                (MODULE.EV_ABS, MODULE.ABS_RZ, 255, 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
