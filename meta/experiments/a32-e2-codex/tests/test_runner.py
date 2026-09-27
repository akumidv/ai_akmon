import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

RUNNER_PATH = Path(__file__).parents[1] / "runner.py"
if not RUNNER_PATH.is_file():
    RUNNER_PATH = Path(__file__).with_name("runner.py")
SPEC = importlib.util.spec_from_file_location("a32_e2_runner", RUNNER_PATH)
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(runner)


class PromptTests(unittest.TestCase):
    def test_real_cohort_maps_to_recorded_trial_arms(self):
        labels, ids, data = runner.load_inputs(runner.RAW)
        self.assertEqual(len(ids), 161)
        self.assertEqual(sum(labels[i]["label"] == "FAIL" for i in ids), 84)
        self.assertEqual(
            sum(labels[i]["case"] == "P2-4" and "E2" in labels[i]["failed_elements"].split(",") for i in ids), 28
        )
        self.assertEqual(sum(labels[i]["label"] == "PASS" for i in ids), 77)
        for rid in ids:
            trial, arm, role = labels[rid]["trial"].lower(), labels[rid]["arm"], labels[rid]["_role"]
            path = runner.RAW / trial / "arms" / f"{arm}.{role}.system.txt"
            self.assertEqual(data[f"arm:{rid}"], path.read_text(encoding="utf-8"))

    def test_prompt_extractor_and_e1_prompt_are_exact(self):
        prompt = runner.extract_prompt(runner.DESIGN.read_text(encoding="utf-8"))
        self.assertIn('"verdict": "FLAG" or "OK"', prompt)
        message = runner.prompt_for("claude-small", "g1", {"g1": "exchange\n"}, prompt)
        self.assertEqual(message, prompt + "\n\n=== EXCHANGE ===\n\nexchange\n")

    def test_v1_uses_actual_delivered_arm_content(self):
        prompt = runner.extract_prompt(runner.DESIGN.read_text(encoding="utf-8"))
        data = {"g1": "exchange\n", "arm:g1": "ACTUAL A ARM\n"}
        message = runner.prompt_for("codex-mid-v1", "g1", data, prompt)
        self.assertIn("The instructions delivered to the agent for this exchange:\n\nACTUAL A ARM", message)
        self.assertNotIn("B_full", message)
        self.assertTrue(message.endswith("=== EXCHANGE ===\n\nexchange\n"))

    def test_scored_base_matches_pilot_output_contract(self):
        prompt = runner.extract_prompt(runner.DESIGN.read_text(encoding="utf-8"))
        message = runner.prompt_for("codex-strong-v0", "g1", {"g1": "x"}, prompt)
        self.assertIn(runner.PILOT_PROMPT_NEW, message)
        self.assertNotIn(runner.PILOT_PROMPT_OLD, message)


