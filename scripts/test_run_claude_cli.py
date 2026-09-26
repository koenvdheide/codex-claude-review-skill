import json
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_claude_cli.py")
SKILL = SCRIPT.parent.parent / "SKILL.md"
REFERENCE = SCRIPT.parent.parent / "references" / "claude-cli.md"
OPENAI_YAML = SCRIPT.parent.parent / "agents" / "openai.yaml"
SIMPLICITY_BAR_MARKER = "Simplicity bar:"
EXPECTED_SIMPLICITY_BAR = (
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


class ClaudeCliWrapperTests(unittest.TestCase):
    def make_fake_claude(self, body):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        fake = root / "fake_claude.py"
        fake.write_text(textwrap.dedent(body), encoding="utf-8")
        return tmp, fake

    def run_wrapper(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=cwd,
            text=True,
            capture_output=True,
        )

    def test_print_mode_invokes_claude_with_plan_permissions_and_stdin_prompt(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import os
            import sys
            payload = {
                "argv": sys.argv[1:],
                "stdin": sys.stdin.read(),
                "cwd": os.getcwd(),
            }
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            print("FAKE CLAUDE REVIEW")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            out = Path(tmp.name) / "review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "artifact-review",
                "--question",
                "Review this plan.",
                "--context",
                "Plan body",
                "--instructions",
                "Focus on correctness.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "FAKE CLAUDE REVIEW")
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertEqual(payload["argv"][payload["argv"].index("--permission-mode"):payload["argv"].index("--permission-mode") + 2], ["--permission-mode", "plan"])
            self.assertEqual(payload["argv"][payload["argv"].index("--output-format"):payload["argv"].index("--output-format") + 2], ["--output-format", "text"])
            self.assertIn("--print", payload["argv"])
            self.assertIn("--no-session-persistence", payload["argv"])
            self.assertIn("Mode: artifact-review", payload["stdin"])
            self.assertIn("Question: Review this plan.", payload["stdin"])
            self.assertIn("Complete the review before returning a final answer", payload["stdin"])
            self.assertNotIn("Wait until the process exits", payload["stdin"])

    def test_analysis_passthrough_flags_are_forwarded(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"argv": sys.argv[1:]}, fh)
            print("FLAGS OK")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--model",
                "fable",
                "--effort",
                "xhigh",
                "--debug-file",
                "claude-debug.log",
                "--permission-mode",
                "acceptEdits",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            argv = json.loads(record.read_text(encoding="utf-8"))["argv"]
            self.assertEqual(argv[argv.index("--model"):argv.index("--model") + 2], ["--model", "fable"])
            self.assertEqual(argv[argv.index("--effort"):argv.index("--effort") + 2], ["--effort", "xhigh"])
            self.assertEqual(argv[argv.index("--debug-file"):argv.index("--debug-file") + 2], ["--debug-file", "claude-debug.log"])
            self.assertEqual(argv[argv.index("--permission-mode"):argv.index("--permission-mode") + 2], ["--permission-mode", "acceptEdits"])

    def test_analysis_omits_model_and_effort_by_default(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"argv": sys.argv[1:]}, fh)
            print("DEFAULTS OK")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            argv = json.loads(record.read_text(encoding="utf-8"))["argv"]
            self.assertNotIn("--model", argv)
            self.assertNotIn("--effort", argv)

    def test_change_recommending_modes_include_one_simplicity_bar(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"stdin": sys.stdin.read()}, fh)
            print("PROMPT CAPTURED")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            for mode in [
                "artifact-review",
                "plan-review",
                "diff-review",
                "red-team",
                "compare-decide",
            ]:
                with self.subTest(mode=mode):
                    result = self.run_wrapper(
                        "--claude-bin",
                        sys.executable,
                        "--claude-arg",
                        str(fake),
                        "--claude-arg=--record",
                        "--claude-arg",
                        str(record),
                        "--mode",
                        mode,
                        "--question",
                        "Review this.",
                    )

                    self.assertEqual(result.returncode, 0, result.stderr)
                    prompt = json.loads(record.read_text(encoding="utf-8"))["stdin"]
                    self.assertEqual(prompt.count(SIMPLICITY_BAR_MARKER), 1)
                    self.assertEqual(prompt.count(EXPECTED_SIMPLICITY_BAR), 1)
                    self.assertEqual(prompt.count("Architectural ownership:"), 1)

    def test_explain_mode_does_not_inject_change_recommendations(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"stdin": sys.stdin.read()}, fh)
            print("PROMPT CAPTURED")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "explain",
                "--question",
                "Explain this.",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            prompt = json.loads(record.read_text(encoding="utf-8"))["stdin"]
            self.assertNotIn(SIMPLICITY_BAR_MARKER, prompt)
            self.assertNotIn("Architectural ownership:", prompt)

    def test_analysis_rejects_literal_extra_effort_aliases(self):
        for effort in ["extra", "very-high"]:
            with self.subTest(effort=effort):
                result = self.run_wrapper(
                    "--mode",
                    "artifact-review",
                    "--question",
                    "Review this.",
                    "--model",
                    "fable",
                    "--effort",
                    effort,
                    "--dry-run",
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid choice", result.stderr)
                self.assertIn(effort, result.stderr)

    def test_prompt_file_is_resolved_against_repo_and_included_in_stdin(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            payload = {
                "argv": sys.argv[1:],
                "stdin": sys.stdin.read(),
            }
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            print("PROMPT FILE REVIEW")
            """
        )
        with tmp:
            repo = Path(tmp.name) / "repo"
            repo.mkdir()
            (repo / "bundle.md").write_text("PROMPT FILE BODY", encoding="utf-8")
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--repo",
                str(repo),
                "--mode",
                "artifact-review",
                "--prompt-file",
                "bundle.md",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertIn("Prompt file: bundle.md", payload["stdin"])
            self.assertIn("PROMPT FILE BODY", payload["stdin"])

    def test_composed_prompt_footer_has_single_blank_line_separator(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"stdin": sys.stdin.read()}, fh)
            print("PROMPT OK")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--context",
                "Context body",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            stdin = json.loads(record.read_text(encoding="utf-8"))["stdin"]
            self.assertIn("Context body\n\nReturn findings first", stdin)
            self.assertNotIn("Context body\n\n\nReturn findings first", stdin)

    def test_convergence_mode_composes_round_prompt_with_prior_findings(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            payload = {
                "argv": sys.argv[1:],
                "stdin": sys.stdin.read(),
            }
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            print("CONVERGENCE REVIEW")
            """
        )
        with tmp:
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "convergence",
                "--convergence-review-mode",
                "plan-review",
                "--round",
                "2",
                "--original-brief",
                "Build a tiny CLI line counter.",
                "--prior-findings",
                "F1 addressed: clarify whitespace. F2 skipped: color output out of scope.",
                "--question",
                "Review the revised plan.",
                "--context",
                "Plan v2 body",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertIn("--print", payload["argv"])
            self.assertIn("Mode: convergence", payload["stdin"])
            self.assertIn("Review mode: plan-review", payload["stdin"])
            self.assertIn("Round: 2", payload["stdin"])
            self.assertIn("Original one-sentence brief: Build a tiny CLI line counter.", payload["stdin"])
            self.assertIn("Previously identified findings:", payload["stdin"])
            self.assertIn("F1 addressed", payload["stdin"])
            self.assertIn("Gate 1", payload["stdin"])
            self.assertIn("Gate 2", payload["stdin"])
            self.assertIn("READY TO EXECUTE", payload["stdin"])
            self.assertIn("scope drift", payload["stdin"])
            self.assertIn("Plan v2 body", payload["stdin"])
            self.assertEqual(payload["stdin"].count(SIMPLICITY_BAR_MARKER), 1)
            self.assertEqual(payload["stdin"].count(EXPECTED_SIMPLICITY_BAR), 1)
            self.assertEqual(payload["stdin"].count("Architectural ownership:"), 1)

    def test_convergence_later_round_requires_brief_and_prior_findings(self):
        result = self.run_wrapper(
            "--claude-bin",
            "definitely-not-launched",
            "--mode",
            "convergence",
            "--round",
            "2",
            "--question",
            "Review this.",
            "--context",
            "Artifact",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("convergence rounds after round 1 require", result.stderr)

    def test_missing_prompt_file_fails_before_launching_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_wrapper(
                "--claude-bin",
                "definitely-not-launched",
                "--repo",
                tmp,
                "--mode",
                "artifact-review",
                "--prompt-file",
                "missing.md",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Prompt file not found", result.stderr)

    def test_invalid_utf8_prompt_file_fails_before_launching_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "bad.md"
            bad_file.write_bytes(b"\xff\xfe\x00")
            result = self.run_wrapper(
                "--claude-bin",
                "definitely-not-launched",
                "--repo",
                tmp,
                "--mode",
                "artifact-review",
                "--prompt-file",
                "bad.md",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not valid UTF-8", result.stderr)

    def test_missing_claude_binary_writes_marker_to_out_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "missing-binary-review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                "definitely-not-a-real-claude-binary",
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 127)
            self.assertIn("Claude CLI not found", result.stderr)
            self.assertIn("claude binary not found", out.read_text(encoding="utf-8"))

    def test_analysis_dry_run_has_no_default_wrapper_timeout(self):
        result = self.run_wrapper(
            "--mode",
            "artifact-review",
            "--question",
            "Review this.",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertIsNone(plan["process_timeout_seconds"])

    def test_ultrareview_dry_run_uses_minutes_timeout_and_omits_print_mode(self):
        result = self.run_wrapper(
            "--mode",
            "ultrareview",
            "--target",
            "main",
            "--timeout-minutes",
            "120",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertIsNone(plan["process_timeout_seconds"])
        self.assertEqual(plan["command"], ["claude", "ultrareview", "main", "--timeout", "120"])
        self.assertNotIn("--print", plan["command"])

    def test_ultrareview_requires_an_explicit_claude_timeout(self):
        result = self.run_wrapper(
            "--mode",
            "ultrareview",
            "--dry-run",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--timeout-minutes is required for ultrareview", result.stderr)
        self.assertIn("explicitly authorized", result.stderr)

    def test_ultrareview_live_path_uses_sentinel_and_final_output(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            sentinel_path = sys.argv[sys.argv.index("--expect-sentinel") + 1]
            with open(sentinel_path, "r", encoding="utf-8") as fh:
                sentinel = fh.read()
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"argv": sys.argv[1:], "sentinel": sentinel}, fh)
            print("ULTRAREVIEW OUTPUT")
            """
        )
        with tmp:
            out = Path(tmp.name) / "ultrareview.txt"
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--expect-sentinel",
                "--claude-arg",
                str(out),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "ultrareview",
                "--target",
                "main",
                "--timeout-minutes",
                "120",
                "--json",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertIn("in progress", payload["sentinel"])
            self.assertEqual(payload["argv"], ["--expect-sentinel", str(out), "--record", str(record), "ultrareview", "main", "--timeout", "120", "--json"])
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "ULTRAREVIEW OUTPUT")

    def test_ultrareview_warns_about_ignored_analysis_flags(self):
        result = self.run_wrapper(
            "--mode",
            "ultrareview",
            "--question",
            "ignored",
            "--context",
            "ignored context",
            "--prompt-file",
            "ignored.md",
            "--instructions",
            "ignored instructions",
            "--model",
            "sonnet",
            "--effort",
            "high",
            "--debug-file",
            "claude-debug.log",
            "--permission-mode",
            "acceptEdits",
            "--timeout-seconds",
            "60",
            "--timeout-minutes",
            "120",
            "--dry-run",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ignoring flags for ultrareview mode", result.stderr)
        self.assertIn("--question", result.stderr)
        self.assertIn("--context", result.stderr)
        self.assertIn("--prompt-file", result.stderr)
        self.assertIn("--instructions", result.stderr)
        self.assertIn("--model", result.stderr)
        self.assertIn("--effort", result.stderr)
        self.assertIn("--debug-file", result.stderr)
        self.assertIn("--permission-mode", result.stderr)
        self.assertIn("--timeout-seconds", result.stderr)

    def test_timeout_minutes_is_rejected_for_non_ultrareview_modes(self):
        result = self.run_wrapper(
            "--mode",
            "artifact-review",
            "--question",
            "Review this.",
            "--timeout-minutes",
            "120",
            "--dry-run",
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--timeout-minutes only applies to ultrareview", result.stderr)

    def test_timeout_reports_that_configured_timeout_was_reached(self):
        tmp, fake = self.make_fake_claude(
            """
            import time
            time.sleep(5)
            """
        )
        with tmp:
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--timeout-seconds",
                "1",
            )

            self.assertEqual(result.returncode, 124)
            self.assertIn("explicit wrapper process timeout", result.stderr)
            self.assertIn("Long-running silence before that point is not failure", result.stderr)

    def test_timeout_preserves_partial_stdout_in_out_file(self):
        tmp, fake = self.make_fake_claude(
            """
            import sys
            import time
            print("partial review output", flush=True)
            print("partial stderr", file=sys.stderr, flush=True)
            time.sleep(5)
            """
        )
        with tmp:
            out = Path(tmp.name) / "timeout-review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--timeout-seconds",
                "1",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 124)
            self.assertIn("partial stderr", result.stderr)
            self.assertIn("Captured partial output, if any, was written", result.stderr)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "partial review output")

    def test_timeout_without_captured_stdout_writes_marker_to_out_file(self):
        tmp, fake = self.make_fake_claude(
            """
            import time
            time.sleep(5)
            """
        )
        with tmp:
            out = Path(tmp.name) / "timeout-review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--timeout-seconds",
                "1",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 124)
            self.assertIn("no stdout captured", out.read_text(encoding="utf-8"))

    def test_out_file_has_in_progress_sentinel_while_process_runs(self):
        tmp, fake = self.make_fake_claude(
            """
            import json
            import sys
            sentinel_path = sys.argv[sys.argv.index("--expect-sentinel") + 1]
            with open(sentinel_path, "r", encoding="utf-8") as fh:
                sentinel = fh.read()
            with open(sys.argv[sys.argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"sentinel": sentinel}, fh)
            print("FINAL OUTPUT")
            """
        )
        with tmp:
            out = Path(tmp.name) / "review.txt"
            record = Path(tmp.name) / "record.json"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--claude-arg=--expect-sentinel",
                "--claude-arg",
                str(out),
                "--claude-arg=--record",
                "--claude-arg",
                str(record),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(record.read_text(encoding="utf-8"))
            self.assertIn("in progress", payload["sentinel"])
            self.assertIn("wrapper_process_timeout_seconds: none", payload["sentinel"])
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "FINAL OUTPUT")

    def test_nonzero_exit_preserves_stdout_in_out_file(self):
        tmp, fake = self.make_fake_claude(
            """
            import sys
            print("diagnostic output before failure")
            raise SystemExit(7)
            """
        )
        with tmp:
            out = Path(tmp.name) / "failed-review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 7)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "diagnostic output before failure")

    def test_nonzero_exit_writes_stderr_to_out_file_when_stdout_is_empty(self):
        tmp, fake = self.make_fake_claude(
            """
            import sys
            print("API Error: 400 role 'system' is not supported on this model", file=sys.stderr)
            raise SystemExit(1)
            """
        )
        with tmp:
            out = Path(tmp.name) / "failed-review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("role 'system' is not supported", result.stderr)
            self.assertIn("role 'system' is not supported", out.read_text(encoding="utf-8"))

    def test_out_file_parent_directories_are_created(self):
        tmp, fake = self.make_fake_claude(
            """
            print("NESTED OUTPUT")
            """
        )
        with tmp:
            out = Path(tmp.name) / "nested" / "dir" / "review.txt"
            result = self.run_wrapper(
                "--claude-bin",
                sys.executable,
                "--claude-arg",
                str(fake),
                "--mode",
                "artifact-review",
                "--question",
                "Review this.",
                "--out",
                str(out),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "NESTED OUTPUT")

    def test_skill_distinguishes_caller_waits_from_process_timeouts(self):
        skill = SKILL.read_text(encoding="utf-8")

        self.assertIn("caller-side wait", skill)
        self.assertIn("wrapper process timeout", skill)
        self.assertIn("caller-side execution handle", skill)
        self.assertIn("Do not set either timeout unless the user explicitly authorizes the limit", skill)
        self.assertNotIn("resume the same session with another maximum-length blocking wait", skill)
        self.assertNotIn("Normal analysis timeout defaults to 3600 seconds", skill)

    def test_skill_and_ui_metadata_make_simplicity_the_review_default(self):
        skill = SKILL.read_text(encoding="utf-8")
        metadata = OPENAI_YAML.read_text(encoding="utf-8")

        self.assertIn("Simplicity bar:", skill)
        self.assertIn("equal scrutiny", skill)
        self.assertIn("add-machinery findings", skill)
        self.assertIn(
            "Mode: artifact-review|plan-review|diff-review|red-team|compare-decide|explain|convergence",
            skill,
        )
        self.assertIn("For change-recommending modes only:", skill)
        self.assertIn("smallest sufficient change", metadata)

    def test_diff_review_examples_preserve_output_without_implicit_timeout(self):
        skill = SKILL.read_text(encoding="utf-8")
        examples = [
            match.group(0)
            for match in re.finditer(
                r'(?s)python "\$SkillDir\\scripts\\run_claude_cli\.py" `\s+--mode diff-review.*?```',
                skill,
            )
        ]

        self.assertGreaterEqual(len(examples), 2)
        for example in examples:
            self.assertIn("--out", example)
            self.assertNotIn("--timeout-seconds", example)

    def test_reference_documents_opt_in_timeout_model(self):
        reference = REFERENCE.read_text(encoding="utf-8")

        self.assertIn("Analysis modes have no wrapper process timeout by default", reference)
        self.assertIn("requires an explicit `--timeout-minutes`", reference)
        self.assertIn("does not add a second wrapper process timeout", reference)
        self.assertNotIn("Normal analysis timeout defaults to 3600 seconds", reference)
        self.assertNotIn("ultrareview timeout defaults to 120 minutes", reference.lower())


if __name__ == "__main__":
    unittest.main()
