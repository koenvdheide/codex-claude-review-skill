---
name: claude
description: Use when Codex should call the local Claude Code CLI as an independent analysis or review partner, including plan review, diff review, red-team critique, artifact review, convergence review loops, compare/decide tasks, Claude ultrareview, or operational help invoking Claude CLI reliably. Trust Claude to deliver a result by default; do not stop a running Claude process or configure a finite process timeout unless the user explicitly authorizes it. While Claude runs, use the longest supported blocking wait and do not poll it on a recurring schedule.
---

# Claude CLI

## Overview

Use this skill to ask a separate Claude Code CLI process for an independent read on a concrete artifact, diff, plan, or decision. Gather local facts first, send the smallest useful evidence bundle, and treat Claude's output as review evidence to verify before presenting or applying. For reviews that can recommend changes, make the smallest sufficient change the default and require added machinery to earn its keep.

## When to Use

- **Artifact review:** plans, specs, generated reports, prompts, skill docs, migration notes.
- **Diff review:** staged changes, uncommitted work, base-branch deltas, or precomputed evidence bundles.
- **Red-team:** challenge an approach, security-sensitive workflow, or high-cost decision.
- **Convergence:** repeat review -> fix -> re-review on an evolving spec, plan, or design until an affirmative verdict, user stop, or scope drift.
- **Compare/decide:** evaluate a few concrete options against stated constraints.
- **Explain:** get another model's explanation of a supplied artifact.
- **Ultrareview:** run Claude's cloud-hosted multi-agent branch/PR/base-branch review.

Do not use this for trivial lookups, mechanical edits, prompts containing secrets, or broad "think about this repo" requests before local inspection. Do not fire Claude and another external CLI on the same prompt without a concrete reason.

## Long Reviews

Claude CLI reviews can take a long time, especially `claude ultrareview` and large artifact or repo reviews. Trust Claude to deliver a result by default. Do not treat silence, lack of emitted stdout, or lack of early findings as a timeout or failure.

Keep these two mechanisms distinct:

- A **caller-side wait** only controls how long Codex blocks before the execution tool returns control. If the execution handle remains alive, Claude is still running; re-wait on that handle.
- A **process timeout** ends the Claude process. Analysis modes have no wrapper process timeout by default. `--timeout-seconds` enables one for analysis. The underlying `claude ultrareview` command always requires a finite timeout, so the wrapper requires an explicit `--timeout-minutes` and passes it to Claude without adding a second wrapper process timeout. Do not set either timeout unless the user explicitly authorizes the limit.

Once Claude is running, let it continue until it exits on its own or the user explicitly tells Codex to stop it. Do not kill, terminate, retry, read partial output as final, or delete output files while it is running. If a user-authorized process timeout is reached, report the resulting process exit and preserved output; do not treat it as a completed review or restart automatically.

When `--out` is used, the wrapper writes an in-progress sentinel before launching Claude, then replaces it when Claude exits. The file is not streamed incrementally. On success, final stdout is written. On nonzero exit without stdout, stderr is written so API validation errors are preserved. When an explicit analysis `--timeout-seconds` limit is reached, captured partial stdout is written before the wrapper returns `124`; if Claude had not flushed stdout, the wrapper writes a timeout marker. An ultrareview timeout is handled by Claude's own command and reaches the wrapper as an ordinary process exit.

Do not poll a running Claude process on a recurring schedule. After confirming the process started, wait on its caller-side execution handle, such as the PTY or process-session ID returned by the execution tool, and use the longest blocking wait the tool supports. This execution handle is not a Claude Code conversation session and is unaffected by `--no-session-persistence`. Never choose a 1-2 minute wait when a longer wait is available. If the maximum wait returns while the execution handle is still alive, call the tool's wait or resume operation again on that same handle without reading the sentinel or output file, running a separate status command, or sending a user update. Do not narrate unchanged state. Check sooner only when the user asks for status or a concrete signal indicates completion or failure.

## Large Bundles: Temp-File Pipe

For substantial artifact, diff, prose, or repo-context reviews, make a UTF-8 prompt bundle in a temp file and pipe that file directly into `claude.exe`. This path preserves the full bundle and removes wrapper prompt-composition variables from the diagnosis.

Use `cmd /c` for input redirection on Windows PowerShell:

```powershell
$Prompt = "C:\path\to\review-bundle.md"
$Out = "C:\path\to\claude-review.txt"
$Claude = (Get-Command claude).Source
$Command = '"' + $Claude + '" --print --no-session-persistence ' +
  '--permission-mode plan --output-format text ' +
  '< "' + $Prompt + '" > "' + $Out + '" 2>&1'
cmd /c $Command
if ($LASTEXITCODE -ne 0) {
  Get-Content $Out -ErrorAction SilentlyContinue
  throw "Claude review failed with exit code $LASTEXITCODE"
}
```

