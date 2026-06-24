# Claude Code 对话笔记保存 (save-claude-notes)

一个 Claude Code Skill，用于把当前 Claude Code 对话中的**提问和回答**保存为本地 Markdown 笔记：脚本优先通过 `--latest` 从 Claude Code transcript 读取最近一轮问答，并按配置追加写入本地文件，适合沉淀调试记录、配置过程、学习笔记和可复用经验。

> English quick summary: `save-claude-notes` saves the latest Claude Code Q&A into local Markdown notes. The three common modes are: default daily note under configured `notesDir`, exact `.md` file via `--output-file`, and temporary directory via `--notes-dir`.

## ✨ 功能

- 📝 保存 Claude Code 最近一轮提问与回答
- ⚡ 优先使用 `--latest` 从 transcript 读取问答，避免把长回答重复传给脚本（节省token）
- 📅 默认保存到配置的 `notesDir` 目录下的当天文件：`YYYY-MM-DD.md`
- 📄 支持保存到指定 `.md` 文件，例如 `D:/xiao/WuKong/空.md`
- 📂 支持临时保存到指定文件夹目录，例如 `D:/xiao/WuKong/`
- ➕ 文件存在时追加到末尾，不覆盖已有内容
- 🕒 每条记录带时间戳，便于回溯
- 🔐 默认拦截常见密钥格式，避免误存 API Key / Token / 私钥
- 🔒 使用写入锁避免并发追加时内容交错
- 🧪 附带测试脚本，便于安装后验证

## ⚙️ 依赖

- Claude Code
- Bash-compatible shell
  - Windows 推荐 Git Bash 或 WSL
  - PowerShell 示例只用于复制配置文件；脚本本身请在 Git Bash / WSL 中运行
  - macOS/Linux 可直接使用系统 shell
- Python 3，可通过 `python3`、`python` 或 `py` 调用
- Git，仅手动 clone 安装时需要

## 📦 安装

### 方式一：让 Claude Code 自动安装（推荐）

如果你的 Claude Code 环境支持从 GitHub 安装 skill，在 Claude Code 中输入：

```text
帮我从这个 GitHub 仓库安装 skill：https://github.com/xiao2769433/save-claude-notes
```

Claude Code 应完成：克隆仓库到 skills 目录、确认脚本权限、提示你创建个人配置。

### 方式二：手动安装

```bash
# 1. 克隆仓库到 Claude Code 的 skills 目录
git clone https://github.com/xiao2769433/save-claude-notes.git ~/.claude/skills/save-claude-notes

# 2. 确保脚本可执行
chmod +x ~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh
chmod +x ~/.claude/skills/save-claude-notes/tests/test-save-claude-notes.sh
```

> **目录说明**：
> - Windows: `C:\Users\<你的用户名>\.claude\skills\save-claude-notes`
> - macOS/Linux: `~/.claude/skills/save-claude-notes`

### 3. 配置保存目录

仓库里只提供模板文件：

```text
~/.claude/skills/save-claude-notes/config.example.json
```

真正生效的个人配置文件应放在：

```text
~/.claude/save-claude-notes/config.json
```

首次安装后，请把模板复制到个人配置目录，再修改成自己的笔记目录。

macOS / Linux / Git Bash：

```bash
mkdir -p ~/.claude/save-claude-notes
cp ~/.claude/skills/save-claude-notes/config.example.json ~/.claude/save-claude-notes/config.json
```

Windows PowerShell：

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\save-claude-notes"
Copy-Item "$env:USERPROFILE\.claude\skills\save-claude-notes\config.example.json" "$env:USERPROFILE\.claude\save-claude-notes\config.json" -Force
```

配置内容示例：

```json
{
  "notesDir": "~/claude-notes"
}
```

如果不创建个人配置文件，脚本会使用内置默认目录：

```text
~/claude-notes
```

> Windows 路径建议在 JSON 中使用 `/`，例如 `D:/Notes/claude`，比 `D:\\Notes\\claude` 更不容易写错。

### 4. 验证安装

不要用 `/save-claude-notes` 做安装检查，因为它会真实保存最近一轮问答。

推荐使用：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --help
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --print-config
bash ~/.claude/skills/save-claude-notes/tests/test-save-claude-notes.sh
```

看到以下输出说明脚本功能正常：

```text
save-claude-notes tests passed
```

## 🚀 使用

这里按最常用的 3 种 `/save-claude-notes` 用法说明。默认都优先使用 `--latest`，让脚本从 Claude Code transcript 读取最近一轮问答，避免把长回答重复传给脚本。

### 1. 保存到配置目录的当天文件

在 Claude Code 中输入：

```text
/save-claude-notes
```

