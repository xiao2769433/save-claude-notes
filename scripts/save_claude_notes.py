#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_NOTES_DIR = "~/claude-notes"
DEFAULT_CONFIG_FILE = "~/.claude/save-claude-notes/config.json"
MAX_CONFIG_BYTES = 64 * 1024
MAX_TRANSCRIPT_BYTES = 50 * 1024 * 1024
MAX_LOCK_OWNER_BYTES = 4096
EXIT_ARGUMENT_ERROR = 2
EXIT_SECRET = 3
EXIT_LOCK = 4
EXIT_UNSAFE_NOTE = 5
EXIT_UNSAFE_WRITE_DIR = 6


class SaveNoteError(Exception):
    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def env_or_default(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="save-claude-notes")
    parser.add_argument("--config", default=env_or_default("SAVE_NOTE_CONFIG", DEFAULT_CONFIG_FILE))
    parser.add_argument("--notes-dir", dest="notes_dir")
    parser.add_argument("--output-file", dest="output_file")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--transcript", default=os.environ.get("SAVE_NOTE_TRANSCRIPT", ""))
    parser.add_argument("--question", default="")
    parser.add_argument("--answer", default="")
    parser.add_argument("--question-file", dest="question_file", default="")
    parser.add_argument("--answer-file", dest="answer_file", default="")
    parser.add_argument("--stdin-json", dest="stdin_json", action="store_true")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true")
    parser.add_argument("--print-config", dest="print_config", action="store_true")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def is_absolute_notes_dir(raw_path: str) -> bool:
    return raw_path.startswith("/") or re.match(r"^[A-Za-z]:/", raw_path) is not None


def validate_notes_dir(raw_path: str, field_name: str = "notesDir") -> str:
    if not raw_path or "\n" in raw_path or "\r" in raw_path or not is_absolute_notes_dir(raw_path):
        raise ValueError(f"{field_name} must be an absolute path without newlines")
    return raw_path


def validate_output_file(raw_path: str) -> str:
    if not raw_path or "\n" in raw_path or "\r" in raw_path:
        raise ValueError("--output-file must be non-empty and must not contain newlines")
    return raw_path


def load_notes_dir(config_file: Path, default_notes_dir: str) -> str:
    if not config_file.is_file():
        return default_notes_dir
    if config_file.stat().st_size > MAX_CONFIG_BYTES:
        raise ValueError(f"Config {config_file} is too large")
    try:
        data = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read config {config_file}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Config {config_file} must be a JSON object")
    unknown_keys = set(data) - {"notesDir"}
    if unknown_keys:
        raise ValueError(f"Config {config_file} contains unsupported fields: {sorted(unknown_keys)}")
    notes_dir = data.get("notesDir")
    if not isinstance(notes_dir, str) or not notes_dir.strip():
        raise ValueError(f"Config {config_file} must contain a non-empty string field: notesDir")
    try:
        return validate_notes_dir(expand_user_path(notes_dir.strip()))
    except ValueError as exc:
        raise ValueError(f"Config {config_file} has invalid notesDir: {exc}") from exc


def resolve_note_file(args: argparse.Namespace, notes_dir: str, day: str) -> str:
    output_file = getattr(args, "output_file", None)
    if output_file is not None:
        return expand_user_path(validate_output_file(output_file))
    normalized_notes_dir = validate_notes_dir(notes_dir).rstrip("/\\")
    return f"{normalized_notes_dir}/{day}.md"


def validate_input_mode(args: argparse.Namespace) -> None:
    if args.latest and (args.stdin_json or args.question or args.answer or args.question_file or args.answer_file):
        raise ValueError("--latest cannot be combined with explicit question or answer input.")


def resolve_notes_dir(args: argparse.Namespace, default_notes_dir: str = DEFAULT_NOTES_DIR) -> str:
    output_file = getattr(args, "output_file", None)
    if output_file is not None:
        return expand_user_path(default_notes_dir)
    if args.notes_dir is not None:
        expanded_notes_dir = expand_user_path(args.notes_dir)
        return validate_notes_dir(expanded_notes_dir, "--notes-dir")
    config_notes_dir = load_notes_dir(Path(expand_user_path(args.config)), default_notes_dir)
    expanded_config_notes_dir = expand_user_path(config_notes_dir)
    return validate_notes_dir(expanded_config_notes_dir)


