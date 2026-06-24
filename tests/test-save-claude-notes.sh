#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT_DIR/scripts/save-claude-notes.sh"
PYTHON_TEST="$ROOT_DIR/tests/test_save_claude_notes.py"

python_command() {
  local candidate
  for candidate in python3 python py; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[0] >= 3 else 1)' >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  echo "Python 3 is required to run save-claude-notes tests." >&2
  return 1
}

PYTHON_CMD="$(python_command)"
"$PYTHON_CMD" "$PYTHON_TEST" -v

TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

assert_file_contains() {
  local file="$1"
  local expected="$2"
  if ! grep -Fq -- "$expected" "$file"; then
    echo "Expected $file to contain: $expected" >&2
    exit 1
  fi
}

assert_file_contains_line() {
  local file="$1"
  local expected="$2"
  "$PYTHON_CMD" - "$file" "$expected" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
lines = path.read_text(encoding="utf-8").splitlines()
if expected not in lines:
    raise SystemExit(1)
PY
  if [[ "$?" != "0" ]]; then
    echo "Expected $file to contain line: $expected" >&2
    exit 1
  fi
}

assert_fails() {
  if "$@" >/dev/null 2>&1; then
    echo "Expected command to fail: $*" >&2
    exit 1
  fi
}

make_config() {
  local config_file="$1"
  local notes_dir="$2"
  mkdir -p "$(dirname "$config_file")"
  cat > "$config_file" <<JSON
{
  "notesDir": "$notes_dir"
}
JSON
}

CONFIG_DIR="$TMP_DIR/config"
NOTES_DIR="$TMP_DIR/notes"
CONFIG_FILE="$CONFIG_DIR/config.json"
make_config "$CONFIG_FILE" "$NOTES_DIR"

export SAVE_NOTE_CONFIG="$CONFIG_FILE"
export SAVE_NOTE_NOW="2026-06-23T10:11:12+08:00"

printf 'What is Claude Code?\n' | "$SCRIPT" --answer "Claude Code is an agentic coding CLI."
NOTE_FILE="$NOTES_DIR/2026-06-23.md"

if [[ ! -f "$NOTE_FILE" ]]; then
  echo "Expected note file to be created: $NOTE_FILE" >&2
  exit 1
fi

assert_file_contains "$NOTE_FILE" "# What is Claude Code?"
assert_file_contains "$NOTE_FILE" "> 记录时间：2026-06-23 10:11:12"
assert_file_contains "$NOTE_FILE" "## Claude Code is an agentic coding CLI."
if grep -Fq -- "## Claude 回答" "$NOTE_FILE"; then
  echo "Did not expect a fixed Claude answer wrapper heading" >&2
  exit 1
fi

printf '请详细解释 Claude Code 是什么，以及它适合哪些开发场景？\n' | "$SCRIPT" --answer "Second answer."
assert_file_contains "$NOTE_FILE" "# Claude Code 是什么及适用场景？"
ENTRY_COUNT="$(grep -c '^# ' "$NOTE_FILE")"
if [[ "$ENTRY_COUNT" != "2" ]]; then
  echo "Expected append behavior with 2 question headings, got $ENTRY_COUNT" >&2
  exit 1
fi

MARKDOWN_CONFIG="$CONFIG_DIR/markdown.json"
MARKDOWN_DIR="$TMP_DIR/markdown-notes"
make_config "$MARKDOWN_CONFIG" "$MARKDOWN_DIR"
QUESTION_FILE="$TMP_DIR/question.md"
ANSWER_FILE="$TMP_DIR/answer.md"
cat > "$QUESTION_FILE" <<'EOF_Q'
请解释下面的命令：

```bash
git status --short
```
EOF_Q
cat > "$ANSWER_FILE" <<'EOF_A'
# 总览

Setext 总览
============

这个命令会输出简洁状态：

## 常见标记

Setext 子标题
------------

  # 缩进标题

Intro

---

More

- `M` 表示修改
- `??` 表示未跟踪

