"""Offline checks for personal HeyGen inventory and pagination."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, call
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.heygen_client import HeyGenClient, GenerationCancelled


class PersonalInventoryTests(unittest.TestCase):
    def test_video_agent_routes_prompt_and_polls_video(self):
        client = HeyGenClient("fake")
        with patch.object(client, "_post", return_value={"data": {"session_id": "s"}}) as post, \
             patch.object(client, "_get", side_effect=[
                 {"data": {"status": "generating", "video_id": "v"}},
                 {"data": {"status": "completed", "video_url": "https://example.test/video.mp4"}},
             ]) as get, patch.object(client, "download", return_value=Path("video.mp4")) as download:
            result = client.generate_from_prompt_and_wait("a", "voice", "Original script", "Directions", Path("out"))
            self.assertEqual(result, Path("video.mp4"))
            self.assertEqual(post.call_args.args, ("/v3/video-agents", {
                "prompt": "Directions", "mode": "generate", "avatar_id": "a", "voice_id": "voice"}))
            self.assertEqual([c.args[0] for c in get.call_args_list], ["/v3/video-agents/s", "/v3/videos/v"])
            download.assert_called_once()

    def test_video_agent_cancel_and_failed_session(self):
        client = HeyGenClient("fake")
        cancel = threading.Event()
        cancel.set()
        with patch.object(client, "_post") as post:
            with self.assertRaises(GenerationCancelled):
                client.generate_from_prompt_and_wait("a", "v", "script", "prompt", Path("out"), cancel_event=cancel)
            post.assert_not_called()
        with patch.object(client, "_post", return_value={"data": {"session_id": "s"}}), \
             patch.object(client, "_get", return_value={"data": {"status": "failed"}}), \
             patch.object(client, "download") as download:
            with self.assertRaises(RuntimeError):
                client.generate_from_prompt_and_wait("a", "v", "script", "prompt", Path("out"))
            download.assert_not_called()

    def test_avatar_pagination_and_ui_fields(self):
        client = HeyGenClient("fake")
        with patch.object(client, "_get", side_effect=[
            {"data": [{"id": "a", "name": "My look", "preview_image_url": "preview"}], "has_more": True, "next_token": "next"},
            {"data": [{"id": "b"}], "has_more": False},
        ]) as get:
            rows = client.list_avatars()
        self.assertEqual([r["avatar_id"] for r in rows], ["a", "b"])
        self.assertEqual(rows[0]["avatar_name"], "My look")
        self.assertEqual(rows[0]["preview_image_url"], "preview")
        self.assertEqual(get.call_args_list, [
            call("/v3/avatars/looks", params={"ownership": "private", "limit": 50}),
            call("/v3/avatars/looks", params={"ownership": "private", "limit": 50, "token": "next"}),
        ])

    def test_private_voice_filter_on_every_page(self):
        client = HeyGenClient("fake")
        with patch.object(client, "_get", side_effect=[
            {"data": [{"voice_id": "v1"}], "has_more": True, "next_token": "next"},
            {"data": [{"voice_id": "v2"}], "has_more": False},
        ]) as get:
            self.assertEqual([r["voice_id"] for r in client.list_voices()], ["v1", "v2"])
        for args in get.call_args_list:
            self.assertEqual(args.args[0], "/v3/voices")
            self.assertEqual(args.kwargs["params"]["type"], "private")

    def test_empty_and_failed_private_inventory_never_falls_back(self):
        client = HeyGenClient("fake")
        for method in (client.list_avatars, client.list_voices):
            with patch.object(client, "_get", return_value={"data": [], "has_more": False}) as get:
                self.assertEqual(method(), [])
                self.assertEqual(get.call_count, 1)
            with patch.object(client, "_get", side_effect=RuntimeError("denied")) as get:
                with self.assertRaises(RuntimeError):
                    method()
                self.assertEqual(get.call_count, 1)

    def test_repeated_cursor_is_an_error(self):
        client = HeyGenClient("fake")
        with patch.object(client, "_get", return_value={"data": [], "has_more": True, "next_token": "same"}):
            with self.assertRaises(RuntimeError):
                client.list_voices()


if __name__ == "__main__":
    unittest.main()