def encode_project_path(cwd: str) -> str:
    normalized = cwd.replace("\\", "/")
    if len(normalized) >= 2 and normalized[1] == ":":
        return normalized[0].upper() + "-" + normalized[2:].replace("/", "-")
    if len(normalized) >= 3 and normalized[0] == "/" and normalized[2] == "/" and normalized[1].isalpha():
        return normalized[1].upper() + "-" + normalized[2:].replace("/", "-")
    encoded = normalized.replace("/", "-")
    if not encoded:
        raise ValueError("Cannot encode empty current directory")
    return encoded


def normalize_windows_shell_path(raw_path: str, force: bool = False) -> str:
    if not (force or os.name == "nt"):
        return raw_path
    match = re.match(r"^/([A-Za-z])(?:/(.*))?$", raw_path)
    if not match:
        return raw_path
    tail = match.group(2) or ""
    return f"{match.group(1).upper()}:/{tail}".rstrip("/")


def expand_user_path(raw_path: str, home: str | None = None) -> str:
    resolved_home = normalize_windows_shell_path(home if home is not None else os.environ.get("HOME", os.path.expanduser("~"))).replace("\\", "/")
    if raw_path == "~":
        return resolved_home
    if raw_path.startswith("~/"):
        return resolved_home.rstrip("/\\") + "/" + raw_path[2:]
    return normalize_windows_shell_path(raw_path)


def text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    texts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
            text = item["text"].strip()
            if text:
                texts.append(text)
    return "\n\n".join(texts).strip()


def extract_latest_qa_from_records(records: list[dict[str, Any]]) -> tuple[str, str]:
    pairs: list[tuple[str, str]] = []
    pending_question: str | None = None
    pending_answer: list[str] = []

    for item in records:
        if not isinstance(item, dict) or item.get("isMeta"):
            continue
        message = item.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content_text = text_from_content(message.get("content"))
        if not content_text:
            continue
        if role == "user":
            if pending_question and pending_answer:
                pairs.append((pending_question, "\n\n".join(pending_answer).strip()))
            pending_question = content_text
            pending_answer = []
        elif role == "assistant" and pending_question:
            pending_answer.append(content_text)

    if pending_question and pending_answer:
        pairs.append((pending_question, "\n\n".join(pending_answer).strip()))
    if not pairs:
        raise ValueError("No latest user/assistant Q&A found in transcript")
    return pairs[-1]


def read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                item = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records


def optimize_question_title(question: str) -> str:
    line = next((item.strip() for item in question.splitlines() if item.strip()), "Untitled Question")
    line = re.sub(r"^(?:#{1,6}|[-*+]|\d+[.)]|>)\s*", "", line).strip()
    line = re.sub(r"^(?:请你|请|麻烦|帮我一下|帮我)\s*", "", line)
    line = re.sub(r"^(?:详细)?\s*(?:解释|说明|介绍|分析|讲解|告诉我)\s*", "", line)
    line = re.sub(r"，?以及它适合哪些开发场景[？?]?$", "及适用场景？", line)
    line = re.sub(r"，?以及(.+)$", r"及\1", line)
    line = re.sub(
        r"^(?:please\s+)?(?:can you\s+)?(?:explain|describe|summarize|analyze)\s+",
        "",
        line,
        flags=re.IGNORECASE,
    )
    line = re.sub(r"\s+", " ", line).strip()
    if not re.search(r"[\w一-鿿]", line):
        line = ""
    if len(line) > 80:
        shortened = re.split(r"[。！？!?；;]", line, maxsplit=1)[0].strip()
        line = shortened if 8 <= len(shortened) <= 80 else line[:77].rstrip() + "..."
    return line or "Untitled Question"


SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}"
    r"|ghp_[A-Za-z0-9_]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN (RSA |EC |OPENSSH |)?PRIVATE KEY-----"
    r"|xox[baprs]-[A-Za-z0-9-]{20,}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|Authorization:\s*Bearer\s+[A-Za-z0-9._~+/=-]{20,}"
    r"|(^|[^A-Za-z0-9_])(api_key|token|secret|password|passwd|private_key|secret_access_key)"
    r"[A-Za-z0-9_]*\s*[:=]\s*\S+)",
    re.IGNORECASE | re.MULTILINE,
)


def contains_possible_secret(text: str) -> bool:
    return SECRET_PATTERN.search(text) is not None


