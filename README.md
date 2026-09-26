# Claude review skill for Codex

A Codex skill that calls the local Claude Code CLI for independent reviews of plans, diffs, documents, and technical decisions. The Python wrapper builds review prompts, preserves process diagnostics, and supports individual rounds of a review-and-revise workflow.

This package runs inside Codex. The separate [claude-reviewer](https://github.com/koenvdheide/claude-reviewer) repository provides a QA reviewer subagent for Claude Code.

## Requirements

- Codex with local skill support.
- Python 3.10 or later; the wrapper uses only the standard library.
- An installed and authenticated Claude Code CLI available as `claude`, or supplied with `--claude-bin`.

The CLI's available models and review commands depend on its version and account access. The reference notes record an observed CLI version; check local CLI help when capabilities differ. Review requests send the supplied material to the service configured in Claude Code and use that account's usage allowance.

## Install

Clone the repository as the `claude` directory in your Codex skills directory. In PowerShell, using the default Codex home:

```powershell
git clone https://github.com/koenvdheide/codex-claude-review-skill.git "$env:USERPROFILE/.codex/skills/claude"
```

If you set `CODEX_HOME`, use its `skills/claude` subdirectory instead. Preserve any existing `claude` skill before installing. Start a new Codex chat after installation.

## Use

Ask Codex:

```text
Use $claude to review this implementation plan and verify the findings against the repository.
```

The skill retains the invocation name `$claude`. Its [instructions](SKILL.md) cover artifact and plan review, diff review, red-team critique, comparisons, explanations, convergence rounds, and Claude ultrareview.

To inspect a wrapper command without calling Claude, run this from the repository root:

```powershell
python scripts/run_claude_cli.py --mode plan-review --question "Review this plan for correctness and unnecessary complexity." --prompt-file path/to/plan.md --dry-run
```

Remove `--dry-run` and add `--out path/to/review.txt` to request a review. For large evidence bundles, follow the direct file-pipe procedure in [SKILL.md](SKILL.md).

Analysis defaults to Claude's `plan` permission mode. The wrapper does not select a model, effort level, or process timeout unless requested. Ultrareview requires an explicitly authorized timeout. These are review instructions and CLI settings; independently verify material findings before applying them.

## Validation

From the repository root:

```powershell
python -B -m unittest discover -s scripts -p "test_*.py" -v
```

The tests use fake CLI processes and require no model credentials. They exercise wrapper behavior; they do not establish compatibility with every live CLI version or the quality of model reviews. The initial package was checked on Windows with Python 3.14.

## Related skill

[Antigravity review for Codex](https://github.com/koenvdheide/codex-antigravity-review-skill) calls Gemini through the Antigravity CLI. Each package includes its own architectural ownership checklist so it can be installed independently.

## License

[MIT](LICENSE).
