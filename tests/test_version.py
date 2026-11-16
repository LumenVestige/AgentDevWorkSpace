"""Remote version fallbacks; all responses are mocked and never use the network."""
import base64
import contextlib
import io
import json
import os
import runpy
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock
from urllib.error import HTTPError, URLError

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills"))
import _version as version

RATE_LIMIT = {
    "message": "API rate limit exceeded for 141.11.131.247. "
               "(But here's the good news: Authenticated requests get a higher rate limit. "
               "Check out the documentation for more details.)",
    "documentation_url": "https://docs.github.com/rest/overview/resources-in-the-rest-api#rate-limiting",
}


class RemoteVersionTests(unittest.TestCase):
    def fetch(self, responses, url=None):
        def respond(request, **kwargs):
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return io.BytesIO(response)

        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "", "GH_TOKEN": ""}), \
                mock.patch.object(version.urllib.request, "urlopen", side_effect=respond) as open_url:
            result = version.fetch_remote_version(url)
        self.assertTrue(open_url.call_args_list)
        for call in open_url.call_args_list:
            self.assertEqual(call.kwargs["timeout"], 5)
        return result, [call.args[0].full_url for call in open_url.call_args_list]

    def test_both_endpoints_get_full_five_second_timeout(self):
        result, urls = self.fetch([TimeoutError("timed out"), b"0.3.7\n"])
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [version.API_URL, version.RAW_URL])

    def test_welcome_and_background_checks_use_five_seconds_per_endpoint(self):
        with tempfile.TemporaryDirectory(prefix="agentdev-version-timeout-") as temporary:
            root = Path(temporary)
            skill = root / "installation"
            (skill / "publish").mkdir(parents=True)
            (skill / "publish/version").write_text("0.3.7\n")
            common = types.ModuleType("common")
            common.ENV = root
            cfg = {"auto_update": False}
            common.load_config = mock.Mock(return_value=cfg)
            common.skill_dir = mock.Mock(return_value=skill)
            for name in ("project_root", "python_path", "update_stamp_file"):
                setattr(common, name, mock.Mock())
            with mock.patch.dict(sys.modules, {"common": common}):
                updater = runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills/notes/update.py"))
            for entry in ("welcome", "check"):
                with self.subTest(entry=entry), contextlib.redirect_stdout(io.StringIO()), \
                        mock.patch.object(version.urllib.request, "urlopen", side_effect=[
                            TimeoutError("timed out"), io.BytesIO(b"0.3.7\n")]) as open_url:
                    updater[entry](root, *([cfg] if entry == "check" else []))
                    self.assertEqual(open_url.call_count, 2)
                    self.assertEqual([call.kwargs["timeout"] for call in open_url.call_args_list], [5, 5])

    def test_valid_plain_version_stops_without_fallback(self):
        result, urls = self.fetch([b"0.3.7\n"])
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [version.API_URL])

    def test_contents_response_is_decoded_before_validating_version(self):
        body = json.dumps({"content": base64.b64encode(b"0.3.7\n").decode()}).encode()
        result, urls = self.fetch([body])
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [version.API_URL])

    def test_rate_limit_json_falls_back_even_with_successful_http_status(self):
        result, urls = self.fetch([json.dumps(RATE_LIMIT).encode(), b"0.3.7\n"])
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [version.API_URL, version.RAW_URL])

    def test_http_errors_and_network_failures_fall_back(self):
        errors = [HTTPError(version.API_URL, status, "rate limited", {}, None)
                  for status in (403, 429)] + [URLError("offline"), TimeoutError("timed out")]
        for error in errors:
            with self.subTest(error=error):
                result, urls = self.fetch([error, b"0.3.7\n"])
                self.assertEqual(result, (0, 3, 7))
                self.assertEqual(urls, [version.API_URL, version.RAW_URL])

    def test_any_response_without_valid_version_falls_back(self):
        bodies = [b"", b"<html>error</html>", b"not a version", b"0.3.x", b"{broken",
                  b"{}", b"[]", b'{"content": null}', b'{"content": []}',
                  b'{"content": "%%%"}', b"\xff",
                  json.dumps({"content": base64.b64encode(b"not a version").decode()}).encode()]
        for body in bodies:
            with self.subTest(body=body):
                result, urls = self.fetch([body, b"0.3.7\n"])
                self.assertEqual(result, (0, 3, 7))
                self.assertEqual(urls, [version.API_URL, version.RAW_URL])

    def test_all_sources_must_fail_before_raising(self):
        with self.assertRaises(RuntimeError) as caught:
            self.fetch([json.dumps(RATE_LIMIT).encode(), b"not a version"])
        self.assertIn("API rate limit exceeded", str(caught.exception))
        self.assertIn("not a version", str(caught.exception))

    def test_raw_configuration_still_uses_api_then_raw_fallback(self):
        result, urls = self.fetch([json.dumps(RATE_LIMIT).encode(), b"0.3.7"], version.RAW_URL)
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [version.API_URL, version.RAW_URL])

    def test_custom_version_source_is_not_replaced(self):
        url = "https://example.invalid/version"
        result, urls = self.fetch([b"0.3.7\n"], url)
        self.assertEqual(result, (0, 3, 7))
        self.assertEqual(urls, [url])


if __name__ == "__main__":
    unittest.main()
