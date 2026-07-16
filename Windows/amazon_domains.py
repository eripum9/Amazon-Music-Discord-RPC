# MIT License - Copyright (c) 2026 eripum9

from urllib.parse import urlparse


AMAZON_REGION_SUFFIXES = (
    "com",
    "de",
    "co.uk",
    "fr",
    "it",
    "es",
    "co.jp",
    "ca",
    "com.au",
    "com.br",
    "com.mx",
)
AMAZON_MUSIC_HOSTS = frozenset(f"music.amazon.{suffix}" for suffix in AMAZON_REGION_SUFFIXES)
AMAZON_WEBAPP_HOSTS = frozenset(
    host
    for suffix in AMAZON_REGION_SUFFIXES
    for host in (f"music.amazon.{suffix}", f"www.amazon.{suffix}")
)
AMAZON_IMAGE_HOSTS = frozenset(
    {
        "m.media-amazon.com",
        "images-na.ssl-images-amazon.com",
        "images-eu.ssl-images-amazon.com",
        "images-fe.ssl-images-amazon.com",
    }
)


def exact_https_host(url, allowed_hosts):
    parsed = urlparse(str(url or ""))
    try:
        port = parsed.port
    except ValueError:
        return ""
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme.lower() != "https"
        or host not in allowed_hosts
        or port not in (None, 443)
        or parsed.username
        or parsed.password
    ):
        return ""
    return host


def exact_https_origin(url, allowed_hosts):
    parsed = urlparse(str(url or ""))
    host = exact_https_host(url, allowed_hosts)
    if not host or parsed.path or parsed.params or parsed.query or parsed.fragment:
        return ""
    return f"https://{host}"


def is_amazon_webapp_url(url):
    return bool(exact_https_host(url, AMAZON_WEBAPP_HOSTS))


def is_amazon_music_url(url):
    return bool(exact_https_host(url, AMAZON_MUSIC_HOSTS))