Build the prompt bundle yourself: include the question, instructions, exact evidence, the simplicity bar from [Prompt Shape](#prompt-shape) and the [architectural ownership checklist](references/architectural-ownership.md) for every change-recommending review, and a request for a final verdict or concrete error. Do not reduce evidence fidelity just to fit the wrapper. The temp-file pipe removes wrapper prompt-composition variables, but it is not a guaranteed fix for backend/model routing errors such as `role 'system' is not supported on this model`. If the user asks for Fable on a direct temp-file pipe, pass Claude Code's native flags, for example `--model fable --effort xhigh`. If a backend/model error appears, preserve the output file, retry once without any explicit `--model` or `--effort` if they were used, then split or narrow the bundle before changing models.

## Wrapper

Use the bundled wrapper for smoke tests, small analysis calls, dry-run command inspection, timeout/sentinel behavior, and `ultrareview`. Do not use it as the first choice for large precomputed bundles.

```powershell
$SkillDir = Join-Path $env:USERPROFILE ".codex\skills\claude"
python "$SkillDir\scripts\run_claude_cli.py" `
  --mode artifact-review `
  --question "Review this implementation plan." `
  --prompt-file "C:\path\to\plan.md" `
  --instructions "Focus on correctness, missing tests, and over-engineering." `
  --out "C:\path\to\claude-review.txt"
```

Review a precomputed diff bundle:

```powershell
$SkillDir = Join-Path $env:USERPROFILE ".codex\skills\claude"
python "$SkillDir\scripts\run_claude_cli.py" `
  --mode diff-review `
  --repo "C:\path\to\repo" `
  --prompt-file ".codex-review-bundle.md" `
  --out "C:\path\to\claude-diff-review.txt"
```

Use Fable at `xhigh` effort when the user asks for that model:

```powershell
$SkillDir = Join-Path $env:USERPROFILE ".codex\skills\claude"
python "$SkillDir\scripts\run_claude_cli.py" `
  --mode diff-review `
  --repo "C:\path\to\repo" `
  --prompt-file ".codex-review-bundle.md" `
  --model fable `
  --effort xhigh `
  --out "C:\path\to\claude-fable-review.txt"
```

Run one round in a convergence loop:

```powershell
$SkillDir = Join-Path $env:USERPROFILE ".codex\skills\claude"
python "$SkillDir\scripts\run_claude_cli.py" `
  --mode convergence `
  --convergence-review-mode plan-review `
  --round 2 `
  --original-brief "Build the import wizard without changing export behavior." `
  --prior-findings "F1 addressed: added rollback step. F2 skipped: export rewrite out of scope." `
  --question "Review the revised plan for convergence." `
  --prompt-file "C:\path\to\plan.md" `
  --out "C:\path\to\claude-convergence-round-2.txt"
```

Run Claude ultrareview after the user explicitly authorizes a 120-minute Claude-side timeout:

```powershell
$SkillDir = Join-Path $env:USERPROFILE ".codex\skills\claude"
python "$SkillDir\scripts\run_claude_cli.py" `
  --mode ultrareview `
  --repo "C:\path\to\repo" `
  --target main `
  --timeout-minutes 120 `
  --out "C:\path\to\ultrareview.txt"
```

Use `--dry-run` before the first run in an unfamiliar environment. For normal analysis modes, including `convergence`, the wrapper uses `claude --print --no-session-persistence --output-format text`, defaults to `--permission-mode plan`, and passes the review prompt over stdin. It does not set `--model`, `--effort`, or a wrapper process timeout unless you explicitly pass those flags. Leave them omitted unless the user asks for a model/effort or explicitly authorizes a finite `--timeout-seconds`. When the user asks for the Fable model at high review effort, pass `--model fable --effort xhigh`. Do not use `max` effort by default. Add `--debug-file <path>` when reproducing CLI/API routing failures.

For `ultrareview`, `--timeout-minutes` is required because the underlying Claude command always has a finite timeout; obtain explicit user authorization for the limit. The wrapper passes that value to Claude and does not add a second wrapper process timeout. Omit `--target` to review the current branch. Add `--json` to return Claude's raw `bugs.json` payload. Analysis-only flags (`--question`, `--context`, `--prompt-file`, `--instructions`, `--convergence-review-mode`, `--original-brief`, `--prior-findings`, `--round`, `--model`, `--effort`, `--debug-file`, `--timeout-seconds`, and non-default `--permission-mode`) are ignored in `ultrareview` mode; the wrapper prints a warning when they are supplied.

## Prompt Shape

Default to this shape:

```text
Mode: artifact-review|plan-review|diff-review|red-team|compare-decide|explain|convergence
Question: concrete question Claude should answer
Instructions: focus area and expected output shape
Context: smallest useful artifact, diff, logs, or plan

For change-recommending modes only:
Simplicity bar: prefer deletion, inlining, or code that already exists. For any
recommendation that adds a layer, wrapper, config knob, flag, interface, file,
test, validation, or process step, name the reachable failure or stated
requirement that the smaller option cannot cover, and drop the recommendation
if you cannot. Treat a single-caller or single-implementation abstraction as
suspect unless it establishes a current ownership or system boundary, or a
necessary test seam tied to stated behavior or a reachable failure. Reject
speculative generality. Keep defensive checks at trust and system boundaries.
Tests and validation must cover stated behavior or a reachable failure, not
framework behavior or hypothetical inputs. If the artifact already meets the
brief, say so and do not invent work.

Return findings first when there are findings. Cite concrete files, lines,
commands, or pasted evidence when possible. If evidence is insufficient, say
what is missing. Do not edit files.
```

The wrapper injects the simplicity bar once for `artifact-review`, `plan-review`, `diff-review`, `red-team`, `compare-decide`, and `convergence`. It does not inject change recommendations into `explain`, and `ultrareview` does not accept analysis prompts. The wrapper also adds a completion note asking Claude to return a final verdict or a concrete error. Caller-side waiting behavior stays in this skill; do not inject instructions that ask Claude to manage Codex's wait loop.

## Architectural Ownership

The wrapper injects [this checklist](references/architectural-ownership.md) into every change-recommending mode, including convergence. Include its full text outside the evidence in direct temp-file prompt bundles. It applies to code and technical plans; `explain` is unchanged.

The checklist adapts the global Architectural ownership instruction. Each review skill carries its own copy so it remains independently installable; keep the Claude and Antigravity copies aligned when updating this policy.

`ultrareview` cannot accept this section. When using it for an architectural review, also run a prompted `diff-review` with the checklist; do not claim that `ultrareview` received custom instructions.

## Review Bias: Simplicity First

Give breakage and simplification equal scrutiny in red-team reviews. Hunt for single-caller interfaces whose only justification is future reuse, forwarding wrappers, unused configuration or flags, generality for unstated requirements, redundant validation or retries inside already-constrained call paths, unnecessary caches or bookkeeping, duplicated sources of truth, and ceremony such as scaffolding files, docs that restate code, or tests of mocks and framework behavior. Preserve a current ownership or system boundary, or a necessary test seam, when it is tied to stated behavior or a reachable failure.

For each simplification finding, say what to cut, merge, or flatten and why removal is safe. Prefer the biggest safe cut. If nothing should be removed, say `nothing to cut` and do not pad the section. Do not remove defensive code at trust or system boundaries, explanatory comments whose reason is not obvious from the code, or anything whose removal sacrifices clarity for line count.

## Convergence Mode

Use `--mode convergence` when reviewing an artifact that will go through multiple revisions, especially specs, plans, and designs. The wrapper runs one review round at a time; Codex applies selected fixes, then invokes another round if the user chooses to continue.

Use `--convergence-review-mode` to name the underlying review style: `artifact-review`, `plan-review`, `diff-review`, `red-team`, or `compare-decide`. For round 2 and later, pass both:

- `--original-brief`: the original one-sentence goal, restated every round to detect drift.
- `--prior-findings`: prior findings with statuses such as `addressed`, `skipped`, or `still-open`.

After each convergence output:

1. Verify findings against local facts before editing.
2. Gate fixes with the user or existing workflow: `yes-all`, `per-finding`, or `skip`.
3. Apply selected fixes.
4. Gate continuation: `continue`, `stop`, or `switch-mode`.

Stop the loop when Claude gives an affirmative verdict for the review mode and no findings remain open, the user stops, or scope drift appears. Scope drift signs include large artifact growth, new findings mostly caused by prior-round fixes, or simplification findings being converted into extra machinery instead of stop-or-remove options.

## Handling Output

- Verify every material finding against local files, commands, or pasted evidence before acting on it.
- Down-rank add-machinery findings. For any recommendation that adds code, configuration, files, tests, or process, state the smallest fix and whether removing something closes the same hole. Reject or mark optional a finding whose only payoff is ceremony.
- Quote evaluative language carefully; do not turn "might miss" into "misses" or "I would consider" into "requires."
- Count inline citations in prose as well as bullet lists.
- If Claude disagrees with your approach, present both positions with the evidence.
- If output is generic, retry once with a narrower artifact and question. Do not loop indefinitely.
- For high-stakes summaries, self-review the summary against the source output before presenting it.

## Failure Handling

- `Claude CLI not found`: run `Get-Command claude` on Windows PowerShell or `command -v claude` on Unix; install or fix PATH. `where.exe claude` is also useful on Windows when PATH resolution differs between shells.
- Authentication failure: run `claude auth login` or the relevant Claude Code login/setup flow outside the wrapper.
- Workspace trust or permission noise: use precomputed evidence in `--prompt-file`; avoid asking the nested CLI to explore the repo live.
- Explicit analysis wrapper timeout: `--timeout-seconds` returns `124` only when that user-authorized limit is reached. Slow silence before that is not failure.
- Ultrareview timeout: the underlying Claude CLI exits when the user-authorized `--timeout-minutes` limit is reached. The wrapper does not add a second process timeout. Treat the timeout output as no completed review.
- `role 'system' is not supported on this model`: this is an API validation failure, not a review result. Preserve the exact command and output file. Retry once without explicit `--model` or `--effort` if either was used; if it still fails, split the prompt bundle or use a narrower task. Treat the failed run as no review.
- `ultrareview` CLI default: local help shows a 30-minute default, but the wrapper requires an explicit `--timeout-minutes` so Codex cannot silently accept that limit.

Read `references/claude-cli.md` when exact command-surface notes or local help details matter.
