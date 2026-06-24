# Examples

## `settings-config-check.example.json`

This is a minimal Claude Code hook example that verifies the `save-claude-notes` configuration at Stop time.

It does **not** save notes and does **not** automatically capture full Q&A transcripts. Automatic capture requires a hook that can reliably access both the user prompt and assistant response, or a transcript parser tailored to your Claude Code environment.

Copy hook snippets into your own `~/.claude/settings.json` only after reading and adapting them.