对应脚本参数：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --latest
```

保存位置：

```text
<notesDir>/YYYY-MM-DD.md
```

其中 `notesDir` 来自：

```text
~/.claude/save-claude-notes/config.json
```

如果没有配置文件，默认保存到：

```text
~/claude-notes/YYYY-MM-DD.md
```

### 2. 保存到指定 `.md` 文件

在 Claude Code 中输入：

```text
/save-claude-notes 保存到 D:\xiao\WuKong\空.md
```

对应脚本参数：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh \
  --latest \
  --output-file "D:/xiao/WuKong/空.md"
```

行为：

- 直接追加到指定的 `.md` 文件；
- 文件不存在时自动创建；
- 父目录不存在时自动创建；
- 不修改 `~/.claude/save-claude-notes/config.json`；
- 当前脚本接受任意非空路径，但推荐只保存到 `.md` / `.markdown` 文件，避免误写配置文件或其他非笔记文件。

### 3. 保存到指定文件夹目录

在 Claude Code 中输入：

```text
/save-claude-notes 保存到 D:\xiao\WuKong\
```

对应脚本参数：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh \
  --latest \
  --notes-dir "D:/xiao/WuKong"
```

保存位置：

```text
D:/xiao/WuKong/YYYY-MM-DD.md
```

行为：

- 把目标当作文件夹目录；
- 在该目录下追加到当天 `YYYY-MM-DD.md`；
- 只影响本次保存；
- 不修改默认配置。

### `--latest` 如何找到 transcript

`--latest` 会根据当前工作目录推导 Claude Code project 目录，并在 `~/.claude/projects` 下查找最新的 `.jsonl` transcript。

如果自动发现失败，优先使用下面两种低 token 方式修正来源：

```bash
# 指定当前对话所属项目目录
SAVE_NOTE_CWD="D:/xiao/WuKong" \
  ~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --latest

# 直接指定 transcript JSONL 文件
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh \
  --latest \
  --transcript "C:/Users/10911/.claude/projects/D--xiao-WuKong/session.jsonl"
```

### 如果 `--latest` 失败

推荐 fallback 顺序：

1. 先用 `SAVE_NOTE_CWD` 修正项目目录；
2. 再用 `--transcript PATH` 指定 transcript；
3. 长内容优先用 `--question-file` / `--answer-file`；
4. 最后才用 stdin JSON。

stdin JSON 会把完整问答重新传给脚本，长回答时 token 消耗更高，只建议短内容使用：

```bash
printf '%s' "$PAYLOAD_JSON" | \
  ~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --stdin-json
```

## 📖 参数说明

| 参数 / 环境变量 | 说明 | 默认值 |
|------|------|--------|
| `--latest` | 从 Claude Code transcript 读取最近一轮问答，推荐默认使用 | 否 |
| `--output-file PATH` | 保存/追加到指定 `.md` 文件，例如 `D:/xiao/WuKong/空.md` | 无 |
| `--notes-dir PATH` | 本次保存到指定文件夹目录，并追加到其中的 `YYYY-MM-DD.md` | 无 |
| `--transcript PATH` | 为 `--latest` 指定 transcript JSONL 文件 | 自动发现 |
| `--stdin-json` | 从 stdin 读取 `{ "question": "...", "answer": "..." }`，作为 `--latest` 失败时的 fallback | 否 |
| `--question` | 要保存的提问内容，适合短文本和测试 | 可从 stdin 读取 |
| `--answer` | 要保存的回答内容，适合短文本和测试 | 必填，除非使用 `--latest` / `--stdin-json` / `--answer-file` |
| `--question-file` | 从文件读取提问 | 无 |
| `--answer-file` | 从文件读取回答 | 无 |
| `--config` | 指定配置文件路径 | `~/.claude/save-claude-notes/config.json` |
| `--dry-run` | 预览将写入的内容，不实际保存 | 否 |
| `--print-config` | 打印当前配置和当天目标文件 | 否 |
| `SAVE_NOTE_CONFIG` | 指定配置文件路径 | `~/.claude/save-claude-notes/config.json` |
| `SAVE_NOTE_TRANSCRIPT` | 为 `--latest` 指定 transcript JSONL 文件 | 自动发现 |
| `SAVE_NOTE_PROJECTS_DIR` | 指定 Claude Code projects 根目录 | `~/.claude/projects` |
| `SAVE_NOTE_CWD` | 指定用于 transcript 自动发现的项目目录 | 当前工作目录 |
| `SAVE_NOTE_ALLOW_SECRETS` | 设为 `1` 时允许保存疑似密钥内容 | 空，默认拒绝 |
| `SAVE_NOTE_NOW` | 测试用时间戳，格式 `YYYY-MM-DDTHH:MM:SS+08:00` | 当前系统时间 |

### 参数优先级

保存目标的优先级如下：

| 优先级 | 参数 / 配置 | 保存目标 |
| --- | --- | --- |
| 1 | `--output-file PATH` | 直接追加到指定文件 |
| 2 | `--notes-dir PATH` | 追加到 `PATH/YYYY-MM-DD.md` |
| 3 | config `notesDir` | 追加到 `<notesDir>/YYYY-MM-DD.md` |
| 4 | 无配置 | 追加到 `~/claude-notes/YYYY-MM-DD.md` |

如果同时传入 `--output-file` 和 `--notes-dir`，实际写入以 `--output-file` 为准。

### 输入来源不要混用

一次保存只使用一种问答来源：

- `--latest`
- `--stdin-json`
- `--question` + `--answer`
- `--question-file` + `--answer-file`

`--latest` 不能和显式 question/answer 输入混用。如果 `--latest` 选错内容，请单独改用 `SAVE_NOTE_CWD`、`--transcript PATH` 或文件/stdin fallback。

### Exit code

| Exit code | 含义 |
| --- | --- |
| `1` | 通用错误，或 wrapper 找不到 Python 3 |
| `2` | 参数、输入或配置错误 |
| `3` | 疑似密钥，拒绝保存 |
| `4` | 获取写入锁失败 |
| `5` | 目标 note 文件不安全 |
| `6` | 写入目录不安全 |

### 大小限制

- 配置文件最大 `64KB`；
- transcript 最大 `50MB`；
- lock owner metadata 最多读取 `4096 bytes`；
- 如果 transcript 太大，可以指定较小的 transcript，或改用 `--question-file` / `--answer-file` / stdin JSON fallback。

## 📊 输出格式

### 文件命名

默认保存和 `--notes-dir` 保存会写入当天 Markdown 文件：

```text
YYYY-MM-DD.md
```

例如：

```text
2026-06-23.md
```

如果使用 `--output-file`，则直接追加到指定文件，例如：

```text
D:/xiao/WuKong/空.md
```

### Markdown 内容格式

每次保存会追加一条记录：

```markdown
# [简洁准确的用户问题]

