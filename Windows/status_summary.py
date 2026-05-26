def metadata_source_summary(state, config):
    state = state if isinstance(state, dict) else {}
    config = config if isinstance(config, dict) else {}
    track = state.get("track") if isinstance(state.get("track"), dict) else {}
    privacy = state.get("privacy") if isinstance(state.get("privacy"), dict) else {}
    amazon = state.get("amazon_devtools") if isinstance(state.get("amazon_devtools"), dict) else {}
    notification = state.get("notification") if isinstance(state.get("notification"), dict) else None

    if privacy.get("hidden") or config.get("privacy_private_session"):
        return {
            "label": "Private",
            "detail": privacy.get("reason") or "Private session enabled",
            "state": "warn",
        }

    track_status = str(track.get("status") or "").lower()
    if track_status == "paused":
        return {
            "label": "Paused",
            "detail": track.get("title") or "Playback is paused",
            "state": "warn",
        }

    if config.get("amazon_devtools_enabled") and amazon.get("status") == "found":
        return {
            "label": "Amazon Metadata",
            "detail": amazon.get("title") or track.get("title") or "Using Amazon Music metadata",
            "state": "good",
        }

    if notification and config.get("notification_enrichment_enabled"):
        return {
            "label": "Notification Fallback",
            "detail": notification.get("title") or "Using Amazon Music notifications",
            "state": "good",
        }

    if track:
        return {
            "label": "SMTC Fallback",
            "detail": track.get("title") or "Using Windows media session data",
            "state": "good" if track_status == "playing" else "muted",
        }

    if config.get("amazon_devtools_enabled"):
        devtools_status = str(amazon.get("status") or "waiting").lower()
        if devtools_status in ("error", "unavailable"):
            return {
                "label": "Unavailable",
                "detail": amazon.get("detail") or "Amazon Music metadata is unavailable",
                "state": "bad",
            }
        return {
            "label": "Waiting",
            "detail": amazon.get("detail") or "Waiting for Amazon Music metadata",
            "state": "warn",
        }

    return {
        "label": "Waiting",
        "detail": "Waiting for Amazon Music",
        "state": "muted",
    }
