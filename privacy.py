# MIT License - Copyright (c) 2026 eripum9


def _privacy_keywords(config):
    """Return a list of lowercased privacy keywords from the config."""
    raw = config.get("privacy_blocked_keywords", "")
    return [item.strip().lower() for item in raw.replace("\n", ",").split(",") if item.strip()]


def _privacy_match(config, title="", artist="", album=""):
    """
    Return a non-empty reason string if the track should be hidden, or an
    empty string if it is safe to display.
    """
    if config.get("privacy_private_session"):
        return "Private session enabled"
    haystack = f"{title} {artist} {album}".lower()
    for keyword in _privacy_keywords(config):
        if keyword in haystack:
            return f"Matched privacy keyword: {keyword}"
    return ""
