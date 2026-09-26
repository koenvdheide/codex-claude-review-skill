# Claude CLI Reference Notes

These notes are based on the local `claude --help` and `claude ultrareview --help` surface observed on this machine with Claude Code `2.1.197`.

## Non-Interactive Analysis

Use `claude --print` or `claude -p` for non-interactive output. Relevant flags:

| Flag | Use |
| --- | --- |
| `--print` / `-p` | Print response and exit. Useful for piped/stdin prompts. |
| `--no-session-persistence` | Avoid saving the review as a resumable session. |
| `--permission-mode plan` | Keep the nested run in planning/review mode. |
| `--output-format text` | Plain text output. |
| `--model <model>` | Optional model alias or full model name. Use `claude-opus-5-5` to select Opus 5.5 explicitly. The wrapper omits this by default so Claude Code can select its own route. |
| `--effort <level>` | Optional effort level: `low`, `medium`, `high`, `xhigh`, or `max`. The wrapper omits this by default; do not use `max` by default. |
| `--debug-file <path>` | Write Claude CLI debug details to a file for analysis-mode failure diagnosis. |
| `--add-dir <directories...>` | Allow extra directories only when live file access is intentionally needed. |

For substantial precomputed evidence, use the authoritative temp-file pipe example in `SKILL.md`. On Windows PowerShell, it uses `cmd /c` so the UTF-8 prompt file is streamed directly to `claude.exe` without wrapper prompt composition.

For Opus 5.5 reviews, use the [documented model ID](https://support.claude.com/en/articles/11940350-claude-code-model-configuration): `--model claude-opus-5-5 --effort xhigh`.

Use the wrapper for small analysis calls, convergence prompt construction, dry runs, explicit timeout/sentinel behavior, and ultrareview. See `SKILL.md` Failure Handling for the authoritative `role 'system' is not supported on this model` retry procedure.

Wrapper analysis modes: `artifact-review`, `plan-review`, `diff-review`, `red-team`, `compare-decide`, `explain`, and `convergence`. `convergence` runs one review round over an evolving artifact; pass `--convergence-review-mode`, `--round`, `--original-brief`, and `--prior-findings` when continuing after round 1.

## Ultrareview

`claude ultrareview [target]` runs a cloud-hosted multi-agent code review of the current branch, a PR, or a base branch.

Relevant flags:

| Flag | Use |
| --- | --- |
| `--timeout <minutes>` | Maximum minutes to wait for the review. Local help default: 30. |
| `--json` | Print raw `bugs.json` payload instead of formatted findings. |

The underlying CLI always has a finite ultrareview timeout and defaults to 30 minutes. The wrapper requires an explicit `--timeout-minutes` so Codex cannot silently accept that default. Set the limit only when the user explicitly authorizes it.

## Wrapper Process Limits

Analysis modes have no wrapper process timeout by default. `--timeout-seconds` adds an explicit wrapper limit only when the user authorizes it. On that timeout, the wrapper returns `124` and writes captured partial stdout to `--out`, or a timeout marker when Claude emitted no stdout.

Ultrareview requires an explicit `--timeout-minutes`. The wrapper passes that limit to the underlying `claude ultrareview --timeout` option and does not add a second wrapper process timeout. When Claude exits at its own limit, preserve the resulting stdout or stderr and treat the run as no completed review.

When `--out` is provided, the wrapper writes an in-progress sentinel before launch and replaces it with final stdout on success or stderr on nonzero failures without stdout. The sentinel records `wrapper_process_timeout_seconds: none` when the wrapper has no process timeout.

Normal analysis mode defaults to `--permission-mode plan`. It does not pass `--model` or `--effort` unless explicitly requested. For Opus 5.5 reviews through the wrapper, use `--model claude-opus-5-5 --effort xhigh`. In `ultrareview` mode, analysis-only flags are ignored and reported on stderr; `--json` remains available for the raw `bugs.json` payload.