````markdown
```bash
```not-a-close
# 代码块里的标题不应降级
```
````

| 标记 | 含义 |
| --- | --- |
| M | Modified |
EOF_A
"$SCRIPT" --config "$MARKDOWN_CONFIG" --question-file "$QUESTION_FILE" --answer-file "$ANSWER_FILE"
MARKDOWN_FILE="$MARKDOWN_DIR/2026-06-23.md"
assert_file_contains "$MARKDOWN_FILE" '```bash'
assert_file_contains "$MARKDOWN_FILE" '## 总览'
assert_file_contains "$MARKDOWN_FILE" '## Setext 总览'
assert_file_contains "$MARKDOWN_FILE" '### 常见标记'
assert_file_contains "$MARKDOWN_FILE" '### Setext 子标题'
assert_file_contains "$MARKDOWN_FILE" '## 缩进标题'
assert_file_contains_line "$MARKDOWN_FILE" '---'
assert_file_contains "$MARKDOWN_FILE" '# 代码块里的标题不应降级'
assert_file_contains "$MARKDOWN_FILE" '| 标记 | 含义 |'

MIXED_HEADING_CONFIG="$CONFIG_DIR/mixed-heading.json"
MIXED_HEADING_DIR="$TMP_DIR/mixed-heading-notes"
make_config "$MIXED_HEADING_CONFIG" "$MIXED_HEADING_DIR"
"$SCRIPT" --config "$MIXED_HEADING_CONFIG" --question "Mixed headings" --answer $'## First\ntext\n# Later'
MIXED_HEADING_FILE="$MIXED_HEADING_DIR/2026-06-23.md"
assert_file_contains "$MIXED_HEADING_FILE" '## First'
assert_file_contains "$MIXED_HEADING_FILE" '## Later'

DEEP_FIRST_CONFIG="$CONFIG_DIR/deep-first-heading.json"
DEEP_FIRST_DIR="$TMP_DIR/deep-first-heading-notes"
make_config "$DEEP_FIRST_CONFIG" "$DEEP_FIRST_DIR"
"$SCRIPT" --config "$DEEP_FIRST_CONFIG" --question "Deep first heading" --answer $'### First\ntext\n## Later'
DEEP_FIRST_FILE="$DEEP_FIRST_DIR/2026-06-23.md"
assert_file_contains "$DEEP_FIRST_FILE" '## First'
assert_file_contains "$DEEP_FIRST_FILE" '## Later'

JSON_CONFIG="$CONFIG_DIR/stdin-json.json"
JSON_DIR="$TMP_DIR/json-notes"
make_config "$JSON_CONFIG" "$JSON_DIR"
printf '{"question":"JSON question","answer":"JSON answer"}' | "$SCRIPT" --config "$JSON_CONFIG" --stdin-json
assert_file_contains "$JSON_DIR/2026-06-23.md" "JSON question"
assert_file_contains "$JSON_DIR/2026-06-23.md" "JSON answer"

UNICODE_JSON_CONFIG="$CONFIG_DIR/unicode-stdin-json.json"
UNICODE_JSON_DIR="$TMP_DIR/unicode-json-notes"
make_config "$UNICODE_JSON_CONFIG" "$UNICODE_JSON_DIR"
PYTHONIOENCODING=utf-8 "$PYTHON_CMD" - <<'PY' | PYTHONIOENCODING=cp936 "$SCRIPT" --config "$UNICODE_JSON_CONFIG" --stdin-json
import json
payload = {"question": "请优化保存格式", "answer": "已完成保存格式优化。"}
print(json.dumps(payload, ensure_ascii=False), end="")
PY
UNICODE_JSON_FILE="$UNICODE_JSON_DIR/2026-06-23.md"
assert_file_contains "$UNICODE_JSON_FILE" "# 优化保存格式"
assert_file_contains "$UNICODE_JSON_FILE" "## 已完成保存格式优化。"

EMPTY_TITLE_CONFIG="$CONFIG_DIR/empty-title-stdin-json.json"
EMPTY_TITLE_DIR="$TMP_DIR/empty-title-json-notes"
make_config "$EMPTY_TITLE_CONFIG" "$EMPTY_TITLE_DIR"
PYTHONIOENCODING=utf-8 "$PYTHON_CMD" - <<'PY' | PYTHONIOENCODING=cp936 "$SCRIPT" --config "$EMPTY_TITLE_CONFIG" --stdin-json
import json
payload = {"question": "请详细解释？", "answer": "这是没有标题的中文回答。"}
print(json.dumps(payload, ensure_ascii=False), end="")
PY
EMPTY_TITLE_FILE="$EMPTY_TITLE_DIR/2026-06-23.md"
assert_file_contains "$EMPTY_TITLE_FILE" "# Untitled Question"
assert_file_contains "$EMPTY_TITLE_FILE" "## 这是没有标题的中文回答。"
if grep -Fxq -- "# " "$EMPTY_TITLE_FILE"; then
  echo "Question title must not be empty" >&2
  exit 1
