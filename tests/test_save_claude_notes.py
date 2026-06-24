import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import save_claude_notes as notes


class PathEncodingTests(unittest.TestCase):
    def test_encodes_windows_drive_path(self):
        self.assertEqual(notes.encode_project_path("D:/xiao/WuKong"), "D--xiao-WuKong")

    def test_encodes_git_bash_drive_path(self):
        self.assertEqual(notes.encode_project_path("/d/xiao/WuKong"), "D--xiao-WuKong")

    def test_encodes_unix_absolute_path_with_leading_dash(self):
        self.assertEqual(notes.encode_project_path("/tmp/project"), "-tmp-project")

    def test_expand_user_path_expands_home_prefix(self):
        self.assertEqual(
            notes.expand_user_path("~/claude-notes", home="/home/example"),
            "/home/example/claude-notes",
        )

    def test_home_environment_overrides_platform_home_for_shell_compatibility(self):
        with unittest.mock.patch.dict(os.environ, {"HOME": "/tmp/save-notes-home"}):
            self.assertEqual(notes.expand_user_path("~/claude-notes"), "/tmp/save-notes-home/claude-notes")

    def test_normalizes_git_bash_drive_path_for_windows_python(self):
        self.assertEqual(
            notes.normalize_windows_shell_path("/c/Users/example/notes", force=True),
            "C:/Users/example/notes",
        )

    def test_decodes_stdin_bytes_as_utf8(self):
        self.assertEqual(notes.decode_stdin_bytes("请优化保存格式".encode("utf-8")), "请优化保存格式")