def render_record(date_part: str, time_part: str, question: str, answer: str) -> str:
    question_title = optimize_question_title(question).replace("\r", "")
    question_lines = question.splitlines()
    body_start = next((index + 1 for index, line in enumerate(question_lines) if line.split()), len(question_lines))
    question_body = "\n".join(question_lines[body_start:])
    body_section = f"{question_body}\n\n" if question_body.strip() else ""
    normalized_answer = normalize_answer_headings(answer).replace("\r", "")
    return f"\n# {question_title}\n\n{body_section}> 记录时间：{date_part} {time_part}\n\n{normalized_answer}"


def normalize_answer_headings(answer: str) -> str:
    lines = answer.splitlines()
    output: list[str] = []
    atx_re = re.compile(r"^( {0,3})(#{1,6})(\s+.*)$")
    fence_close_re = re.compile(r"^( {0,3})(`{3,}|~{3,})[ \t]*$")
    fence_open_re = re.compile(r"^( {0,3})(`{3,}|~{3,}).*$")
    setext_re = re.compile(r"^\s*(=+|-+)\s*$")

    def first_heading_level() -> int | None:
        fence_char: str | None = None
        fence_len = 0
        pending: str | None = None
        for line in lines:
            fence_match = fence_open_re.match(line) if fence_char is None else fence_close_re.match(line)
            if fence_match:
                marker = fence_match.group(2)
                marker_char = marker[0]
                marker_len = len(marker)
                if fence_char is None:
                    pending = None
                    fence_char = marker_char
                    fence_len = marker_len
                    continue
                if marker_char == fence_char and marker_len >= fence_len:
                    fence_char = None
                    fence_len = 0
                    continue
            if fence_char is not None:
                pending = None
                continue
            atx_match = atx_re.match(line)
            if atx_match:
                return len(atx_match.group(2))
            setext_match = setext_re.match(line)
            if pending is not None and pending.strip() and setext_match:
                return 1 if setext_match.group(1).startswith("=") else 2
            pending = line
        return None

    base_level = first_heading_level()
    fence_char: str | None = None
    fence_len = 0
    pending: str | None = None
    promoted_first_line = False

    def normalized_level(original: int) -> int:
        if base_level is None:
            return original
        return min(max(original - base_level + 2, 2), 6)

    def normalize_atx(line: str) -> str:
        match = atx_re.match(line)
        if not match:
            return line
        return "#" * normalized_level(len(match.group(2))) + match.group(3)

    def emit_pending() -> None:
        nonlocal pending, promoted_first_line
        if pending is None:
            return
        if base_level is None and pending.strip() and not promoted_first_line:
            output.append("## " + pending.strip())
            promoted_first_line = True
        else:
            output.append(normalize_atx(pending))
        pending = None

    for line in lines:
        fence_match = fence_open_re.match(line) if fence_char is None else fence_close_re.match(line)
        if fence_match:
            marker = fence_match.group(2)
            marker_char = marker[0]
            marker_len = len(marker)
            if fence_char is None:
                emit_pending()
                fence_char = marker_char
                fence_len = marker_len
                output.append(line)
                continue
            if marker_char == fence_char and marker_len >= fence_len:
                fence_char = None
                fence_len = 0
                output.append(line)
                continue

        if fence_char is not None:
            emit_pending()
            output.append(line)
            continue

        setext_match = setext_re.match(line)
        if pending is not None and pending.strip() and setext_match:
            original_level = 1 if setext_match.group(1).startswith("=") else 2
            output.append("#" * normalized_level(original_level) + " " + pending.strip())
            pending = None
            continue

        emit_pending()
        pending = line

    emit_pending()
    return "\n".join(output)


def validate_timestamp(value: str) -> datetime:
    if not re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([+-][0-9]{4}|[+-][0-9]{2}:[0-9]{2}|Z)?$", value):
        raise ValueError("Invalid timestamp format. Expected YYYY-MM-DDTHH:MM:SS+ZZZZ.")
    normalized = value
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    elif len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = normalized[:-2] + ":" + normalized[-2:]
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid timestamp value: {exc}") from exc


def now_from_environment() -> tuple[str, str]:
    raw_now = os.environ.get("SAVE_NOTE_NOW")
    if raw_now:
        parsed = validate_timestamp(raw_now)
        return raw_now[:10], raw_now[11:19]
    parsed = datetime.now().astimezone()
    return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M:%S")