fi

LATEST_TRANSCRIPT="$TMP_DIR/latest-transcript.jsonl"
LATEST_OUTPUT_FILE="$TMP_DIR/latest-output/Latest.md"
"$PYTHON_CMD" - "$LATEST_TRANSCRIPT" <<'PY'
import json
import sys
from pathlib import Path

records = [
    {"type": "user", "isMeta": True, "message": {"role": "user", "content": "system reminder should be ignored"}},
    {"type": "user", "message": {"role": "user", "content": "Old question"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Old answer"}]}},
    {"type": "user", "message": {"role": "user", "content": "Latest transcript question"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "tool_use", "name": "Bash", "input": {} }]}},
    {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "tool output should be ignored"}]}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Latest transcript answer"}]}},
]
Path(sys.argv[1]).write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")
PY
SAVE_NOTE_TRANSCRIPT="$LATEST_TRANSCRIPT" "$SCRIPT" --config "$CONFIG_FILE" --latest --output-file "$LATEST_OUTPUT_FILE"
assert_file_contains "$LATEST_OUTPUT_FILE" "# Latest transcript question"
assert_file_contains "$LATEST_OUTPUT_FILE" "## Latest transcript answer"
if grep -Fq -- "Old question" "$LATEST_OUTPUT_FILE"; then
  echo "--latest must save the latest Q&A, not an older one" >&2
  exit 1
fi
if grep -Fq -- "tool output should be ignored" "$LATEST_OUTPUT_FILE"; then
  echo "--latest must ignore tool result content" >&2
  exit 1
fi

AUTO_PROJECTS_ROOT="$TMP_DIR/auto-projects"
AUTO_OUTPUT_BASE="$TMP_DIR/latest-auto-workdir"
AUTO_OUTPUT_FILE="$AUTO_OUTPUT_BASE/Auto.md"
mkdir -p "$AUTO_OUTPUT_BASE"
AUTO_PROJECT_DIR="$("$PYTHON_CMD" - "$AUTO_PROJECTS_ROOT" "$AUTO_OUTPUT_BASE" <<'PY'
import sys
from pathlib import Path
projects_dir = Path(sys.argv[1])
cwd = sys.argv[2].replace('\\\\', '/')
if len(cwd) >= 2 and cwd[1] == ':':
    encoded = cwd[0].upper() + '-' + cwd[2:].replace('/', '-')
else:
    encoded = cwd.replace('/', '-')
path = projects_dir / encoded
path.mkdir(parents=True, exist_ok=True)
print(path)
PY
)"
"$PYTHON_CMD" - "$AUTO_PROJECT_DIR/older.jsonl" "$AUTO_PROJECT_DIR/newer.jsonl" <<'PY'
import json
import os
import sys
import time
from pathlib import Path

older = Path(sys.argv[1])
newer = Path(sys.argv[2])

def write(path, question, answer):
    records = [
        {"type": "user", "message": {"role": "user", "content": question}},
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": answer}]}},
    ]
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")

write(older, "Older auto question", "Older auto answer")
write(newer, "Newest auto question", "Newest auto answer")
os.utime(older, (time.time() - 100, time.time() - 100))
os.utime(newer, None)
PY
(
  cd "$AUTO_OUTPUT_BASE"
  SAVE_NOTE_PROJECTS_DIR="$AUTO_PROJECTS_ROOT" "$SCRIPT" --config "$CONFIG_FILE" --latest --output-file "Auto.md"
)
assert_file_contains "$AUTO_OUTPUT_FILE" "# Newest auto question"
assert_file_contains "$AUTO_OUTPUT_FILE" "## Newest auto answer"
if grep -Fq -- "Older auto question" "$AUTO_OUTPUT_FILE"; then
  echo "--latest auto-discovery must use the newest project transcript" >&2
  exit 1
