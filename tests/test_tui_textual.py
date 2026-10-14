"""Unit and integration tests for modern Textual TUI foundation."""

import unittest
from collections.abc import Callable
from unittest.mock import patch

from textual import events
from textual.geometry import Size

from authy_local.errors import MESSAGES, AppError
from authy_local.tui import (
    ACTIONS,
    ActionListView,
    AuthyApp,
    Capture,
    DashboardScreen,
    DetailWorkspace,
    HeaderBar,
    KeyboardFooter,
    MinSizeWarning,
    SessionStatusPanel,
    run,
)


class TestTextualTuiFoundation(unittest.IsolatedAsyncioTestCase):
    """Test suite covering Textual components, layout, reactivity, and execution bridge."""

    def setUp(self) -> None:
        self.dummy_dispatch: Callable = lambda args, out, diag: 0
        self.dummy_preview: Callable = lambda wheel, out, diag: 0
        self.profiles = {"onepassword": {"account": "acc1", "vault": "v1"}}

    async def test_app_initialization_and_metadata(self) -> None:
        """Verify AuthyApp metadata, title, and initial reactive properties."""
        app = AuthyApp(
            dispatch=self.dummy_dispatch,
            preview=self.dummy_preview,
            profiles=self.profiles,
        )
        self.assertEqual(app.TITLE, "Authy Local")
        self.assertEqual(app.SUB_TITLE, "PRIVATE OTP CONSOLE")
        self.assertIn("dashboard", app.SCREENS)
        self.assertEqual(app.current_backend, "onepassword")
        self.assertEqual(app.session_status, "Local capabilities not checked")
        self.assertEqual(app.profiles, self.profiles)

    async def test_widget_composition_and_defaults(self) -> None:
        """Verify declarative widget tree composition under DashboardScreen."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)

            header = screen.query_one(HeaderBar)
            self.assertIsInstance(header, HeaderBar)

            sidebar = screen.query_one(ActionListView)
            self.assertIsInstance(sidebar, ActionListView)
            self.assertEqual(sidebar.option_count, len(ACTIONS))

            workspace = screen.query_one(DetailWorkspace)
            self.assertIsInstance(workspace, DetailWorkspace)
            self.assertEqual(workspace.selected_index, 0)

            status_panel = screen.query_one(SessionStatusPanel)
            self.assertIsInstance(status_panel, SessionStatusPanel)

            footer = screen.query_one(KeyboardFooter)
            self.assertIsInstance(footer, KeyboardFooter)

            warning = screen.query_one(MinSizeWarning)
            self.assertIsInstance(warning, MinSizeWarning)

            await pilot.press("q")

    async def test_header_bar_reactive_backend_updates(self) -> None:
        """Verify HeaderBar updates label when current_backend changes."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            header = app.screen.query_one(HeaderBar)
            self.assertEqual(header.backend, "onepassword")

            app.current_backend = "pass-otp"
            await pilot.pause()
            self.assertEqual(header.backend, "pass-otp")

            app.current_backend = "totpm"
            await pilot.pause()
            self.assertEqual(header.backend, "totpm")

            await pilot.press("q")

    async def test_session_status_reactive_updates(self) -> None:
        """Verify SessionStatusPanel updates content when session_status changes."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            status_panel = app.screen.query_one(SessionStatusPanel)
            self.assertEqual(status_panel.status, "Local capabilities not checked")

            app.session_status = "Doctor: 5 available, 0 missing, 0 unknown"
            await pilot.pause()
            self.assertEqual(status_panel.status, "Doctor: 5 available, 0 missing, 0 unknown")

            await pilot.press("q")

    async def test_keyboard_navigation_updates_workspace_detail(self) -> None:
        """Verify pressing j and k updates sidebar cursor and workspace detail."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            workspace = app.screen.query_one(DetailWorkspace)
            sidebar = app.screen.query_one(ActionListView)

            self.assertEqual(workspace.selected_index, 0)
            self.assertEqual(sidebar.highlighted, 0)

            # Move cursor down via 'j'
            await pilot.press("j")
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 1)

            # Move cursor down via 'down'
            await pilot.press("down")
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 2)

            # Move cursor up via 'k'
            await pilot.press("k")
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 1)

            # Move cursor up via 'up'
            await pilot.press("up")
            await pilot.pause()
            self.assertEqual(workspace.selected_index, 0)

            await pilot.press("q")

    async def test_direct_numeric_keybindings(self) -> None:
        """Verify numeric keys 1-9 trigger corresponding actions."""
        actions_triggered = []
        app = AuthyApp(dispatch=self.dummy_dispatch)
        app.trigger_action = lambda num: actions_triggered.append(num)

        async with app.run_test() as pilot:
            for num in range(1, 10):
                await pilot.press(str(num))
            self.assertEqual(actions_triggered, list(range(1, 10)))
            await pilot.press("q")

    async def test_responsive_layout_classes_on_resize(self) -> None:
        """Verify on_resize assigns responsive CSS classes and compact sidebar."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            screen = app.screen
            sidebar = screen.query_one(ActionListView)

            # 1. Standard desktop dimensions (80x24)
            screen.on_resize(events.Resize(Size(80, 24), Size(80, 24)))
            self.assertFalse(screen.has_class("too-small"))
            self.assertFalse(screen.has_class("compact-width"))
            self.assertFalse(screen.has_class("compact-height"))
            self.assertFalse(sidebar.compact)

            # 2. Compact width dimensions (70x24)
            screen.on_resize(events.Resize(Size(70, 24), Size(80, 24)))
            self.assertFalse(screen.has_class("too-small"))
            self.assertTrue(screen.has_class("compact-width"))
            self.assertFalse(screen.has_class("compact-height"))
            self.assertTrue(sidebar.compact)

            # 3. Compact height dimensions (80x20)
            screen.on_resize(events.Resize(Size(80, 20), Size(80, 24)))
            self.assertFalse(screen.has_class("too-small"))
            self.assertFalse(screen.has_class("compact-width"))
            self.assertTrue(screen.has_class("compact-height"))

            # 4. Under minimum dimensions (<60x18)
            screen.on_resize(events.Resize(Size(55, 15), Size(80, 24)))
            self.assertTrue(screen.has_class("too-small"))

            await pilot.press("q")

    def test_capture_bounded_sink(self) -> None:
        """Verify Capture implements isatty and enforces bounded 128 KB ceiling."""
        sink = Capture()
        self.assertTrue(sink.isatty())

        # Write within ceiling
        sink.write("A" * 1024)
        self.assertEqual(sink.tell(), 1024)

        # Exceed ceiling (>131072)
        sink.seek(131070)
        with self.assertRaises(AppError) as ctx:
            sink.write("OVERFLOW")
        self.assertEqual(ctx.exception.exit_code, 5)

    def test_execute_doctor_probe_parsing_and_summary(self) -> None:
        """Verify execute parses doctor capabilities and computes summary."""

        def doctor_dispatch(args, output, diagnostic):
            output.write("platform: available\n")
            output.write("op: available\n")
            output.write("wl-copy: missing\n")
            output.write("clock: unknown\n")
            return 0

        app = AuthyApp(dispatch=doctor_dispatch)
        status, summary, lines = app.execute(["doctor"])
        self.assertEqual(status, 0)
        self.assertEqual(summary, "Doctor: 2 available, 1 missing, 1 unknown")
        self.assertEqual(app.session_status, summary)
        self.assertIn("platform: available", lines)
        self.assertIn("op: available", lines)
        self.assertIn("wl-copy: missing", lines)
        self.assertIn("clock: unknown", lines)

    def test_execute_doctor_failure_diagnostics(self) -> None:
        """Verify execute handles doctor failure code and sets retry summary."""

        def failing_doctor(args, output, diagnostic):
            output.write("platform: available\n")
            return 5

        app = AuthyApp(dispatch=failing_doctor)
        status, summary, lines = app.execute(["doctor"])
        self.assertEqual(status, 5)
        self.assertEqual(summary, "Doctor failed (exit 5); press 1 to retry")
        self.assertEqual(app.session_status, summary)

    def test_execute_show_code_success_and_invalid(self) -> None:
        """Verify execute parses valid OTP code and handles invalid parse."""

        def valid_code(args, output, diagnostic):
            output.write("123456\n")
            return 0

        app = AuthyApp(dispatch=valid_code)
        status, summary, lines = app.execute(["show", "item1"])
        self.assertEqual(status, 0)
        self.assertEqual(lines, ["Code", "123456"])

        def invalid_code(args, output, diagnostic):
            output.write("non_ascii_code_\xff\n")
            return 0

        app.dispatch_callback = invalid_code
        status_err, _, lines_err = app.execute(["show", "item1"])
        self.assertEqual(status_err, 5)
        self.assertEqual(lines_err, [MESSAGES[5]])

    def test_execute_preview_command(self) -> None:
        """Verify execute invokes preview_callback and formats banner."""

        def preview_cb(wheel, output, diagnostic):
            output.write("Create file A\nCreate file B\n")
            return 0

        app = AuthyApp(dispatch=self.dummy_dispatch, preview=preview_cb)
        status, _, lines = app.execute(["preview", "package.whl"])
        self.assertEqual(status, 0)
        self.assertEqual(lines[0], "Preview only; no changes authorized.")
        self.assertEqual(lines[1], "Create file A")
        self.assertEqual(lines[2], "Create file B")

    def test_execute_copy_completion(self) -> None:
        """Verify execute formats clipboard copy message."""

        def copy_dispatch(args, output, diagnostic):
            return 0

        app = AuthyApp(dispatch=copy_dispatch)
        status, _, lines = app.execute(["copy", "item1"])
        self.assertEqual(status, 0)
        self.assertTrue(lines[0].startswith("Copy completed."))

    def test_execute_error_codes(self) -> None:
        """Verify execute handles AppError, KeyboardInterrupt, and generic exceptions."""

        def error_dispatch(args, output, diagnostic):
            raise AppError(2)

        app = AuthyApp(dispatch=error_dispatch)
        status, _, lines = app.execute(["show", "item1"])
        self.assertEqual(status, 2)
        self.assertEqual(lines, [MESSAGES[2]])

        def interrupt_dispatch(args, output, diagnostic):
            raise KeyboardInterrupt()

        app = AuthyApp(dispatch=interrupt_dispatch)
        status, _, _ = app.execute(["show", "item1"])
        self.assertEqual(status, 130)

    def test_load_and_delete_records_bridges(self) -> None:
        """Verify load_records and delete_record helpers."""
        app = AuthyApp(dispatch=self.dummy_dispatch)

        with patch("authy_local.tui_items.records", return_value=[("k1", "Item 1")]):
            rows = app.load_records("onepassword", {})
            self.assertEqual(rows, [("k1", "Item 1")])

        with patch("authy_local.tui_items.records", side_effect=AppError(4)):
            self.assertIsNone(app.load_records("onepassword", {}))

        with patch("authy_local.tui_items.remove"):
            self.assertTrue(app.delete_record("pass-otp", {}, "entry1"))

        with patch("authy_local.tui_items.remove", side_effect=AppError(3)):
            self.assertFalse(app.delete_record("pass-otp", {}, "entry1"))

    def test_public_run_non_terminal_refusal(self) -> None:
        """Verify run() immediately returns 3 when terminal is False."""
        self.assertEqual(run(self.dummy_dispatch, terminal=False), 3)

    def test_public_run_app_error_propagation(self) -> None:
        """Verify run() lets AppError from profile loading propagate to caller."""
        with patch("authy_local.tui_profiles.load", side_effect=AppError(2)):
            with self.assertRaises(AppError) as ctx:
                run(self.dummy_dispatch)
            self.assertEqual(ctx.exception.exit_code, 2)

    async def test_dashboard_direct_numeric_hotkeys(self) -> None:
        """Verify direct numeric keys 1-9 invoke trigger_action on AuthyApp."""
        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            screen = app.screen
            self.assertIsInstance(screen, DashboardScreen)
            with patch.object(app, "trigger_action") as mock_trigger:
                for num in range(1, 10):
                    getattr(screen, f"action_action_{num}")()
                    mock_trigger.assert_called_with(num)
                for num in range(1, 10):
                    getattr(screen, f"action_{num}")()
                    mock_trigger.assert_called_with(num)
                screen.action_add_otp()
                mock_trigger.assert_called_with(5)
            await pilot.press("q")

    async def test_code_display_modal_refresh_none_and_copy_branches(self) -> None:
        """Verify CodeDisplayModal branches when refresh_callback is None or code is empty/expired."""
        from authy_local.tui import CodeDisplayModal

        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            modal = CodeDisplayModal("123456", "TestItem", refresh_callback=None)
            await app.push_screen(modal)
            await pilot.pause()

            modal.action_refresh_code_action()

            modal.code = ""
            modal.action_copy_code_action()

            modal.code = "123456"
            modal._is_expired = True
            with patch("authy_local.interaction.copy_code"):
                modal.action_copy_code_action()

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_token_browser_show_and_copy_branches(self) -> None:
        """Verify TokenBrowserScreen show and copy branches on empty, success, and error paths."""
        from authy_local.tui import TokenBrowserScreen

        app = AuthyApp(dispatch=self.dummy_dispatch, profiles={"onepassword": {}})
        async with app.run_test() as pilot:
            browser = TokenBrowserScreen(
                backend="onepassword",
                profile={},
                records=[("k1", "Item 1"), ("k2", "Item 2")],
                default_action="show",
            )
            await app.push_screen(browser)
            await pilot.pause()

            # Empty highlighted item
            with patch.object(browser, "_get_highlighted_item", return_value=None):
                browser.action_select_show()
                browser.action_select_copy()

            # Error status when showing
            with patch.object(app, "execute", return_value=(3, "err", ["Failed to retrieve"])):
                browser.action_select_show()
                await pilot.pause()
                await pilot.press("escape")

            # Error status when copying
            with patch.object(app, "execute", return_value=(3, "err", ["Failed to copy"])):
                browser.action_select_copy()
                await pilot.pause()
                await pilot.press("escape")

            # Success copy fallback without notify_copy
            with patch.object(app, "execute", return_value=(0, "ok", ["001234"])):
                browser.action_select_copy()
                await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("q")

    async def test_modal_buttons_and_scrolling_branches(self) -> None:
        """Verify button handlers and scrolling methods on modals."""
        from textual.widgets import Input

        from authy_local.tui import (
            BackendSelectModal,
            DeleteConfirmModal,
            DoctorModal,
            HelpModal,
            InstallPreviewModal,
            MessageModal,
            PromptItemModal,
            SavedScopeModal,
            WheelPathModal,
        )

        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            # 1. WheelPathModal
            wp_modal = WheelPathModal()
            await app.push_screen(wp_modal)
            await pilot.pause()
            wp_modal.query_one("#wheel-path-input", Input).value = "test.whl"
            wp_modal.on_submit_pressed()
            await pilot.pause()

            wp_modal2 = WheelPathModal()
            await app.push_screen(wp_modal2)
            await pilot.pause()
            wp_modal2.on_cancel_pressed()
            await pilot.pause()

            # 2. InstallPreviewModal
            prev_modal = InstallPreviewModal(initial_path="test.whl")
            await app.push_screen(prev_modal)
            await pilot.pause()
            prev_modal.on_run_preview_pressed()
            prev_modal.on_close_pressed()
            await pilot.pause()

            # 3. HelpModal
            help_modal = HelpModal()
            await app.push_screen(help_modal)
            await pilot.pause()
            help_modal.action_scroll_down()
            help_modal.action_scroll_up()
            help_modal.action_scroll_page_down()
            help_modal.action_scroll_page_up()
            help_modal.on_close_pressed()
            await pilot.pause()

            # 4. DoctorModal close & copy buttons
            doc_modal = DoctorModal(states={"op": "available"})
            await app.push_screen(doc_modal)
            await pilot.pause()
            with patch("authy_local.interaction.copy_code"):
                doc_modal.on_copy_pressed()
            doc_modal.on_close_pressed()
            await pilot.pause()

            # 5. DeleteConfirmModal cancel button
            del_modal = DeleteConfirmModal(label="Item", backend="pass-otp")
            await app.push_screen(del_modal)
            await pilot.pause()
            del_modal.on_cancel_pressed()
            await pilot.pause()

            # 6. PromptItemModal cancel button
            prompt_modal = PromptItemModal(backend="onepassword", profile={})
            await app.push_screen(prompt_modal)
            await pilot.pause()
            prompt_modal.on_cancel_pressed()
            await pilot.pause()

            # 7. SavedScopeModal cancel button
            scope_modal = SavedScopeModal(backend="onepassword")
            await app.push_screen(scope_modal)
            await pilot.pause()
            scope_modal.on_cancel_pressed()
            await pilot.pause()

            # 8. BackendSelectModal cancel button
            be_modal = BackendSelectModal(current_backend="onepassword")
            await app.push_screen(be_modal)
            await pilot.pause()
            be_modal.on_cancel_pressed()
            await pilot.pause()

            # 9. MessageModal close button
            msg_modal = MessageModal("Notice", ["Content"])
            await app.push_screen(msg_modal)
            await pilot.pause()
            msg_modal.on_dismiss_pressed()
            await pilot.pause()

            await pilot.press("q")

    async def test_federated_browse_and_saved_scope_no_validation_error(self) -> None:
        """Verify federated, bitwarden, and keepass backends open browser directly and dismiss SavedScopeModal cleanly."""
        from authy_local.tui import SavedScopeModal, TokenBrowserScreen

        app = AuthyApp(dispatch=self.dummy_dispatch)
        async with app.run_test() as pilot:
            app.current_backend = "federated"
            await pilot.pause()

            # Saved scope ('p') for federated should dismiss cleanly on Enter/Save without validation failure
            await pilot.press("p")
            await pilot.pause()
            self.assertIsInstance(app.screen, SavedScopeModal)
            app.screen.on_save_pressed()
            await pilot.pause()
            self.assertIsInstance(app.screen, DashboardScreen)

            # Browse and show ('1') for federated should open TokenBrowserScreen directly without SavedScopeModal
            with patch.object(app, "aload_records", return_value=[("item1", "GitHub [BW]")]):
                await pilot.press("1")
                await pilot.pause()
                self.assertIsInstance(app.screen, TokenBrowserScreen)
                await pilot.press("escape")
                await pilot.pause()

            await pilot.press("q")
