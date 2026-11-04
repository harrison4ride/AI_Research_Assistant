"""The test setup itself: every piece of the app's module-level state is reset between tests."""

from support import app_state


def test_all_module_level_state_of_the_app_is_reset_between_tests():
    # A new cache, lock, or cooldown in app/ must be added to support/app_state.py,
    # or it would carry over from one test to the next.
    assert app_state.state_in_the_app() == app_state.reset_names()