fi

UNIX_PROJECTS_ROOT="$TMP_DIR/unix-projects"
UNIX_WORKDIR="/tmp/save-claude-notes-unix-path-test"
UNIX_PROJECT_DIR="$UNIX_PROJECTS_ROOT/-tmp-save-claude-notes-unix-path-test"
UNIX_OUTPUT_FILE="$TMP_DIR/unix-latest.md"
mkdir -p "$UNIX_WORKDIR" "$UNIX_PROJECT_DIR"
"$PYTHON_CMD" - "$UNIX_PROJECT_DIR/session.jsonl" <<'PY'
import json
import sys
from pathlib import Path
records = [
    {"type": "user", "message": {"role": "user", "content": "Unix cwd question"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Unix cwd answer"}]}},
]
Path(sys.argv[1]).write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n", encoding="utf-8")
PY
(
  cd "$UNIX_WORKDIR"
  MSYS2_ENV_CONV_EXCL="SAVE_NOTE_CWD" SAVE_NOTE_CWD="/tmp/save-claude-notes-unix-path-test" SAVE_NOTE_PROJECTS_DIR="$UNIX_PROJECTS_ROOT" "$SCRIPT" --config "$CONFIG_FILE" --latest --output-file "$UNIX_OUTPUT_FILE"
)
assert_file_contains "$UNIX_OUTPUT_FILE" "# Unix cwd question"
assert_file_contains "$UNIX_OUTPUT_FILE" "## Unix cwd answer"

DRY_RUN_OUTPUT="$(printf 'Dry run question' | "$SCRIPT" --config "$CONFIG_FILE" --answer "Dry run answer" --dry-run)"
if [[ "$DRY_RUN_OUTPUT" != *"DRY RUN"* || "$DRY_RUN_OUTPUT" != *"Dry run question"* ]]; then
  echo "Expected dry-run output to include rendered note content" >&2
  exit 1
fi
if grep -Fq "Dry run question" "$NOTE_FILE"; then
  echo "Dry-run must not write to the note file" >&2
  exit 1
fi

PRINT_CONFIG_OUTPUT="$("$SCRIPT" --config "$CONFIG_FILE" --print-config)"
NORMALIZED_NOTES_DIR="$("$PYTHON_CMD" - "$NOTES_DIR" <<'PY'
import sys
from pathlib import Path
print(Path(sys.argv[1]))
PY
)"
if [[ "$PRINT_CONFIG_OUTPUT" != *"Notes dir: $NOTES_DIR"* && "$PRINT_CONFIG_OUTPUT" != *"Notes dir: $NORMALIZED_NOTES_DIR"* ]]; then
  echo "Expected print-config to show resolved notes directory" >&2
  exit 1
fi

HOME_DIR="$TMP_DIR/home"
mkdir -p "$HOME_DIR"
printf 'Default path question\n' | env HOME="$HOME_DIR" SAVE_NOTE_CONFIG="$TMP_DIR/missing-config.json" SAVE_NOTE_NOW="2026-06-23T10:11:12+08:00" \
  "$SCRIPT" --answer "Default path answer."
if [[ ! -f "$HOME_DIR/claude-notes/2026-06-23.md" ]]; then
  echo "Expected generic default ~/claude-notes path to be used" >&2
  exit 1
fi

TILDE_CONFIG="$CONFIG_DIR/tilde.json"
cat > "$TILDE_CONFIG" <<'JSON'
{
  "notesDir": "~/tilde-notes"
}
JSON
printf 'Tilde path question\n' | env HOME="$HOME_DIR" "$SCRIPT" --config "$TILDE_CONFIG" --answer "Tilde path answer."
if [[ ! -f "$HOME_DIR/tilde-notes/2026-06-23.md" ]]; then
  echo "Expected ~/ path to expand relative to HOME" >&2
  exit 1
fi

OVERRIDE_DIR="$TMP_DIR/override-notes"
printf '{"question":"Override dir?","answer":"Yes."}' | "$SCRIPT" --config "$CONFIG_FILE" --notes-dir "$OVERRIDE_DIR" --stdin-json
if [[ ! -f "$OVERRIDE_DIR/2026-06-23.md" ]]; then
  echo "Expected --notes-dir to override configured notesDir" >&2
  exit 1
fi
if grep -Fq -- "Override dir?" "$NOTE_FILE"; then
  echo "--notes-dir must not write to configured default note file" >&2
  exit 1
fi

printf 'Override tilde question\n' | env HOME="$HOME_DIR" "$SCRIPT" --config "$CONFIG_FILE" --notes-dir "~/override-tilde" --answer "Override tilde answer."
if [[ ! -f "$HOME_DIR/override-tilde/2026-06-23.md" ]]; then
  echo "Expected --notes-dir ~/ path to expand relative to HOME" >&2
  exit 1
fi

OUTPUT_FILE="$TMP_DIR/exact-notes/Git.md"
printf '{"question":"Exact file?","answer":"Saved directly."}' | "$SCRIPT" --config "$CONFIG_FILE" --output-file "$OUTPUT_FILE" --stdin-json
if [[ ! -f "$OUTPUT_FILE" ]]; then
  echo "Expected --output-file to create exact Markdown file" >&2
  exit 1
fi
assert_file_contains "$OUTPUT_FILE" "# Exact file?"
assert_file_contains "$OUTPUT_FILE" "## Saved directly."
if [[ -f "$TMP_DIR/exact-notes/2026-06-23.md" ]]; then
  echo "--output-file must not write to a dated note inside the parent directory" >&2
  exit 1
fi
if grep -Fq -- "Exact file?" "$NOTE_FILE"; then
  echo "--output-file must not write to configured default note file" >&2
  exit 1
fi

printf 'Exact file second question\n' | "$SCRIPT" --config "$CONFIG_FILE" --output-file "$OUTPUT_FILE" --answer "Second direct save."
OUTPUT_ENTRY_COUNT="$(grep -c '^# ' "$OUTPUT_FILE")"
if [[ "$OUTPUT_ENTRY_COUNT" != "2" ]]; then
  echo "Expected --output-file append behavior with 2 question headings, got $OUTPUT_ENTRY_COUNT" >&2
  exit 1
fi

RELATIVE_OUTPUT_BASE="$TMP_DIR/relative-output-base"
mkdir -p "$RELATIVE_OUTPUT_BASE"
(
  cd "$RELATIVE_OUTPUT_BASE"
  printf 'Relative exact file question\n' | "$SCRIPT" --config "$CONFIG_FILE" --output-file "nested/Git.md" --answer "Relative direct save."
)
if [[ ! -f "$RELATIVE_OUTPUT_BASE/nested/Git.md" ]]; then
  echo "Expected relative --output-file to resolve from current directory" >&2
  exit 1
fi
assert_file_contains "$RELATIVE_OUTPUT_BASE/nested/Git.md" "# Relative exact file question"

assert_fails "$SCRIPT" --config "$CONFIG_FILE" --notes-dir "relative-dir" --question "q" --answer "a"
assert_fails "$SCRIPT" --config "$CONFIG_FILE" --notes-dir "" --question "q" --answer "a"
assert_fails "$SCRIPT" --config "$CONFIG_FILE" --output-file "" --question "q" --answer "a"
assert_fails "$SCRIPT" --config "$CONFIG_FILE" --output-file $'bad\nfile.md' --question "q" --answer "a"

BAD_OVERRIDE_CONFIG="$CONFIG_DIR/bad-override.json"
printf '{bad json' > "$BAD_OVERRIDE_CONFIG"
BAD_OVERRIDE_DIR="$TMP_DIR/bad-config-override"
printf 'Bad config override question\n' | "$SCRIPT" --config "$BAD_OVERRIDE_CONFIG" --notes-dir "$BAD_OVERRIDE_DIR" --answer "Bad config override answer."
if [[ ! -f "$BAD_OVERRIDE_DIR/2026-06-23.md" ]]; then
  echo "Expected --notes-dir to bypass bad config for this run" >&2
  exit 1
fi

BAD_CONFIG_OUTPUT_FILE="$TMP_DIR/bad-config-exact/Git.md"
printf 'Bad config exact file question\n' | "$SCRIPT" --config "$BAD_OVERRIDE_CONFIG" --output-file "$BAD_CONFIG_OUTPUT_FILE" --answer "Bad config exact answer."
if [[ ! -f "$BAD_CONFIG_OUTPUT_FILE" ]]; then
  echo "Expected --output-file to bypass bad config for this run" >&2
  exit 1
fi
assert_file_contains "$BAD_CONFIG_OUTPUT_FILE" "# Bad config exact file question"

BAD_CONFIG="$CONFIG_DIR/bad.json"
printf '{bad json' > "$BAD_CONFIG"
assert_fails "$SCRIPT" --config "$BAD_CONFIG" --question "q" --answer "a"

MISSING_CONFIG="$CONFIG_DIR/missing-field.json"
printf '{}' > "$MISSING_CONFIG"
assert_fails "$SCRIPT" --config "$MISSING_CONFIG" --question "q" --answer "a"

UNKNOWN_CONFIG="$CONFIG_DIR/unknown-field.json"
printf '{"notesDir":"%s","extra":true}' "$NOTES_DIR" > "$UNKNOWN_CONFIG"
assert_fails "$SCRIPT" --config "$UNKNOWN_CONFIG" --question "q" --answer "a"

RELATIVE_CONFIG="$CONFIG_DIR/relative.json"
printf '{"notesDir":"relative-notes"}' > "$RELATIVE_CONFIG"
assert_fails "$SCRIPT" --config "$RELATIVE_CONFIG" --question "q" --answer "a"

if printf 'Bad timestamp\n' | env SAVE_NOTE_NOW="../badpathT10:11:12+08:00" "$SCRIPT" --config "$CONFIG_FILE" --answer "Should fail" >/dev/null 2>&1; then
  echo "Expected invalid timestamp to fail" >&2
  exit 1
fi

if printf 'Bad calendar\n' | env SAVE_NOTE_NOW="2026-99-99T99:99:99+08:00" "$SCRIPT" --config "$CONFIG_FILE" --answer "Should fail" >/dev/null 2>&1; then
  echo "Expected invalid calendar timestamp to fail" >&2
  exit 1
fi

FAKE_SLACK_TOKEN="xox""b-123456789012-123456789012-abcdefghijklmnopqrstuv"
FAKE_GOOGLE_API_KEY="AI""zaSyABCDEFGHIJKLMNOPQRSTUVWXYZ123456789"
SECRET_SAMPLES=(
  'API_KEY=sk-proj-example-secret-token-value'
  'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.example'
  'password: super-secret-password'
  "$FAKE_SLACK_TOKEN"
  "$FAKE_GOOGLE_API_KEY"
)
for secret in "${SECRET_SAMPLES[@]}"; do
  if printf 'Secret question\n' | "$SCRIPT" --config "$CONFIG_FILE" --answer "$secret" >/dev/null 2>&1; then
    echo "Expected suspected secret to be blocked: $secret" >&2
    exit 1
  fi
done

printf 'Secret override question\n' | env SAVE_NOTE_ALLOW_SECRETS=1 "$SCRIPT" --config "$CONFIG_FILE" --answer "API_KEY=sk-proj-example-secret-token-value"
ENTRY_COUNT="$(grep -c '^# ' "$NOTE_FILE")"
if [[ "$ENTRY_COUNT" != "3" ]]; then
  echo "Expected secret override append behavior with 3 question headings, got $ENTRY_COUNT" >&2
  exit 1
fi

SYMLINK_CONFIG="$CONFIG_DIR/symlink.json"
SYMLINK_DIR="$TMP_DIR/symlink-notes"
make_config "$SYMLINK_CONFIG" "$SYMLINK_DIR"
mkdir -p "$SYMLINK_DIR"
ln -s "$TMP_DIR/target.txt" "$SYMLINK_DIR/2026-06-23.md" 2>/dev/null || true
if [[ -L "$SYMLINK_DIR/2026-06-23.md" ]]; then
  assert_fails "$SCRIPT" --config "$SYMLINK_CONFIG" --question "q" --answer "a"
fi

mkdir -p "$NOTES_DIR/.save-claude-notes.lock"
if printf 'Locked question\n' | "$SCRIPT" --answer "Should fail" >/dev/null 2>&1; then
  echo "Expected stale lock to fail" >&2
  exit 1
fi
rmdir "$NOTES_DIR/.save-claude-notes.lock"

echo "save-claude-notes tests passed"
