"""Check actual SDK multipart uploads without contacting OpenAI."""
import base64
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from openai import OpenAI
from importlib import import_module

# Use the same HTTP transport as the installed SDK.
_client = import_module("openai._client")
httpx = getattr(_client, "httpx2", None) or getattr(_client, "httpx")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.image_client import ImageClient


class UploadTests(unittest.TestCase):
    def test_explicit_mime_for_single_multiple_and_mask_uploads(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            paths = [folder / name for name in ("face.PNG", "scene.JpEg", "product.WEBP", "mask.png")]
            for path in paths:
                path.write_bytes(b"synthetic upload bytes")
            expected = []

            def handle(request):
                message = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + request.headers["content-type"].encode() + b"\r\n\r\n" + request.read()
                )
                files = [part for part in message.iter_parts() if part.get_filename()]
                self.assertEqual([(part.get_filename(), part.get_content_type()) for part in files], expected)
                self.assertTrue(all(part.get_payload(decode=True) == b"synthetic upload bytes" for part in files))
                return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(b"result").decode()}]})

            with OpenAI(api_key="test-only", http_client=httpx.Client(transport=httpx.MockTransport(handle))) as sdk, \
                 patch("app.core.image_client.OpenAI", return_value=sdk), \
                 patch("mimetypes.guess_type", return_value=("application/octet-stream", None)):
                client = ImageClient("test-only")
                expected[:] = [(paths[2].name, "image/webp")]
                client.generate_image("Product", "1024x1024", folder, product_image_path=paths[2])
                expected[:] = [(paths[0].name, "image/png"), (paths[1].name, "image/jpeg"), (paths[2].name, "image/webp")]
                client.generate_image("Scene", "1024x1024", folder, face_image_path=paths[0],
                                      reference_image_path=paths[1], product_image_path=paths[2])
                expected[:] = [(paths[1].name, "image/jpeg"), (paths[0].name, "image/png"),
                               (paths[2].name, "image/webp"), (paths[3].name, "image/png")]
                client.generate_image("Edit", "1024x1024", folder, face_image_path=paths[0],
                                      reference_image_path=paths[1], product_image_path=paths[2], mask_path=paths[3])


if __name__ == "__main__":
    unittest.main()