class ResultTests(unittest.TestCase):
    def freeze_test_manifest(self, artifact):
        path = runner.HERE / "runner.py"
        manifest = {
            "inputs_sha256": {str(path): runner.sha(path.read_bytes())},
            "cli_versions": {
                "claude": {"path": "/fake/claude", "version": "1", "binary_sha256": "test"},
                "codex": {"path": "/fake/codex", "version": "1", "binary_sha256": "test"},
                "qwen": {"path": "/fake/qwen", "version": "1", "binary_sha256": "test"},
            },
        }
        mf = artifact / "freeze/manifest.json"
        runner.write_json(mf, manifest)
        (mf.parent / "manifest.sha256").write_text(runner.sha(mf.read_bytes()) + "\n")

    def test_parser_requires_valid_integer_score_for_scored_arms(self):
        self.assertEqual(
            runner.parse_reply('{"verdict":"FLAG","mismatch_score":8,"findings":[]}', needs_score=True),
            ("FLAG", 8, None),
        )
        self.assertEqual(
            runner.parse_reply('{"verdict":"OK","findings":[]}', needs_score=True)[2],
            "invalid_or_missing_score",
        )
        self.assertEqual(
            runner.parse_reply('{"verdict":"OK","mismatch_score":11,"findings":[]}', needs_score=True)[2],
            "invalid_or_missing_score",
        )
        self.assertEqual(
            runner.parse_reply('{"verdict":"OK","findings":[]}', needs_score=False),
            ("OK", None, None),
        )

    def test_quota_is_a_circuit_breaker(self):
        assessed, halt = runner.classify(
            {"returncode": 1, "stderr": "HTTP 429 quota exceeded"},
            "codex",
            "gpt-6-sol",
            needs_score=True,
        )
        self.assertEqual((assessed["status"], halt), ("halted_quota", "quota"))

    def test_valid_model_prose_does_not_trip_quota_or_auth_circuit_breakers(self):
        for phrase in ("block unauthorized mutation", "quotation-like wording"):
            with self.subTest(phrase=phrase):
                attempt = {
                    "returncode": 0,
                    "stderr": "",
                    "reply": json.dumps(
                        {
                            "verdict": "FLAG",
                            "findings": [{"claim": "c", "evidence": "e", "why": phrase}],
                        }
                    ),
                    "actual_model": "gpt-reserve",
                }
                assessed, halt = runner.classify(attempt, "codex", "gpt-reserve", needs_score=False)
                self.assertEqual((assessed["status"], halt), ("valid", None))

    def test_exit_zero_provider_limits_without_model_provenance_still_halt(self):
        for message, status, reason in (
            ("Error: quota exceeded", "halted_quota", "quota"),
            ("Error: unauthorized", "halted_auth", "auth"),
            (
                '{"type":"error","error":{"type":"rate_limit_error","message":"Too many requests"}}',
                "halted_quota",
                "quota",
            ),
        ):
            with self.subTest(message=message):
                assessed, halt = runner.classify(
                    {"returncode": 0, "stderr": "", "reply": message, "actual_model": None},
                    "codex",
                    "gpt-reserve",
                    needs_score=False,
                )
                self.assertEqual((assessed["status"], halt), (status, reason))

    def test_unverified_prose_with_quota_or_auth_terms_is_not_provider_error(self):
        for reply in (
            "Malformed response discusses quotation-like wording.",
            "Malformed response discusses unauthorized mutation.",
        ):
            with self.subTest(reply=reply):
                assessed, halt = runner.classify(
                    {"returncode": 0, "stderr": "", "reply": reply, "actual_model": "gpt-reserve"},
                    "codex",
                    "gpt-reserve",
                    needs_score=False,
                )
                self.assertEqual((assessed["status"], halt), ("invalid_parse", None))

    def _qwen_attempt(self, home, cwd, records):
        usage_path = home / ".qwen/usage_record.jsonl"
        usage_path.parent.mkdir(parents=True, exist_ok=True)

        def append_usage(*args, **kwargs):
            with usage_path.open("a", encoding="utf-8") as stream:
                for row in records:
                    stream.write(json.dumps(row) + "\n")
            return subprocess.CompletedProcess(
                args=args[0],
                returncode=0,
                stdout='{"verdict":"OK","findings":[]}',
                stderr="",
            )

        with (
            patch.object(runner.Path, "home", return_value=home),
            patch.object(runner.subprocess, "run", side_effect=append_usage),
        ):
            return runner._call_qwen("qwen3.8-27b", "prompt", cwd)

    @staticmethod
    def _usage_record(session_id, project, tool_calls):
        return {
            "sessionId": session_id,
            "project": project,
            "models": {"qwen3.8-27b": {"requests": 1}},
            "tools": {"totalCalls": tool_calls},
        }

    def test_qwen_usage_correlation_ignores_unrelated_tool_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cwd = root / "qwen-cell" / "g1" / "attempt-1"
            project = str(cwd.resolve())
            attempt = self._qwen_attempt(
                root / "home",
                cwd,
                [
                    self._usage_record("unrelated-session", str(root / "other-project"), 5),
                    self._usage_record("own-session", project, 0),
                ],
            )
            self.assertEqual(attempt["qwen_project_cwd"], project)
            self.assertEqual([row["sessionId"] for row in attempt["usage_records"]], ["own-session"])
            self.assertEqual(attempt["tool_calls"], 0)
            assessed, halt = runner.classify(attempt, "qwen", "qwen3.8-27b", needs_score=False)
            self.assertEqual((assessed["status"], halt), ("valid", None))

    def test_qwen_correlated_tool_calls_invalidate_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cwd = root / "qwen-cell" / "g2" / "attempt-1"
            attempt = self._qwen_attempt(
                root / "home",
                cwd,
                [self._usage_record("own-session", str(cwd.resolve()), 2)],
            )
            assessed, halt = runner.classify(attempt, "qwen", "qwen3.8-27b", needs_score=False)
            self.assertEqual((assessed["status"], halt), ("invalid_tool_use", None))

    def test_qwen_missing_or_ambiguous_session_provenance_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cwd = root / "qwen-cell" / "g3" / "attempt-1"
            project = str(cwd.resolve())
            cases = (
                [],
                [
                    self._usage_record("session-a", project, 0),
                    self._usage_record("session-b", project, 0),
                ],
            )
            for rows in cases:
                with self.subTest(session_count=len(rows)):
                    attempt = self._qwen_attempt(root / f"home-{len(rows)}", cwd, rows)
                    self.assertIsNone(attempt["actual_model"])
                    self.assertIsNone(attempt["tool_calls"])
                    assessed, halt = runner.classify(attempt, "qwen", "qwen3.8-27b", needs_score=False)
                    self.assertEqual((assessed["status"], halt), ("invalid_model_provenance", None))

    def test_qwen_working_directory_is_unique_per_attempt(self):
        base = Path("/tmp/a32-qwen-test")
        paths = {
            runner._attempt_cwd(base, "qwen", "qwen-small", "g1", 1),
            runner._attempt_cwd(base, "qwen", "qwen-small", "g1", 1),
        }
        self.assertEqual(len(paths), 2)
        self.assertTrue(all(path.parent == base / "qwen-cwd/qwen-small/g1" for path in paths))

    def test_invalid_record_retries_and_preserves_prior_attempts(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td)
            prompt_path = artifact / "freeze/prompts/codex-mid-v0/g1.txt"
            prompt_path.parent.mkdir(parents=True)
            prompt_path.write_text("prompt")
            self.freeze_test_manifest(artifact)
            item = {
                "config": "codex-mid-v0",
                "run_id": "g1",
                "prompt": "prompts/codex-mid-v0/g1.txt",
                "prompt_sha256": runner.sha("prompt"),
                "input_sha256": runner.sha("input"),
            }
            output = runner.result_path(artifact, item["config"], "g1")
            output.parent.mkdir(parents=True)
            output.write_text(
                json.dumps(
                    {
                        "config": item["config"],
                        "run_id": "g1",
                        "status": "invalid_parse",
                        "attempts": [{"status": "invalid_parse", "reply": "old"}],
                    }
                )
            )
            valid_attempt = {
                "returncode": 0,
                "reply": '{"verdict":"FLAG","mismatch_score":8,"findings":[]}',
                "stderr": "",
                "actual_model": "gpt-5.6-terra",
                "model_provenance": "test",
            }
            with (
                patch.object(
                    runner,
                    "command_version",
                    return_value=runner.read_json(artifact / "freeze/manifest.json")["cli_versions"]["codex"],
                ),
                patch.object(runner, "call_one", return_value=valid_attempt),
            ):
                self.assertEqual(runner.run_cell(artifact, item, artifact / "cwd", retries=1), "valid")
            saved = json.loads(output.read_text())
            self.assertEqual(len(saved["attempts"]), 2)
            self.assertEqual(saved["attempts"][0]["reply"], "old")
            self.assertEqual(saved["score"], 8)

    def test_cli_change_after_first_cell_halts_before_next_call(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td)
            config = "claude-small"
            expected_cli = {"path": "/fake/claude", "version": "1", "binary_sha256": "old"}
            changed_cli = {"path": "/fake/claude", "version": "2", "binary_sha256": "new"}
            prompts = []
            for rid in ("g1", "g2"):
                prompt_rel = f"prompts/{config}/{rid}.txt"
                prompt_path = artifact / "freeze" / prompt_rel
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(f"prompt {rid}")
                prompts.append(
                    {
                        "config": config,
                        "route": "claude",
                        "model": runner.MODELS[config][1],
                        "run_id": rid,
                        "prompt": prompt_rel,
                        "prompt_sha256": runner.sha(f"prompt {rid}"),
                        "input_sha256": runner.sha(f"input {rid}"),
                    }
                )
            manifest = {
                "prompts": prompts,
                "cli_versions": {"claude": expected_cli},
                "inputs_sha256": {str(runner.HERE / "runner.py"): runner.sha((runner.HERE / "runner.py").read_bytes())},
            }
            manifest_path = artifact / "freeze/manifest.json"
            runner.write_json(manifest_path, manifest)
            (manifest_path.parent / "manifest.sha256").write_text(runner.sha(manifest_path.read_bytes()) + "\n")
            valid_attempt = {
                "returncode": 0,
                "reply": '{"verdict":"OK","findings":[]}',
                "stderr": "",
                "actual_model": runner.MODELS[config][1],
                "model_provenance": "test",
            }
            with (
                patch.object(runner, "command_version", side_effect=[expected_cli, expected_cli, changed_cli]),
                patch.object(runner, "call_one", return_value=valid_attempt) as call_one,
            ):
                counts = runner.run_family(artifact, "claude", limit=None, retries=1, workers=1)

            self.assertEqual(counts, {"valid": 1, "halted_version_mismatch": 1, "family_halted": 1})
            call_one.assert_called_once()
            first = runner.read_json(runner.result_path(artifact, config, "g1"))
            second = runner.read_json(runner.result_path(artifact, config, "g2"))
            self.assertEqual(first["attempts"][0]["cli_identity"], expected_cli)
            self.assertEqual(second["attempts"][0]["cli_identity"], changed_cli)
            halt = runner.read_json(artifact / "halted/claude.json")
            self.assertEqual(halt["reason"], "version_mismatch")
            self.assertEqual(halt["expected"], expected_cli)

    def test_frozen_prompt_digest_checked_before_call(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td)
            prompt_path = artifact / "freeze/prompts/claude-small/g1.txt"
            prompt_path.parent.mkdir(parents=True)
            prompt_path.write_text("changed")
            self.freeze_test_manifest(artifact)
            item = {
                "config": "claude-small",
                "run_id": "g1",
                "prompt": "prompts/claude-small/g1.txt",
                "prompt_sha256": runner.sha("expected"),
                "input_sha256": runner.sha("input"),
            }
            with self.assertRaises(ValueError):
                runner.run_cell(artifact, item, artifact / "cwd", retries=1)

    def test_missing_cells_block_gate(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td)
            ids = [f"r{i:03}" for i in range(161)]
            prompts = []
            for config, (route, model, _style, cutoff, _) in runner.MODELS.items():
                prompts.extend(
                    {
                        "config": config,
                        "route": route,
                        "model": model,
                        "run_id": rid,
                        "label": "PASS",
                        "failed_elements": "",
                        "case": "P2-1",
                        "prompt": f"prompts/{config}/{rid}.txt",
                        "prompt_sha256": "x",
                        "score_cutoff": cutoff,
                    }
                    for rid in ids
                )
            manifest = {"eligible_ids": ids, "cohort": {"n": 161}, "prompts": prompts}
            runner.write_json(artifact / "freeze/manifest.json", manifest)
            result = runner.summarize(artifact)
            self.assertFalse(result["full_gate_eligible"])
            self.assertFalse(result["configs"]["claude-small"]["gate_eligible"])
            self.assertIsNone(result["configs"]["claude-small"]["metrics"]["verdict"]["meets"])
            self.assertEqual(result["configs"]["claude-small"]["metrics"]["verdict"]["gate_status"], "incomplete")

    def test_run_family_rejects_stale_valid_output_before_skip(self):
        with tempfile.TemporaryDirectory() as td:
            artifact = Path(td)
            rid = "g1"
            config = "claude-small"
            prompt_rel = f"prompts/{config}/{rid}.txt"
            prompt = "prompt"
            prompt_path = artifact / "freeze" / prompt_rel
            prompt_path.parent.mkdir(parents=True)
            prompt_path.write_text(prompt)
            item = {
                "config": config,
                "route": "claude",
                "model": runner.MODELS[config][1],
                "run_id": rid,
                "prompt": prompt_rel,
                "prompt_sha256": runner.sha(prompt),
                "input_sha256": runner.sha("input"),
                "score_cutoff": None,
            }
            manifest = {
                "prompts": [item],
                "cli_versions": {"claude": runner.command_version("claude")},
                "inputs_sha256": {str(runner.HERE / "runner.py"): runner.sha((runner.HERE / "runner.py").read_bytes())},
            }
            mf = artifact / "freeze/manifest.json"
            runner.write_json(mf, manifest)
            (mf.parent / "manifest.sha256").write_text(runner.sha(mf.read_bytes()) + "\n")
            result = runner.result_path(artifact, config, rid)
            runner.write_json(
                result,
                {
                    "status": "valid",
                    "config": config,
                    "run_id": rid,
                    "prompt_sha256": item["prompt_sha256"],
                    "input_sha256": "stale",
                },
            )
            with self.assertRaisesRegex(ValueError, "stale output"):
                runner.run_family(artifact, "claude", limit=1, retries=1, workers=1)


if __name__ == "__main__":
    unittest.main()
