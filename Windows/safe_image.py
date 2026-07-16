# MIT License - Copyright (c) 2026 eripum9

import io
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image

from amazon_domains import AMAZON_IMAGE_HOSTS


MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024
MAX_THUMBNAIL_DIMENSION = 4096
MAX_THUMBNAIL_PIXELS = 12_000_000
MAX_THUMBNAIL_REDIRECTS = 3
ALLOWED_THUMBNAIL_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
ALLOWED_THUMBNAIL_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_THUMBNAIL_HOSTS = frozenset(
    {
        "cdn-images.dzcdn.net",
        "e-cdns-images.dzcdn.net",
        "is1-ssl.mzstatic.com",
        "is2-ssl.mzstatic.com",
        "is3-ssl.mzstatic.com",
        "is4-ssl.mzstatic.com",
        "is5-ssl.mzstatic.com",
        *AMAZON_IMAGE_HOSTS,
    }
)
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


def _trusted_thumbnail_url(url):
    parsed = urlparse(str(url or ""))
    try:
        port = parsed.port
    except ValueError:
        return False
    return bool(
        parsed.scheme.lower() == "https"
        and (parsed.hostname or "").lower() in ALLOWED_THUMBNAIL_HOSTS
        and port in (None, 443)
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )


def _response_length(response):
    try:
        return int((response.headers or {}).get("Content-Length", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _read_bounded(response, max_bytes):
    payload = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        payload.extend(chunk)
        if len(payload) > max_bytes:
            raise ValueError("Thumbnail exceeds the download limit")
    return bytes(payload)


def download_thumbnail(url, requester=requests.get):
    current = str(url or "")
    for redirect_count in range(MAX_THUMBNAIL_REDIRECTS + 1):
        if not _trusted_thumbnail_url(current):
            raise ValueError("Thumbnail URL is not from a trusted image host")
        response = requester(
            current,
            headers={"User-Agent": "AmazonMusicRPC/5"},
            timeout=(3, 5),
            stream=True,
            allow_redirects=False,
        )
        try:
            status = int(getattr(response, "status_code", 200) or 200)
            if status in REDIRECT_STATUS_CODES:
                location = (response.headers or {}).get("Location", "")
                if not location or redirect_count >= MAX_THUMBNAIL_REDIRECTS:
                    raise ValueError("Thumbnail redirected too many times")
                current = urljoin(current, location)
                continue
            response.raise_for_status()
            content_type = str((response.headers or {}).get("Content-Type", "")).split(";", 1)[0].strip().lower()
            if content_type not in ALLOWED_THUMBNAIL_CONTENT_TYPES:
                raise ValueError("Thumbnail content type is not allowed")
            if _response_length(response) > MAX_THUMBNAIL_BYTES:
                raise ValueError("Thumbnail exceeds the download limit")
            return _read_bounded(response, MAX_THUMBNAIL_BYTES)
        finally:
            response.close()
    raise ValueError("Thumbnail redirected too many times")


def decode_thumbnail(payload, size):
    with Image.open(io.BytesIO(payload)) as image:
        image_format = str(image.format or "").upper()
        width, height = image.size
        if image_format not in ALLOWED_THUMBNAIL_FORMATS:
            raise ValueError("Thumbnail image format is not allowed")
        if width < 1 or height < 1 or width > MAX_THUMBNAIL_DIMENSION or height > MAX_THUMBNAIL_DIMENSION:
            raise ValueError("Thumbnail dimensions are not allowed")
        if width * height > MAX_THUMBNAIL_PIXELS:
            raise ValueError("Thumbnail decoded pixel count is too large")
        image.load()
        return image.convert("RGBA").resize((int(size), int(size)), Image.Resampling.LANCZOS)


def load_thumbnail_image(url, size, requester=requests.get):
    return decode_thumbnail(download_thumbnail(url, requester=requester), size)
