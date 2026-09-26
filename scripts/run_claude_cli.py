#!/usr/bin/env python3
"""Run Claude Code CLI as an external review/analysis partner."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ANALYSIS_MODES = {
    "artifact-review": "Review the artifact for correctness, regressions, missing evidence, and mismatch with the stated intent.",
    "plan-review": "Review the supplied implementation plan for missing steps, sequencing issues, rollback gaps, and operational risks.",
    "diff-review": "Review the supplied diff or change bundle. Findings first, ordered by severity, with concrete evidence.",
    "red-team": "Find the strongest objections, breakage modes, wrong assumptions, and missed simplifications. Give breakage and simplification equal scrutiny.",
    "compare-decide": "Compare the supplied options against the constraints and recommend one concrete path.",
    "explain": "Explain the supplied artifact, focusing on non-obvious behavior and likely pitfalls.",
}

CONVERGENCE_REVIEW_MODES = [
    "artifact-review",
    "plan-review",
    "diff-review",
    "red-team",
    "compare-decide",
]

SIMPLICITY_REVIEW_MODES = frozenset(CONVERGENCE_REVIEW_MODES)

ARCHITECTURAL_OWNERSHIP = (
    Path(__file__).resolve().parents[1] / "references" / "architectural-ownership.md"
).read_text(encoding="utf-8").strip()

SIMPLICITY_BAR = (
    "Simplicity bar: prefer deletion, inlining, or code that already exists. For any "
    "recommendation that adds a layer, wrapper, config knob, flag, interface, file, test, "
    "validation, or process step, name the reachable failure or stated requirement that the "
    "smaller option cannot cover, and drop the recommendation if you cannot. Treat a "
    "single-caller or single-implementation abstraction as suspect unless it establishes a "
    "current ownership or system boundary, or a necessary test seam tied to stated behavior "
    "or a reachable failure. Reject speculative generality. Keep defensive checks at trust "
    "and system boundaries. Tests and validation must cover stated behavior or a reachable "
    "failure, not framework behavior or hypothetical inputs. If the artifact already meets "
    "the brief, say so and do not invent work."
)

AFFIRMATIVE_VERDICTS = {
    "artifact-review": '"approve" / "ready" / "no must-fix or should-fix issues"',
    "plan-review": '"READY TO EXECUTE" / "approve" / "ready"',
    "diff-review": '"no regressions" / "approve"',
    "red-team": '"approve" / "no redesign-class problem" / "no regressions"',
    "compare-decide": '"Yes." / "executable as-is"',
}

REVIEW_COMPLETION_NOTE = (
    "Complete the review before returning a final answer. Do not infer failure from "
    "task complexity or lack of early findings. Return a final verdict or a concrete "
    "error based on the supplied evidence."
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Invoke Claude Code CLI for non-interactive analysis or ultrareview."
    )
    parser.add_argument(
        "--mode",
        choices=[*ANALYSIS_MODES.keys(), "convergence", "ultrareview"],
        default="artifact-review",
    )
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument(
        "--claude-arg",
        action="append",
        default=[],
        help="Extra argument inserted immediately after --claude-bin; useful for launchers or tests.",
    )
    parser.add_argument("--repo", default=".", help="Working directory for the Claude process.")
    parser.add_argument("--question", help="Specific question for Claude to answer.")
    parser.add_argument("--context", help="Inline artifact, diff, plan, or evidence bundle.")
    parser.add_argument("--prompt-file", help="File whose contents should be included as context.")
    parser.add_argument("--instructions", help="Additional focus or output instructions.")
    parser.add_argument(
        "--convergence-review-mode",
        choices=CONVERGENCE_REVIEW_MODES,
        help="Underlying review mode for --mode convergence.",
    )
    parser.add_argument(
        "--round",
        dest="round_number",
        type=positive_int,
        default=1,
        help="Convergence review round number. Default: 1.",
    )
    parser.add_argument(
        "--original-brief",
        help="Original one-sentence brief for convergence drift checks.",
    )
    parser.add_argument(
        "--prior-findings",
        help="Prior convergence findings with status labels such as addressed, skipped, or open.",
    )
    parser.add_argument("--out", help="Write Claude output to this file instead of stdout.")
    parser.add_argument(
        "--model",
        help="Optional Claude model alias or full model name. Omitted by default so Claude Code selects its own route.",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "xhigh", "max"],
        help="Optional effort level. Omitted by default so Claude Code selects its own route.",
    )
    parser.add_argument("--debug-file", help="Optional Claude CLI debug log file for analysis-mode calls.")
    parser.add_argument("--permission-mode", default="plan")
    parser.add_argument(
        "--timeout-seconds",
        type=positive_int,
        help=(
            "Optional wrapper process timeout for non-ultrareview modes. Omitted by default; "
            "set only when the user explicitly authorizes a finite limit."
        ),
    )
    parser.add_argument(
        "--target",
        help="Target passed to `claude ultrareview`, such as a PR number, URL, base branch, or branch.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=positive_int,
        help=(
            "Required finite timeout passed to `claude ultrareview`; invalid for other modes. "
            "Set only when the user explicitly authorizes the limit."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Pass --json to `claude ultrareview`.")
    parser.add_argument("--dry-run", action="store_true", help="Print the command plan as JSON and exit.")
    return parser


def read_text_file(path_value: str, repo: Path) -> str:
    path = Path(path_value)
    if not path.is_absolute():
        path = repo / path
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"Prompt file not found: {path}") from None
    except UnicodeDecodeError as exc:
        raise SystemExit(f"Prompt file is not valid UTF-8: {path}: {exc}") from exc


def append_common_prompt_parts(chunks: list[str], args: argparse.Namespace, repo: Path) -> None:
    if args.question:
        chunks.append(f"Question: {args.question}")
    if args.instructions:
        chunks.append(f"Instructions: {args.instructions}")
    if args.context:
        chunks.extend(["Context:", args.context])
    if args.prompt_file:
        chunks.extend([f"Prompt file: {args.prompt_file}", read_text_file(args.prompt_file, repo)])


def compose_convergence_prompt(args: argparse.Namespace, repo: Path) -> str:
    if args.round_number > 1 and not (args.original_brief and args.prior_findings):
        raise SystemExit(
            "convergence rounds after round 1 require --original-brief and --prior-findings."
        )

    review_mode = args.convergence_review_mode or "artifact-review"
    chunks = [
        "Mode: convergence",
        f"Review mode: {review_mode}",
        f"Task: Run one review round in a multi-round convergence loop over an evolving artifact.",
        REVIEW_COMPLETION_NOTE,
        SIMPLICITY_BAR,
        ARCHITECTURAL_OWNERSHIP,
        f"Round: {args.round_number}",
    ]
    if args.original_brief:
        chunks.append(f"Original one-sentence brief: {args.original_brief}")
    append_common_prompt_parts(chunks, args, repo)
    if args.prior_findings:
        chunks.extend(["Previously identified findings:", args.prior_findings])
    chunks.append(
        "\n".join(
            [
                "Convergence loop instructions:",
                "- This invocation is one review round only. Do not edit files.",
                "- Review the current artifact, then prepare the operator for review -> fix -> re-review.",
                "- Gate 1 after this output: the operator chooses yes-all / per-finding / skip for proposed fixes.",
                "- Gate 2 after selected fixes: the operator restates the original brief and chooses continue / stop / switch-mode.",
                "- Terminate only when verdict_text is affirmative for the review mode and no findings remain open, the user stops, or scope drift is detected.",
                f"- Affirmative verdict examples for {review_mode}: {AFFIRMATIVE_VERDICTS[review_mode]}.",
                "",
                "Scope drift checks:",
                "- Has the artifact grown substantially compared with the original brief?",
                "- Are new findings mostly about fixes added in prior rounds rather than the original artifact?",
                "- Are simplification findings being converted into extra machinery instead of stop-or-remove options?",
                "- Would another round deepen the artifact while moving away from what the user asked for?",
                "",
                "Return this structure:",
                "1. verdict_text",
                "2. open_findings, each with title, severity, evidence, and proposed_fix",
                "3. prior_findings_status, marking prior findings addressed / skipped / still-open",
                "4. scope_drift_assessment",
                "5. gate_1_recommendation",
                "6. gate_2_recommendation",
            ]
        )
    )
    return "\n\n".join(chunks)


def compose_prompt(args: argparse.Namespace, repo: Path) -> str:
    if args.mode == "convergence":
        return compose_convergence_prompt(args, repo)
    if args.mode not in ANALYSIS_MODES:
        raise SystemExit("Prompt composition is only valid for analysis modes.")
    chunks = [
        f"Mode: {args.mode}",
        f"Task: {ANALYSIS_MODES[args.mode]}",
        REVIEW_COMPLETION_NOTE,
    ]
    if args.mode in SIMPLICITY_REVIEW_MODES:
        chunks.extend([SIMPLICITY_BAR, ARCHITECTURAL_OWNERSHIP])
    append_common_prompt_parts(chunks, args, repo)
    chunks.append(
        "Return findings first when there are findings. Cite concrete files, lines, "
        "commands, or pasted evidence when possible. If evidence is insufficient, say "
        "what is missing. Do not edit files."
    )
    return "\n\n".join(chunks)


def build_command(args: argparse.Namespace, repo: Path) -> tuple[list[str], str | None, int | None]:
    if not repo.exists():
        raise SystemExit(f"Repository or working directory not found: {repo}")

    base = [args.claude_bin, *args.claude_arg]

    if args.mode == "ultrareview":
        ignored = []
        for flag_name in (
            "question",
            "context",
            "prompt_file",
            "instructions",
            "convergence_review_mode",
            "original_brief",
            "prior_findings",
            "model",
            "effort",
            "debug_file",
            "timeout_seconds",
        ):
            if getattr(args, flag_name):
                ignored.append("--" + flag_name.replace("_", "-"))
        if args.round_number != 1:
            ignored.append("--round")
        if args.permission_mode != "plan":
            ignored.append("--permission-mode")
        if ignored:
            print(f"Ignoring flags for ultrareview mode: {', '.join(ignored)}", file=sys.stderr)
        if args.timeout_minutes is None:
            raise SystemExit(
                "--timeout-minutes is required for ultrareview because Claude's ultrareview "
                "command always has a finite timeout; set it only when the user has explicitly "
                "authorized that limit."
            )
        timeout_minutes = args.timeout_minutes
        command = [*base, "ultrareview"]
        if args.target:
            command.append(args.target)
        command.extend(["--timeout", str(timeout_minutes)])
        if args.json:
            command.append("--json")
        return command, None, None

    if args.timeout_minutes is not None:
        raise SystemExit("--timeout-minutes only applies to ultrareview; use --timeout-seconds for analysis modes.")

    if not (args.question or args.context or args.prompt_file or args.instructions):
        raise SystemExit("Provide --question, --context, --prompt-file, or --instructions.")

    command = [
        *base,
        "--print",
        "--no-session-persistence",
        "--permission-mode",
        args.permission_mode,
        "--output-format",
        "text",
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.effort:
        command.extend(["--effort", args.effort])
    if args.debug_file:
        command.extend(["--debug-file", args.debug_file])
    return command, compose_prompt(args, repo), args.timeout_seconds


def to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def write_output(out_path: str | None, stdout: str) -> None:
    if out_path:
        path = Path(out_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(stdout, encoding="utf-8")
    else:
        sys.stdout.write(stdout)


def initialize_out_file(out_path: str | None, mode: str, timeout_seconds: int | None) -> None:
    if not out_path:
        return
    timeout_text = "none" if timeout_seconds is None else str(timeout_seconds)
    sentinel = (
        "[in progress; populated when wrapper exits]\n"
        f"mode: {mode}\n"
        f"wrapper_process_timeout_seconds: {timeout_text}\n"
    )
    write_output(out_path, sentinel)


def timeout_output(stdout: str) -> str:
    return stdout if stdout else "[timed out; no stdout captured]\n"


def out_file_output(stdout: str, stderr: str, returncode: int) -> str:
    if returncode == 0 or not stderr:
        return stdout
    if not stdout:
        return stderr
    separator = "" if stdout.endswith("\n") else "\n"
    return f"{stdout}{separator}[stderr]\n{stderr}"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    command, stdin_text, process_timeout_seconds = build_command(args, repo)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "cwd": str(repo),
                    "command": command,
                    "process_timeout_seconds": process_timeout_seconds,
                    "stdin_chars": len(stdin_text or ""),
                },
                indent=2,
            )
        )
        return 0

    initialize_out_file(args.out, args.mode, process_timeout_seconds)

    try:
        result = subprocess.run(
            command,
            cwd=repo,
            input=stdin_text,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=process_timeout_seconds,
        )
    except FileNotFoundError:
        if args.out:
            write_output(args.out, f"[claude binary not found: {args.claude_bin}]\n")
        print(f"Claude CLI not found: {args.claude_bin}", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired as exc:
        stdout = to_text(exc.stdout)
        stderr = to_text(exc.stderr)
        if stderr:
            sys.stderr.write(stderr)
        if args.out:
            write_output(args.out, timeout_output(stdout))
        elif stdout:
            sys.stdout.write(stdout)
        print(
            "Claude CLI reached the explicit wrapper process timeout. Long-running silence "
            "before that point is not failure; this message means the user-authorized wrapper "
            "limit was reached. Captured partial output, if any, was written to the configured "
            "output destination.",
            file=sys.stderr,
        )
        return 124

    if result.stderr:
        sys.stderr.write(result.stderr)
    if args.out:
        write_output(args.out, out_file_output(result.stdout, result.stderr, result.returncode))
    else:
        write_output(None, result.stdout)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