> 记录时间：YYYY-MM-DD HH:MM:SS

## [assistant answer1]

### [assistant answer-1]

### [assistant answer-2]

## [assistant answer2]
```

保存时会把用户问题优化成更适合作为一级标题的短标题：去掉礼貌性前缀，保留核心意图，过长时截断。

如果用户问题是多行文本，第一行非空内容会作为标题，后续问题正文会原样保留在标题下方、时间戳之前。保存前请先打码不希望写入笔记的上下文或敏感内容。

回答部分不再固定添加 `## Claude 回答`。无论原回答有没有 Markdown 标题，保存后的回答区域都会从二级标题开始：

| 原回答标题 | 保存后标题 |
| --- | --- |
| `# Title` | `## Title` |
| `## Title` | `## Title` |
| `### Title` 位于 `##` 下方 | `### Title` |
| 回答没有标题 | 第一段非空内容变成 `## ...` |

代码块里的标题不会被修改。

示例：

```markdown
# Claude Code 回答如何保存到本地？

> 记录时间：2026-06-23 14:35:12

## 使用 /save-claude-notes 保存

可以使用 `/save-claude-notes` 手动触发保存。

### 操作步骤

1. 输入 `/save-claude-notes`
2. 等待脚本返回保存路径
```

## ⚙️ 配置说明

配置文件只支持一个字段：

```json
{
  "notesDir": "~/claude-notes"
}
```

规则：

- 默认 `/save-claude-notes` 使用配置的 `notesDir`，保存到 `<notesDir>/YYYY-MM-DD.md`；
- `--notes-dir PATH` 只覆盖本次保存目录，优先级高于配置文件；
- `--output-file PATH` 直接保存到指定 `.md` 文件，不修改配置文件；
- `notesDir` 必须是字符串；
- `notesDir` 必须是绝对路径，或使用 `~/` 开头；
- Windows drive path（如 `D:/Notes/Claude`）只在 Windows Git Bash / MSYS / Cygwin 下视为绝对路径；
- 配置文件必须是小型 JSON 对象；
- 不支持额外字段；
- 目录不存在时会自动创建；
- 已存在的每日笔记只会追加，不会覆盖。

## 🔐 安全机制

脚本会默认检测并拒绝保存常见敏感内容，例如：

- `API_KEY=...`
- `TOKEN=...`
- `PASSWORD=...`
- `Authorization: Bearer ...`
- `sk-...`
- `ghp_...`
- `github_pat_...`
- `xoxb-...`
- `AIza...`
- AWS Access Key
- 私钥块：`-----BEGIN PRIVATE KEY-----`

如果确认内容可以保存，可显式覆盖：