class TranscriptExtractionTests(unittest.TestCase):
    def test_extracts_latest_non_meta_user_assistant_pair(self):
        records = [
            {"type": "user", "isMeta": True, "message": {"role": "user", "content": "ignore me"}},
            {"type": "user", "message": {"role": "user", "content": "Old question"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Old answer"}]}},
            {"type": "user", "message": {"role": "user", "content": "Latest question"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash"}]}},
            {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ignore tool result"}]}},
            {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Latest answer"}]}},
        ]
        self.assertEqual(notes.extract_latest_qa_from_records(records), ("Latest question", "Latest answer"))

    def test_joins_multiple_assistant_text_blocks(self):
        records = [
            {"type": "user", "message": {"role": "user", "content": "Question"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "text", "text": "Part one"},
                {"type": "text", "text": "Part two"},
            ]}},
        ]
        self.assertEqual(notes.extract_latest_qa_from_records(records), ("Question", "Part one\n\nPart two"))

    def test_raises_when_no_qa_pair_exists(self):
        with self.assertRaises(ValueError):
            notes.extract_latest_qa_from_records([])


class MarkdownNormalizationTests(unittest.TestCase):
    def test_optimizes_chinese_question_title(self):
        self.assertEqual(
            notes.optimize_question_title("请详细解释 Claude Code 是什么，以及它适合哪些开发场景？"),
            "Claude Code 是什么及适用场景？",
        )

    def test_promotes_heading_answer_to_level_two(self):
        answer = "# 总览\n\n## 常见标记\n\n内容"
        self.assertEqual(notes.normalize_answer_headings(answer), "## 总览\n\n### 常见标记\n\n内容")

    def test_preserves_headings_inside_fenced_code_blocks(self):
        answer = "# 总览\n\n```markdown\n# 代码块标题\n```"
        self.assertIn("# 代码块标题", notes.normalize_answer_headings(answer))

    def test_headingless_answer_promotes_first_line(self):
        self.assertEqual(notes.normalize_answer_headings("Plain answer."), "## Plain answer.")


class SecretAndRenderTests(unittest.TestCase):
    def test_detects_common_secret_patterns(self):
        samples = [
            "API_KEY=sk-proj-example-secret-token-value",
            "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example",
            "password: super-secret-password",
            "xox" + "b-123456789012-123456789012-abcdefghijklmnopqrstuv",
            "AI" + "zaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123456789",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(notes.contains_possible_secret(sample))

    def test_render_record_matches_current_shape(self):
        record = notes.render_record("2026-06-23", "10:11:12", "What is Claude Code?", "Claude Code is an agentic coding CLI.")
        self.assertIn("# What is Claude Code?", record)
        self.assertIn("> 记录时间：2026-06-23 10:11:12", record)
        self.assertIn("## Claude Code is an agentic coding CLI.", record)


class SafeAppendTests(unittest.TestCase):
    def test_append_record_creates_file_and_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            note_path = Path(tmp) / "note.md"
            notes.append_record_safely(note_path, "first")
            notes.append_record_safely(note_path, "second")
            self.assertIn("first", note_path.read_text(encoding="utf-8"))
            self.assertIn("second", note_path.read_text(encoding="utf-8"))

    def test_append_record_refuses_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                notes.append_record_safely(Path(tmp), "content")

    def test_append_record_refuses_symlink_when_no_nofollow_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            target_path = Path(tmp) / "target.md"
            symlink_path = Path(tmp) / "note.md"
            target_path.write_text("safe", encoding="utf-8")
            try:
                symlink_path.symlink_to(target_path)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation is not supported: {exc}")

            had_no_follow = hasattr(notes.os, "O_NOFOLLOW")
            saved_no_follow = getattr(notes.os, "O_NOFOLLOW", None)
            if had_no_follow:
                delattr(notes.os, "O_NOFOLLOW")
            try:
                with self.assertRaisesRegex(ValueError, "symlink"):
                    notes.append_record_safely(symlink_path, "content")
            finally:
                if had_no_follow:
                    setattr(notes.os, "O_NOFOLLOW", saved_no_follow)
            self.assertEqual(target_path.read_text(encoding="utf-8"), "safe")

    def test_append_record_raises_when_os_write_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            note_path = Path(tmp) / "note.md"
            calls = 0

            def zero_then_fail(fd: int, data: bytes) -> int:
                nonlocal calls
                calls += 1
                if calls == 1:
                    return 0
                raise AssertionError("os.write called again after writing zero bytes")

            with unittest.mock.patch.object(notes.os, "write", side_effect=zero_then_fail):
                with self.assertRaisesRegex(OSError, "zero bytes"):
                    notes.append_record_safely(note_path, "content")
            self.assertEqual(calls, 1)

    def test_append_record_sets_permissions_on_open_fd_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            note_path = Path(tmp) / "note.md"
            calls: list[tuple[int, int] | tuple[str, int]] = []
            original_write = notes.os.write

            def record_fchmod(fd: int, mode: int) -> None:
                calls.append((fd, mode))

            def assert_chmod_before_write(fd: int, data: bytes) -> int:
                calls.append(("write", fd))
                self.assertTrue(
                    any(call == (fd, 0o600) for call in calls),
                    "append_record_safely must fchmod the open fd before writing",
                )
                return original_write(fd, data)

            with unittest.mock.patch.object(notes.os, "fchmod", side_effect=record_fchmod, create=True):
                with unittest.mock.patch.object(notes.os, "write", side_effect=assert_chmod_before_write):
                    notes.append_record_safely(note_path, "content")

            self.assertIn("content", note_path.read_text(encoding="utf-8"))


class LockDiagnosticsTests(unittest.TestCase):
    def test_lock_failure_truncates_large_owner_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_dir = Path(tmp)
            lock_dir = write_dir / ".save-claude-notes.lock"
            lock_dir.mkdir()
            (lock_dir / "owner").write_text("x" * 5000, encoding="utf-8")

            with unittest.mock.patch.object(notes.time, "sleep", return_value=None):
                with self.assertRaises(notes.SaveNoteError) as context:
                    notes.acquire_lock(write_dir)

            self.assertEqual(context.exception.exit_code, notes.EXIT_LOCK)
            self.assertIn("Existing lock metadata", str(context.exception))
            self.assertLess(len(str(context.exception)), 4500)

    def test_lock_failure_rejects_symlink_owner_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_dir = Path(tmp)
            lock_dir = write_dir / ".save-claude-notes.lock"
            lock_dir.mkdir()
            target = write_dir / "target"
            owner = lock_dir / "owner"
            target.write_text("unsafe", encoding="utf-8")
            try:
                owner.symlink_to(target)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation is not supported: {exc}")

            with unittest.mock.patch.object(notes.time, "sleep", return_value=None):
                with self.assertRaises(notes.SaveNoteError) as context:
                    notes.acquire_lock(write_dir)

            self.assertEqual(context.exception.exit_code, notes.EXIT_LOCK)
            self.assertNotIn("unsafe", str(context.exception))
            self.assertIn("unsafe owner metadata", str(context.exception))


class CliResolutionTests(unittest.TestCase):
    def test_empty_save_note_config_env_falls_back_to_default_config_file(self):
        original = os.environ.get("SAVE_NOTE_CONFIG")
        os.environ["SAVE_NOTE_CONFIG"] = ""
        try:
            args = notes.parse_args([])
        finally:
            if original is None:
                os.environ.pop("SAVE_NOTE_CONFIG", None)
            else:
                os.environ["SAVE_NOTE_CONFIG"] = original
        self.assertEqual(args.config, notes.DEFAULT_CONFIG_FILE)

    def test_output_file_wins_over_bad_config(self):
        args = notes.parse_args(["--output-file", "D:/xiao/WuKong/空.md", "--question", "q", "--answer", "a"])
        self.assertEqual(notes.resolve_note_file(args, "ignored", "2026-06-23"), "D:/xiao/WuKong/空.md")

    def test_output_file_rejects_empty_string(self):
        args = notes.parse_args(["--output-file", "", "--question", "q", "--answer", "a"])
        with self.assertRaisesRegex(ValueError, "output-file"):
            notes.resolve_note_file(args, "ignored", "2026-06-23")

    def test_output_file_rejects_newline(self):
        args = notes.parse_args(["--output-file", "D:/xiao/WuKong/bad\nname.md", "--question", "q", "--answer", "a"])
        with self.assertRaisesRegex(ValueError, "output-file"):
            notes.resolve_note_file(args, "ignored", "2026-06-23")

    def test_notes_dir_uses_daily_file(self):
        args = notes.parse_args(["--notes-dir", "D:/xiao/WuKong", "--question", "q", "--answer", "a"])
        self.assertEqual(notes.resolve_note_file(args, "D:/xiao/WuKong", "2026-06-23"), "D:/xiao/WuKong/2026-06-23.md")

    def test_resolve_notes_dir_prefers_cli_notes_dir_over_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"notesDir": "/from/config"}), encoding="utf-8")
            args = notes.parse_args(["--config", str(config_file), "--notes-dir", "/from/cli"])
            self.assertEqual(notes.resolve_notes_dir(args), "/from/cli")

    def test_resolve_notes_dir_expands_default_before_validation(self):
        args = notes.parse_args(["--config", "D:/missing-config.json"])
        self.assertTrue(notes.resolve_notes_dir(args).endswith("/claude-notes"))

    def test_load_notes_dir_accepts_unix_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"notesDir": "/tmp/claude-notes"}), encoding="utf-8")
            self.assertEqual(notes.load_notes_dir(config_file, "ignored"), "/tmp/claude-notes")

    def test_load_notes_dir_accepts_windows_drive_absolute_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"notesDir": "D:/xiao/WuKong"}), encoding="utf-8")
            self.assertEqual(notes.load_notes_dir(config_file, "ignored"), "D:/xiao/WuKong")

    def test_load_notes_dir_rejects_relative_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"notesDir": "relative/path"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "notesDir"):
                notes.load_notes_dir(config_file, "ignored")

    def test_load_notes_dir_rejects_newline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            config_file.write_text(json.dumps({"notesDir": "/tmp/bad\npath"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "notesDir"):
                notes.load_notes_dir(config_file, "ignored")

    def test_latest_rejects_explicit_question_answer(self):
        args = notes.parse_args(["--latest", "--question", "q", "--answer", "a"])
        with self.assertRaises(ValueError):
            notes.validate_input_mode(args)


if __name__ == "__main__":
    unittest.main()
