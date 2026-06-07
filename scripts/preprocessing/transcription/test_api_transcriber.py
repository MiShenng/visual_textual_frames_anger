from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from api_transcriber import APITranscriber, build_secure_client_session_factory


class APITranscriberTests(unittest.TestCase):
    def test_secure_client_session_factory_injects_connector(self) -> None:
        import aiohttp

        original = Mock(return_value="session")
        with patch("api_transcriber.ssl.create_default_context", return_value="ssl-context") as create_context:
            with patch("aiohttp.TCPConnector", return_value="connector") as connector_cls:
                factory = build_secure_client_session_factory(original)
                result = factory(timeout="timeout")
        self.assertEqual(result, "session")
        create_context.assert_called_once()
        connector_cls.assert_called_once_with(ssl="ssl-context")
        original.assert_called_once_with(timeout="timeout", connector="connector")

    def test_constructor_reads_dashscope_api_key_from_env(self) -> None:
        previous = os.environ.get("DASHSCOPE_API_KEY")
        os.environ["DASHSCOPE_API_KEY"] = "env-test-key"
        try:
            transcriber = APITranscriber(
                base_websocket_api_url="wss://example.com/api-ws/v1/inference",
                model="fun-asr-realtime",
            )
            self.assertEqual(transcriber.api_key, "env-test-key")
        finally:
            if previous is None:
                os.environ.pop("DASHSCOPE_API_KEY", None)
            else:
                os.environ["DASHSCOPE_API_KEY"] = previous

    def test_save_transcript_bundle_writes_three_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            transcriber = APITranscriber(
                api_key="test-key",
                base_websocket_api_url="wss://example.com/api-ws/v1/inference",
                model="fun-asr-realtime",
            )
            paths = transcriber.save_transcript_bundle(
                transcript={
                    "text": "你好世界",
                    "audio_path": "/tmp/123.mp3",
                    "segments": [{"start": 0, "end": 1.5, "text": "你好世界"}],
                    "raw_result": {"output": {"sentence": [{"text": "你好世界"}]}},
                },
                output_dir=tmpdir,
                video_id="123",
                metadata={"platform_video_id": "123", "author_name": "作者", "title": "标题"},
            )
            self.assertTrue(Path(paths["json_path"]).exists())
            self.assertTrue(Path(paths["txt_path"]).exists())
            self.assertTrue(Path(paths["md_path"]).exists())
            payload = json.loads(Path(paths["json_path"]).read_text(encoding="utf-8"))
            self.assertEqual(payload["text"], "你好世界")
            self.assertEqual(payload["metadata"]["platform_video_id"], "123")


if __name__ == "__main__":
    unittest.main()
