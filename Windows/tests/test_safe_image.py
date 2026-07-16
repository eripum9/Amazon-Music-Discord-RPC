# MIT License - Copyright (c) 2026 eripum9

import io

import pytest
from PIL import Image

import safe_image


class FakeResponse:
    def __init__(self, payload=b"", status=200, headers=None):
        self.payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        for offset in range(0, len(self.payload), chunk_size):
            yield self.payload[offset:offset + chunk_size]

    def close(self):
        self.closed = True


def _image_bytes(image_format="PNG", size=(16, 16)):
    output = io.BytesIO()
    Image.new("RGB", size, "red").save(output, format=image_format)
    return output.getvalue()


def test_thumbnail_download_revalidates_redirect_and_limits_bytes():
    payload = _image_bytes("JPEG")
    redirect = FakeResponse(status=302, headers={"Location": "https://is1-ssl.mzstatic.com/art.jpg"})
    image = FakeResponse(payload, headers={"Content-Type": "image/jpeg", "Content-Length": str(len(payload))})
    responses = iter((redirect, image))

    downloaded = safe_image.download_thumbnail(
        "https://cdn-images.dzcdn.net/start.jpg",
        requester=lambda *args, **kwargs: next(responses),
    )
    assert downloaded == payload
    assert redirect.closed and image.closed

    bad_redirect = FakeResponse(status=302, headers={"Location": "https://127.0.0.1/private.png"})
    with pytest.raises(ValueError, match="trusted image host"):
        safe_image.download_thumbnail(
            "https://cdn-images.dzcdn.net/start.jpg",
            requester=lambda *args, **kwargs: bad_redirect,
        )

    oversized = FakeResponse(
        b"x",
        headers={"Content-Type": "image/png", "Content-Length": str(safe_image.MAX_THUMBNAIL_BYTES + 1)},
    )
    with pytest.raises(ValueError, match="download limit"):
        safe_image.download_thumbnail(
            "https://cdn-images.dzcdn.net/start.png",
            requester=lambda *args, **kwargs: oversized,
        )


def test_thumbnail_decoder_restricts_format_dimensions_and_pixels(monkeypatch):
    decoded = safe_image.decode_thumbnail(_image_bytes("PNG", (32, 24)), 12)
    assert decoded.size == (12, 12)
    assert decoded.mode == "RGBA"

    with pytest.raises(ValueError, match="format"):
        safe_image.decode_thumbnail(_image_bytes("GIF"), 12)

    monkeypatch.setattr(safe_image, "MAX_THUMBNAIL_DIMENSION", 20)
    with pytest.raises(ValueError, match="dimensions"):
        safe_image.decode_thumbnail(_image_bytes("PNG", (21, 10)), 12)

    monkeypatch.setattr(safe_image, "MAX_THUMBNAIL_DIMENSION", 100)
    monkeypatch.setattr(safe_image, "MAX_THUMBNAIL_PIXELS", 100)
    with pytest.raises(ValueError, match="pixel count"):
        safe_image.decode_thumbnail(_image_bytes("PNG", (11, 10)), 12)