def read_regular_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Refusing to read non-regular file: {path}")
    return path.read_text(encoding="utf-8")


def decode_stdin_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"Failed to read stdin as UTF-8: {exc}") from exc


def read_stdin_text() -> str:
    return decode_stdin_bytes(sys.stdin.buffer.read())


def read_stdin_json() -> tuple[str, str]:
    try:
        data = json.loads(read_stdin_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to read stdin JSON: {exc}") from exc
    return qa_from_payload(data, "stdin JSON")


def qa_from_payload(data: object, label: str) -> tuple[str, str]:
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be an object")
    question = data.get("question")
    answer = data.get("answer")
    if not isinstance(question, str) or not question.strip():
        raise ValueError(f"{label} must contain a non-empty string field: question")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(f"{label} must contain a non-empty string field: answer")
    return question, answer


def discover_latest_transcript() -> Path:
    projects_dir = Path(expand_user_path(os.environ.get("SAVE_NOTE_PROJECTS_DIR", "~/.claude/projects")))
    cwd = os.environ.get("SAVE_NOTE_CWD", os.getcwd())
    encoded = encode_project_path(cwd)
    project_dir = projects_dir / encoded
    candidates = [path for path in project_dir.glob("*.jsonl") if path.is_file() and not path.is_symlink()] if project_dir.is_dir() else []
    if not candidates:
        raise ValueError(f"No Claude Code transcript found for current directory under {projects_dir}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def latest_transcript_payload(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Transcript must be a regular file: {path}")
    if path.stat().st_size > MAX_TRANSCRIPT_BYTES:
        raise ValueError(f"Transcript is too large: {path}")
    try:
        return extract_latest_qa_from_records(read_jsonl_records(path))
    except ValueError as exc:
        raise ValueError(f"{exc}: {path}") from exc


def append_record_safely(note_path: Path, record: str) -> None:
    if note_path.is_symlink():
        raise ValueError(f"Refusing to write symlinked note file: {note_path}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(note_path, flags, 0o600)
    except OSError as exc:
        raise ValueError(f"Failed to open note file safely: {exc}") from exc
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"Refusing to write non-regular note file: {note_path}")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        content = (record + "\n").encode("utf-8")
        written = 0
        while written < len(content):
            bytes_written = os.write(fd, content[written:])
            if bytes_written == 0:
                raise OSError(f"Failed to write note file safely: os.write wrote zero bytes for {note_path}")
            written += bytes_written
    finally:
        os.close(fd)


def ensure_safe_write_dir(write_dir: Path) -> None:
    try:
        write_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SaveNoteError(f"Failed to create write directory: {exc}", EXIT_UNSAFE_WRITE_DIR) from exc
    if write_dir.is_symlink() or not write_dir.is_dir():
        raise SaveNoteError(f"Refusing to use non-directory or symlinked write directory: {write_dir}", EXIT_UNSAFE_WRITE_DIR)


def ensure_safe_note_file(note_file: Path) -> None:
    if note_file.exists() and (note_file.is_symlink() or not note_file.is_file()):
        raise SaveNoteError(f"Refusing to write note file because it is not a regular file: {note_file}", EXIT_UNSAFE_NOTE)


def safe_lock_owner_metadata(owner: Path) -> tuple[str | None, str | None]:
    try:
        owner_stat = owner.lstat()
    except OSError as exc:
        return None, f"Could not inspect existing lock owner metadata: {exc}"
    if stat.S_ISLNK(owner_stat.st_mode) or not stat.S_ISREG(owner_stat.st_mode):
        return None, "Existing lock has unsafe owner metadata; refusing to read it."
    try:
        with owner.open("rb") as handle:
            data = handle.read(MAX_LOCK_OWNER_BYTES)
    except OSError as exc:
        return None, f"Could not read existing lock owner metadata: {exc}"
    suffix = "\n[truncated]" if owner_stat.st_size > MAX_LOCK_OWNER_BYTES else ""
    return data.decode("utf-8", errors="replace") + suffix, None


def lock_owner_text() -> str:
    created = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    host = socket.gethostname() or "unknown"
    return f"pid={os.getpid()}\nhost={host}\ncreated={created}\n"


def acquire_lock(write_dir: Path) -> Path:
    lock_dir = write_dir / ".save-claude-notes.lock"
    for _ in range(100):
        try:
            lock_dir.mkdir()
            (lock_dir / "owner").write_text(lock_owner_text(), encoding="utf-8")
            return lock_dir
        except FileExistsError:
            time.sleep(0.05)
        except OSError as exc:
            raise SaveNoteError(f"Could not acquire save-claude-notes lock: {exc}", EXIT_LOCK) from exc
    message = f"Could not acquire save-claude-notes lock: {lock_dir}"
    owner = lock_dir / "owner"
    metadata, diagnostic = safe_lock_owner_metadata(owner)
    if metadata is not None:
        message = message + "\nExisting lock metadata:\n" + metadata
    elif diagnostic is not None:
        message = message + "\n" + diagnostic
    else:
        message = message + "\nIf no save-claude-notes process is running, remove this stale directory and retry."
    raise SaveNoteError(message, EXIT_LOCK)


def release_lock(lock_dir: Path) -> None:
    try:
        (lock_dir / "owner").unlink(missing_ok=True)
        lock_dir.rmdir()
    except OSError:
        pass


def resolve_cli_paths(args: argparse.Namespace) -> tuple[str, Path, Path, str, str]:
    config_file = expand_user_path(args.config)
    try:
        notes_dir = resolve_notes_dir(args)
        day, time_part = now_from_environment()
        note_file = Path(resolve_note_file(args, notes_dir, day))
    except ValueError as exc:
        raise SaveNoteError(str(exc), EXIT_ARGUMENT_ERROR) from exc
    return config_file, Path(notes_dir), note_file, day, time_part


def resolve_input(args: argparse.Namespace) -> tuple[str, str]:
    question = args.question
    answer = args.answer
    try:
        validate_input_mode(args)
        if args.latest:
            transcript = Path(expand_user_path(args.transcript)) if args.transcript.strip() else discover_latest_transcript()
            question, answer = latest_transcript_payload(transcript)
        elif args.stdin_json:
            question, answer = read_stdin_json()
        if args.question_file:
            question = read_regular_file(Path(expand_user_path(args.question_file)))
        if args.answer_file:
            answer = read_regular_file(Path(expand_user_path(args.answer_file)))
        if not question and not sys.stdin.isatty():
            question = read_stdin_text()
        if not question.strip():
            raise ValueError("Missing question. Pass --question, --question-file, --stdin-json, or pipe it on stdin.")
        if not answer.strip():
            raise ValueError("Missing answer. Pass --answer, --answer-file, or --stdin-json.")
    except ValueError as exc:
        raise SaveNoteError(str(exc), EXIT_ARGUMENT_ERROR) from exc
    return question, answer


def maybe_reject_secrets(question: str, answer: str) -> None:
    if contains_possible_secret(f"{question}\n{answer}") and os.environ.get("SAVE_NOTE_ALLOW_SECRETS") != "1":
        raise SaveNoteError(
            "Refusing to save because the note appears to contain a secret.\n"
            "Review and redact the content, or set SAVE_NOTE_ALLOW_SECRETS=1 to override intentionally.",
            EXIT_SECRET,
        )


def print_config(config_file: str, notes_dir: Path, note_file: Path) -> None:
    print(f"Config file: {config_file}")
    print(f"Notes dir: {notes_dir}")
    print(f"Today file: {note_file}")


def run_cli(args: argparse.Namespace) -> int:
    config_file, notes_dir, note_file, day, time_part = resolve_cli_paths(args)
    if args.print_config:
        print_config(config_file, notes_dir, note_file)
        return 0
    question, answer = resolve_input(args)
    maybe_reject_secrets(question, answer)
    record = render_record(day, time_part, question, answer)
    if args.dry_run:
        print("DRY RUN")
        print_config(config_file, notes_dir, note_file)
        print()
        print(record)
        return 0
    write_dir = note_file.parent if args.output_file is not None else notes_dir
    ensure_safe_write_dir(write_dir)
    lock_dir = acquire_lock(write_dir)
    try:
        ensure_safe_note_file(note_file)
        try:
            append_record_safely(note_file, record)
        except ValueError as exc:
            raise SaveNoteError(str(exc), EXIT_UNSAFE_NOTE) from exc
    finally:
        release_lock(lock_dir)
    print(note_file)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
        return run_cli(args)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else EXIT_ARGUMENT_ERROR
    except SaveNoteError as exc:
        print(exc, file=sys.stderr)
        return exc.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
