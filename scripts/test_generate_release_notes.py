"""验证更新说明请求、结构化输出、失败处理与真实 Git 提交范围。"""

import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError


SPEC = importlib.util.spec_from_file_location("notes", Path(__file__).with_name("generate-release-notes.py"))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_notes():
    return {
        "zh": {"features": ["支持语音输入。"], "fixes": [], "improvements": []},
        "en": {"features": ["Added voice input."], "fixes": [], "improvements": []},
    }


def api_response(value=None, finish="stop"):
    return io.BytesIO(json.dumps({"choices": [{
        "finish_reason": finish,
        "message": {"content": json.dumps(value or sample_notes(), ensure_ascii=False)},
    }]}).encode("utf-8"))


class ReleaseNotesTests(unittest.TestCase):
    def test_request_uses_deepseek_non_thinking_json_and_commit_bodies(self):
        captured = []
        def respond(request, timeout):
            captured.append((request, timeout))
            return api_response()
        commits = ["feat(input): voice input\nSupports short recordings."]
        with patch.object(MODULE, "urlopen", side_effect=respond):
            self.assertEqual(MODULE.request_notes(commits, "test-key"), sample_notes())
        request, timeout = captured[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(payload["model"], "deepseek-flash")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual([m["role"] for m in payload["messages"]], ["system", "user"])
        self.assertEqual(json.loads(payload["messages"][1]["content"]), {"commits": commits})
        self.assertEqual(timeout, 60)

    def test_retries_transient_http_and_empty_responses(self):
        transient = HTTPError(MODULE.ENDPOINT, 503, "unavailable", {}, None)
        with patch.object(MODULE, "urlopen", side_effect=[transient, io.BytesIO(b"{}"), api_response()]) as request, \
             patch.object(MODULE.time, "sleep"):
            self.assertEqual(MODULE.request_notes(["feat: input"], "key"), sample_notes())
        self.assertEqual(request.call_count, 3)

    def test_auth_error_is_reported_without_retrying_or_exposing_response(self):
        error = HTTPError(MODULE.ENDPOINT, 401, "sensitive response", {}, None)
        with patch.object(MODULE, "urlopen", side_effect=error) as request:
            with self.assertRaisesRegex(RuntimeError, "^DeepSeek HTTP 401$"):
                MODULE.request_notes(["feat: input"], "key")
        self.assertEqual(request.call_count, 1)

    def test_truncated_content_is_rejected(self):
        with patch.object(MODULE, "urlopen", side_effect=lambda *args, **kwargs: api_response(finish="length")), \
             patch.object(MODULE.time, "sleep"):
            with self.assertRaises(RuntimeError):
                MODULE.request_notes(["feat: input"], "key")

    def test_network_failure_keeps_bounded_attempts(self):
        with patch.object(MODULE, "urlopen", side_effect=URLError("network")) as request, \
             patch.object(MODULE.time, "sleep"):
            with self.assertRaises(RuntimeError):
                MODULE.request_notes(["feat: input"], "key")
        self.assertEqual(request.call_count, 3)

    def test_rejects_missing_languages_categories_and_translation_mismatch(self):
        invalid = [None, {"zh": {}}, {"zh": {}, "en": {}}]
        mismatch = sample_notes()
        mismatch["en"]["features"] = []
        invalid.append(mismatch)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                MODULE.validate_notes(value)

    def test_render_omits_empty_categories_and_keeps_both_languages(self):
        rendered = MODULE.render_notes(sample_notes())
        self.assertIn("- 支持语音输入。", rendered)
        self.assertIn("- Added voice input.", rendered)
        self.assertNotIn("### Fixes", rendered)
        self.assertLess(rendered.index("支持语音输入"), rendered.index("Added voice input"))

    def test_empty_commit_range_does_not_call_api(self):
        with patch.object(MODULE, "urlopen") as request:
            notes, generated = MODULE.generate([], "key", strict=True)
        request.assert_not_called()
        self.assertFalse(generated)
        self.assertIn("没有需要单独说明", notes)

    def test_missing_key_falls_back_and_strict_preview_fails(self):
        notes, generated = MODULE.generate(["feat: input"], "")
        self.assertFalse(generated)
        self.assertIn("更新说明暂未生成", notes)
        with self.assertRaises(ValueError):
            MODULE.generate(["feat: input"], "", strict=True)

    def test_actions_outputs_and_summary_preserve_multiline_unicode(self):
        with tempfile.TemporaryDirectory() as directory:
            output, summary = [Path(directory) / name for name in ("output", "summary")]
            notes = MODULE.render_notes(sample_notes())
            with patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(summary)}):
                MODULE.write_outputs(notes, True)
            lines = output.read_text(encoding="utf-8").splitlines()
            delimiter = lines[0].split("<<", 1)[1]
            end = lines.index(delimiter)
            self.assertEqual("\n".join(lines[1:end]).rstrip(), notes.rstrip())
            self.assertEqual(lines[end + 1], "generated=true")
            self.assertEqual(summary.read_text(encoding="utf-8"), notes)


class CommitRangeTests(unittest.TestCase):
    def test_stable_and_nightly_use_only_reachable_stable_tags(self):
        with tempfile.TemporaryDirectory() as directory:
            def git(*args):
                return subprocess.run(["git", "-C", directory, *args], check=True,
                                      capture_output=True, encoding="utf-8").stdout.strip()
            def commit(message):
                git("-c", "user.name=Test", "-c", "user.email=test@example.test",
                    "commit", "--allow-empty", "-m", message)
            git("init", "-q")
            commit("feat: original")
            git("tag", "v1.0.0")
            commit("fix: typing\n\nPreserve punctuation.")
            git("tag", "v1.1.0-nightly.1")
            commit("chore(release): bump version to 1.1.0")
            git("tag", "v1.1.0")
            commit("feat: future")
            with patch.object(MODULE, "git", side_effect=lambda *args: git(*args)):
                commits, previous = MODULE.collect_commits("v1.1.0")
                self.assertEqual(previous, "v1.0.0")
                self.assertEqual(commits, ["fix: typing\n\nPreserve punctuation."])
                commits, previous = MODULE.collect_commits("v1.1.0", "nightly")
                self.assertEqual(previous, "v1.1.0")
                self.assertEqual(commits, [])
                commits, previous = MODULE.collect_commits("HEAD", "nightly")
                self.assertEqual(commits, ["feat: future"])
                self.assertEqual(previous, "v1.1.0")


if __name__ == "__main__":
    unittest.main()
