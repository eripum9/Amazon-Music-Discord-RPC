# MIT License - Copyright (c) 2026 eripum9

import pylast
import traceback


class LastFMScrobbler:
    def __init__(self, api_key, api_secret, session_key):
        self.network = pylast.LastFMNetwork(
            api_key=api_key,
            api_secret=api_secret,
            session_key=session_key,
        )
        self._pending = []

    def update_now_playing(self, title, artist, album=None, duration=None):
        try:
            self.network.update_now_playing(
                artist=artist,
                title=title,
                album=album or "",
                duration=int(duration) if duration else None,
            )
            print(f"[Last.fm] Now playing: {title} by {artist}")
        except (pylast.NetworkError, pylast.MalformedResponseError) as e:
            print(f"[Last.fm] Now playing failed (network): {e}")
        except Exception as e:
            print(f"[Last.fm] Now playing failed: {e}")
            traceback.print_exc()

    def scrobble(self, title, artist, timestamp, album=None, duration=None):
        entry = {
            "artist": artist,
            "title": title,
            "timestamp": int(timestamp),
            "album": album or "",
            "duration": int(duration) if duration else None,
        }
        try:
            self._flush_pending()
            self.network.scrobble(**entry)
            print(f"[Last.fm] Scrobbled: {title} by {artist}")
        except (pylast.NetworkError, pylast.MalformedResponseError) as e:
            self._pending.append(entry)
            print(f"[Last.fm] Scrobble cached (network error, {len(self._pending)} pending): {e}")
        except Exception as e:
            print(f"[Last.fm] Scrobble failed: {e}")
            traceback.print_exc()

    def _flush_pending(self):
        if not self._pending:
            return
        remaining = []
        for entry in self._pending:
            try:
                self.network.scrobble(**entry)
                print(f"[Last.fm] Flushed cached scrobble: {entry['title']} by {entry['artist']}")
            except (pylast.NetworkError, pylast.MalformedResponseError):
                remaining.append(entry)
                break
        if remaining:
            idx = self._pending.index(remaining[0])
            self._pending = self._pending[idx:]
        else:
            self._pending = []


def get_auth_url(api_key, api_secret):
    skg = pylast.SessionKeyGenerator(
        pylast.LastFMNetwork(api_key=api_key, api_secret=api_secret)
    )
    url = skg.get_web_auth_url()
    return url, skg


def complete_auth(skg, url):
    session_key, username = skg.get_web_auth_session_key_username(url)
    return session_key, username
