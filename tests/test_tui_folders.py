"""Unit and pilot tests for hierarchical namespaces/folders in TUI token browser."""

import unittest

from textual.app import App
from textual.widgets import OptionList

from authy_local.tui import (
    FolderSelectModal,
    TokenBrowserScreen,
    extract_folder,
)


class TestFolderExtraction(unittest.TestCase):
    def test_extract_folder_pass_otp(self):
        self.assertEqual(extract_folder("pass-otp", "work/aws/admin", "work/aws/admin"), "work/aws")
        self.assertEqual(
            extract_folder("pass-otp", "personal/github", "personal/github"), "personal"
        )
        self.assertEqual(extract_folder("pass-otp", "standalone", "standalone"), "(root)")

    def test_extract_folder_totpm(self):
        self.assertEqual(extract_folder("totpm", "aws:alice", "aws:alice"), "aws")
        self.assertEqual(
            extract_folder("totpm", "google:bob@gmail.com", "google:bob@gmail.com"), "google"
        )
        self.assertEqual(extract_folder("totpm", "plain", "plain"), "(root)")

    def test_extract_folder_onepassword(self):
        self.assertEqual(
            extract_folder("onepassword", "a" * 26, "Work/AWS/Production [abcdef12]"),
            "Work/AWS",
        )
        self.assertEqual(
            extract_folder("onepassword", "a" * 26, "Personal/GitHub [abcdef12]"),
            "Personal",
        )
        self.assertEqual(
            extract_folder("onepassword", "a" * 26, "Simple Login [abcdef12]"),
            "(root)",
        )


class TestFolderSelectModal(unittest.IsolatedAsyncioTestCase):
    async def test_folder_select_modal_composition_and_selection(self):
        counts = {"work": 5, "personal": 3, "(root)": 2}
        app = App()
        async with app.run_test() as pilot:
            modal = FolderSelectModal(counts, active_folder="work")
            await app.push_screen(modal)
            await pilot.pause()

            opt_list = modal.query_one("#folder-option-list", OptionList)
            self.assertEqual(opt_list.option_count, 4)  # All items + 3 folders

            # Test dismiss with selection
            modal.action_select_folder()
            await pilot.pause()


class TestTokenBrowserFolderFiltering(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.records = [
            ("work/aws", "work/aws [11111111]"),
            ("work/github", "work/github [22222222]"),
            ("personal/email", "personal/email [33333333]"),
            ("root_entry", "root_entry [44444444]"),
        ]

    async def test_browser_filters_by_folder_and_resets(self):
        app = App()
        screen = TokenBrowserScreen(
            backend="pass-otp",
            profile={"store": "/store", "key_home": "/keys"},
            records=self.records,
        )

        async with app.run_test() as pilot:
            await app.push_screen(screen)
            await pilot.pause()

            # Initially all 4 items present
            self.assertEqual(len(screen._get_folder_records()), 4)

            # Set folder filter
            screen.active_folder = "work"
            screen._apply_search("")
            await pilot.pause()

            self.assertEqual(len(screen._get_folder_records()), 2)
            self.assertIn("Folder:", screen._format_subtitle())
            self.assertIn("work", screen._format_subtitle())

            # Esc clears folder filter when input is empty
            screen.action_handle_escape()
            await pilot.pause()

            self.assertIsNone(screen.active_folder)
            self.assertEqual(len(screen._get_folder_records()), 4)
