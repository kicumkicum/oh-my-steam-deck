import importlib.util
import pathlib
import sys
import unittest


SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "bin"
    / "control-home-media"
    / "scripts"
    / "cec-input-color-buttons.py"
)
SPEC = importlib.util.spec_from_file_location("cec_input_color_buttons", SCRIPT)
LISTENER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = LISTENER
SPEC.loader.exec_module(LISTENER)


class FakeKeyboard:
    def __init__(self):
        self.events = []

    def forward(self, event_type, code, value):
        self.events.append((event_type, code, value))


class CecKeyboardRemapTests(unittest.TestCase):
    def test_ok_and_back_keep_press_and_release_events(self):
        keyboard = FakeKeyboard()
        remaps = {
            LISTENER.KEY_OK: LISTENER.KEY_ENTER,
            LISTENER.KEY_EXIT: LISTENER.KEY_ESC,
        }

        for source in (LISTENER.KEY_OK, LISTENER.KEY_EXIT):
            for value in (1, 0):
                command = LISTENER.route_input_event(
                    LISTENER.EV_KEY,
                    source,
                    value,
                    {},
                    remaps,
                    keyboard,
                )
                self.assertIsNone(command)

        self.assertEqual(
            keyboard.events,
            [
                (LISTENER.EV_KEY, LISTENER.KEY_ENTER, 1),
                (LISTENER.EV_KEY, LISTENER.KEY_ENTER, 0),
                (LISTENER.EV_KEY, LISTENER.KEY_ESC, 1),
                (LISTENER.EV_KEY, LISTENER.KEY_ESC, 0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