```bash
SAVE_NOTE_ALLOW_SECRETS=1 \
  ~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --latest
```

> 建议优先打码或删除敏感信息，而不是使用覆盖开关。内置检测是 best-effort，不替代专业 secret scanner。避免把敏感长文本放进 `--question` / `--answer` 命令行参数，优先使用 `--latest`、文件输入或 stdin。

## 🔄 自动保存说明

`/save-claude-notes` 是**手动触发**的 Claude Code Skill。

如果想实现“每次问答结束后自动保存”，需要额外配置 Claude Code hooks。Skill 本身不会自动修改用户的 hook 配置，也不会后台常驻。

示意流程：

```text
手动模式：
用户输入 /save-claude-notes
→ 调用 save-claude-notes.sh --latest
→ 脚本从 transcript 读取最近一轮问答
→ 写入当天 Markdown

自动模式：
Claude Code hook 触发
→ 调用 save-claude-notes.sh --latest
→ 脚本从 transcript 读取最近一轮问答
→ 写入当天 Markdown
```

建议先使用手动模式，确认保存格式和目录符合预期后，再配置自动 hook。

## 🧪 测试

运行：

```bash
bash ~/.claude/skills/save-claude-notes/tests/test-save-claude-notes.sh
```

该命令会先运行 Python 单元测试，再运行 shell/CLI 集成测试。

测试覆盖：

- 创建每日 Markdown 文件
- 追加记录而不是覆盖
- 问题保存为一级标题
- 时间戳保存为引用块
- 回答标题从二级标题开始
- 无标题回答自动生成二级标题
- 多行 Markdown 内容
- `--latest` 从 transcript 读取最近一轮问答
- `--output-file` 保存到指定 `.md` 文件
- `--notes-dir` 保存到指定文件夹目录
- stdin JSON fallback 输入
- `--dry-run` 不写入
- `--print-config` 输出配置
- 配置 JSON 错误处理
- `~/` 路径展开
- Windows/Git Bash/Unix 项目路径编码
- 疑似密钥默认拒绝保存
- 显式允许保存疑似密钥
- 非法时间戳拒绝
- symlink / 非普通文件拒绝写入
- lock owner metadata 截断和安全读取
- stale lock 超时失败
- Bash wrapper 调用 Python 主脚本

## ❓ 常见问题

### Q: 输入 `/save-claude-notes` 没反应？

A: 确认目录路径正确，且目录下存在 `SKILL.md`：

```text
~/.claude/skills/save-claude-notes/SKILL.md
```

必要时重启 Claude Code，或检查 skills 列表是否包含 `save-claude-notes`。

### Q: 保存到了哪里？

A: 优先读取：

```text
~/.claude/save-claude-notes/config.json
```

如果该文件不存在，使用默认目录：

```text
~/claude-notes
```

可以运行：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh --print-config
```

### Q: 可以临时保存到其他目录吗？

A: 可以，使用 `--notes-dir`：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh \
  --latest \
  --notes-dir "D:/xiao/WuKong"
```

保存到：

```text
D:/xiao/WuKong/YYYY-MM-DD.md
```

`--notes-dir` 只影响本次保存，不会修改 `~/.claude/save-claude-notes/config.json`。

### Q: 可以保存到指定 `.md` 文件吗？

A: 可以，使用 `--output-file`：

```bash
~/.claude/skills/save-claude-notes/scripts/save-claude-notes.sh \
  --latest \
  --output-file "D:/xiao/WuKong/空.md"
```

这会直接追加到 `D:/xiao/WuKong/空.md`，不会按日期另建文件。

### Q: 会覆盖原来的笔记吗？

A: 不会。脚本使用追加写入，每次保存都会追加到当天文件末尾。

### Q: 能自动保存每次问答吗？

A: Skill 本身不能自动保存。需要额外配置 Claude Code hook 或外部包装脚本。

### Q: 为什么提示疑似密钥，拒绝保存？

A: 为避免把 API Key、Token、密码、私钥等敏感内容写入本地笔记。请先打码；如果确认要保存，可使用 `SAVE_NOTE_ALLOW_SECRETS=1`。

### Q: Windows 路径怎么写？

A: 在 `/save-claude-notes` 中可以写 Windows 路径，例如：

```text
/save-claude-notes 保存到 D:\xiao\WuKong\空.md
/save-claude-notes 保存到 D:\xiao\WuKong\
```

在 JSON 配置和脚本参数示例中，推荐写成 `/`：

```json
{
  "notesDir": "D:/Notes/claude"
}
```

不要在 JSON 中写成未转义的：

```json
{
  "notesDir": "D:\Notes\claude"
}
```

因为 JSON 中反斜杠需要转义。

## 📄 许可证

MIT License
