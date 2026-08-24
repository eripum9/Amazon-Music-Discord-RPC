# MIT License - Copyright (c) 2026 eripum9

"""Cross-platform feature core composed with macOS metadata backends."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from Shared.playback import (
    apply_track_mapping,
    configured_game_mode_processes,
    find_custom_album_art,
    game_mode_matches_processes,
    nonnegative_number,
    normalise_track,
    privacy_reason,
    remembered_track_mapping,
    remembered_track_mapping_key,
    same_track_field,
    scrobble_eligible,
)

from . import amazon_devtools, config, media_reader


POLL_SECONDS = 2.0
PAUSE_ICON_URL = (
    "https://raw.githubusercontent.com/eripum9/"
    "Amazon-Music-Discord-RPC/master/Images/pause_icon.png"
)


def _shared_discord_factory(client_id):
    from Windows.discord_rpc import DiscordRPC

    return DiscordRPC(client_id)


def _shared_lastfm_factory(api_key, api_secret, session_key, privacy_enabled=False):
    from Windows.lastfm import LastFMScrobbler

    return LastFMScrobbler(api_key, api_secret, session_key, privacy_enabled)


def _shared_listenbrainz_factory(token, privacy_enabled=False):
    from Windows.listenbrainz_scrobbler import ListenBrainzScrobbler

    return ListenBrainzScrobbler(token, privacy_enabled)


def _shared_art_lookup(title, artist, *, deezer_enabled=True, itunes_enabled=True):
    from Windows.album_art import get_album_art

    return get_album_art(
        title,
        artist,
        deezer_enabled=deezer_enabled,
        itunes_enabled=itunes_enabled,
    )


def _running_process_names():
    try:
        completed = subprocess.run(
            ["/bin/ps", "-axo", "comm="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    if completed.returncode != 0:
        return set()
    names = set()
    for line in completed.stdout.splitlines():
        name = os.path.basename(line.strip()).casefold()
        if name:
            names.add(name)
            names.add(os.path.splitext(name)[0])
    return names


def _record_network_event(service, operation, status, detail=""):
    try:
        from Windows.network_audit import record_network_event

        record_network_event(service, operation, status, detail, config.CONFIG_DIR)
    except Exception:
        pass


@dataclass(slots=True)
class RuntimeDependencies:
    discord_factory: Callable = _shared_discord_factory
    lastfm_factory: Callable = _shared_lastfm_factory
    listenbrainz_factory: Callable = _shared_listenbrainz_factory
    art_lookup: Callable = _shared_art_lookup
    devtools_track: Callable = amazon_devtools.get_devtools_track_sync
    devtools_launch: Callable = amazon_devtools.launch_amazon_music_devtools
    devtools_restart: Callable = amazon_devtools.restart_amazon_music_devtools
    devtools_disable: Callable = amazon_devtools.disable_amazon_music_devtools
    devtools_status: Callable = amazon_devtools.get_devtools_status
    amazon_running: Callable = amazon_devtools.amazon_music_is_running
    now_playing_track: Callable = media_reader.get_track_sync
    process_names: Callable = _running_process_names
    network_event: Callable = _record_network_event
    clock: Callable = time.time


def _number(value, default=0.0):
    return nonnegative_number(value, default)


_normalise_track = normalise_track
_privacy_reason = privacy_reason
_mapping = apply_track_mapping


def _configured_processes(value):
    return configured_game_mode_processes(value)


def _custom_art(settings, album):
    custom = find_custom_album_art(settings, album)
    if not custom:
        return None
    return custom["art_url"], custom.get("album") or album


def _privacy_safe_devtools_state(state):
    if not isinstance(state, dict):
        return {}
    allowed = ("enabled", "status", "detail", "source", "port", "method", "owner")
    return {key: state[key] for key in allowed if key in state}


class MacRuntime:
    """Owns metadata polling, presence, privacy, artwork and scrobbling."""

    def __init__(self, dependencies=None, settings_loader=config.load_config):
        self.dependencies = dependencies or RuntimeDependencies()
        self._settings_loader = settings_loader
        self._settings = settings_loader()
        self._config_mtime = self._configuration_mtime()
        self._listeners = []
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._rpc_enabled = True
        self._rpc = None
        self._last_client_id = ""
        self._last_service_fingerprint = None
        self._lastfm = None
        self._listenbrainz = None
        self._track_key = ""
        self._session_track_mappings = {}
        self._track_started_at = None
        self._scrobble_position_baseline = 0.0
        self._scrobbling_was_blocked = False
        self._scrobbled = False
        self._art_key = ""
        self._art_url = ""
        self._album = ""
        self._deezer_link = ""
        self._presence_visible = False
        self._last_error = ""
        self._snapshot = self._empty_snapshot()

    def _empty_snapshot(self):
        return {
            "updated_at": self.dependencies.clock(),
            "app_version": config.APP_VERSION,
            "rpc_status": "running" if self._rpc_enabled else "stopped",
            "rpc": "on" if self._rpc_enabled else "off",
            "discord_status": "waiting",
            "discord": "Waiting",
            "track": None,
            "title": "",
            "artist": "",
            "album": "",
            "time": "",
            "presence_visible": False,
            "source": "Waiting",
            "source_detail": "Waiting for Amazon Music",
            "amazon_devtools": {"status": "waiting", "detail": "Not checked yet"},
            "devtools_status": "waiting",
            "scrobbling": {"lastfm": "disabled", "listenbrainz": "disabled"},
            "privacy": {"private_session": False, "hidden": False, "reason": ""},
            "private": False,
            "game_mode": "off",
            "correction_suggested": False,
            "last_error": "",
        }

    def add_listener(self, callback, emit_current=True):
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)
            snapshot = dict(self._snapshot)
        if emit_current:
            callback(snapshot)

    def remove_listener(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def snapshot(self):
        with self._lock:
            return json.loads(json.dumps(self._snapshot))

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    @property
    def rpc_enabled(self):
        return self._rpc_enabled

    def start(self):
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="macos-rpc-runtime", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=8)
        self._shutdown_services()
        self._rpc_enabled = False
        self._publish(rpc_status="stopped", rpc="off", presence_visible=False)

    def set_rpc_enabled(self, enabled):
        self._rpc_enabled = bool(enabled)
        if not enabled:
            self._clear_presence()
        self._publish(
            rpc_status="running" if enabled else "stopped",
            rpc="on" if enabled else "off",
        )

    def reload_config(self, settings=None):
        self._settings = dict(settings or self._settings_loader())
        self._config_mtime = self._configuration_mtime()
        self._ensure_services(force=True)
        return self._settings

    def _configuration_mtime(self):
        try:
            return os.stat(config.CONFIG_PATH).st_mtime_ns
        except OSError:
            return 0

    def _reload_if_changed(self):
        modified = self._configuration_mtime()
        if modified == self._config_mtime:
            return
        loaded = self._settings_loader()
        self._config_mtime = modified
        if loaded.get(config.CONFIG_REVISION_KEY) != self._settings.get(config.CONFIG_REVISION_KEY):
            self._settings = loaded
            self._ensure_services(force=True)

    def set_private_session(self, enabled):
        settings = config.update_config_fields({"privacy_private_session": bool(enabled)})
        self.reload_config(settings)
        if enabled:
            if settings.get("privacy_disable_scrobbling", True):
                # Never let listening time accumulated before or during a
                # private session count after the session is disabled.
                self._scrobbling_was_blocked = True
                self._track_started_at = None
                self._scrobble_position_baseline = 0.0
                self._scrobbled = False
            self._clear_presence()
            current = self._snapshot.get("track") or {}
            hidden = {
                "title": "Hidden by privacy controls",
                "artist": "",
                "album": "",
                "status": current.get("status", ""),
                "position": current.get("position"),
                "duration": current.get("duration", 0),
                "source": current.get("source", ""),
            }
            self._publish(
                track=hidden,
                title=hidden["title"],
                artist="",
                album="",
                album_art_url="",
                track_link="",
                raw_track={},
                amazon_devtools=_privacy_safe_devtools_state(
                    self._snapshot.get("amazon_devtools")
                ),
                presence_visible=False,
                private=True,
                correction_suggested=False,
                privacy={
                    "private_session": True,
                    "hidden": True,
                    "reason": "Private session enabled",
                },
            )
        else:
            self._publish(
                private=False,
                privacy={"private_session": False, "hidden": False, "reason": ""},
            )
        return settings

    def set_game_mode(self, enabled):
        settings = config.update_config_fields({"game_mode_enabled": bool(enabled)})
        self.reload_config(settings)
        self._publish(game_mode="on" if enabled else "off")
        return settings

    def game_mode_active(self):
        if self._settings.get("game_mode_enabled"):
            return True
        configured = _configured_processes(self._settings.get("game_mode_processes"))
        if not configured:
            return False
        return game_mode_matches_processes(configured, self.dependencies.process_names())

    def remember_correction(self, raw_title, raw_artist, corrected):
        key = remembered_track_mapping_key(raw_title, raw_artist)

        def transform(fields):
            mappings = dict(fields.get("track_mappings") or {})
            mappings[key] = {
                field: corrected.get(field, "")
                for field in ("title", "artist", "album", "art_url", "track_link", "duration")
            }
            return {"track_mappings": mappings}

        settings = config.mutate_config_fields({"track_mappings"}, transform)
        with self._lock:
            self._session_track_mappings.pop(key, None)
            self._track_key = ""
            self._art_key = ""
        self.reload_config(settings)
        return settings

    def apply_session_correction(self, raw_title, raw_artist, corrected):
        """Apply a correction until the app exits without writing settings."""

        key = remembered_track_mapping_key(raw_title, raw_artist)
        mapping = {
            field: corrected.get(field, "")
            for field in ("title", "artist", "album", "art_url", "track_link", "duration")
        }
        with self._lock:
            self._session_track_mappings[key] = mapping
            self._track_key = ""
            self._art_key = ""
        return mapping

    def apply_correction(self, raw_title, raw_artist, corrected, *, remember=False):
        if remember:
            return self.remember_correction(raw_title, raw_artist, corrected)
        return self.apply_session_correction(raw_title, raw_artist, corrected)

    def launch_enhanced_metadata(self, restart_if_needed=False):
        result = self.dependencies.devtools_launch()
        if result.get("restart_required") and restart_if_needed:
            result = self.dependencies.devtools_restart()
        self._publish(
            amazon_devtools={
                "enabled": True,
                "status": result.get("status", "error"),
                "detail": result.get("error") or "Enhanced metadata is ready",
                "port": result.get("port"),
            },
            devtools_status=result.get("status", "error"),
        )
        return result

    def disable_enhanced_metadata(self, *, relaunch=True):
        """Explicitly remove the listener and reopen Amazon Music normally."""

        result = self.dependencies.devtools_disable(relaunch=relaunch)
        if result.get("ok"):
            settings = config.update_config_fields(
                {
                    "amazon_devtools_enabled": False,
                    "amazon_devtools_auto_launch": False,
                }
            )
            self.reload_config(settings)
        self._publish(
            amazon_devtools={
                "enabled": False,
                "status": result.get("status", "error"),
                "detail": (
                    result.get("error")
                    or "Amazon Music reopened normally without a DevTools listener"
                ),
            },
            devtools_status=result.get("status", "error"),
        )
        return result

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.tick()
                self._last_error = ""
            except Exception as error:
                self._last_error = f"{type(error).__name__}: {error}"
                self._publish(last_error=self._last_error)
            self._stop.wait(POLL_SECONDS)

    def _client_id(self):
        if self._settings.get("use_custom_client_id") and self._settings.get("discord_client_id"):
            return str(self._settings["discord_client_id"])
        return config.DEFAULT_CLIENT_ID

    def _ensure_services(self, force=False):
        client_id = self._client_id()
        if force or client_id != self._last_client_id:
            if self._rpc:
                try:
                    self._rpc.shutdown()
                except Exception:
                    pass
            self._rpc = self.dependencies.discord_factory(client_id)
            self._last_client_id = client_id

        fingerprint = (
            bool(self._settings.get("lastfm_enabled")),
            self._settings.get("lastfm_api_key"),
            self._settings.get("lastfm_api_secret"),
            self._settings.get("lastfm_session_key"),
            bool(self._settings.get("listenbrainz_enabled")),
            self._settings.get("listenbrainz_token"),
            bool(self._settings.get("privacy_private_session")),
            bool(self._settings.get("privacy_disable_scrobbling", True)),
        )
        if not force and fingerprint == self._last_service_fingerprint:
            return
        for service in (self._lastfm, self._listenbrainz):
            if service and hasattr(service, "close"):
                try:
                    service.close()
                except Exception:
                    pass
        self._lastfm = None
        self._listenbrainz = None
        privacy = bool(
            self._settings.get("privacy_private_session")
            and self._settings.get("privacy_disable_scrobbling", True)
        )
        if self._settings.get("lastfm_enabled") and self._settings.get("lastfm_session_key"):
            try:
                self._lastfm = self.dependencies.lastfm_factory(
                    self._settings.get("lastfm_api_key"),
                    self._settings.get("lastfm_api_secret"),
                    self._settings.get("lastfm_session_key"),
                    privacy,
                )
            except Exception as error:
                self._last_error = f"Last.fm: {error}"
        if self._settings.get("listenbrainz_enabled") and self._settings.get("listenbrainz_token"):
            try:
                self._listenbrainz = self.dependencies.listenbrainz_factory(
                    self._settings.get("listenbrainz_token"), privacy
                )
            except Exception as error:
                self._last_error = f"ListenBrainz: {error}"
        self._last_service_fingerprint = fingerprint

    def _shutdown_services(self):
        self._clear_presence()
        for service in (self._lastfm, self._listenbrainz):
            if service and hasattr(service, "close"):
                try:
                    service.close()
                except Exception:
                    pass
        self._lastfm = None
        self._listenbrainz = None
        if self._rpc:
            try:
                self._rpc.shutdown()
            except Exception:
                pass
        self._rpc = None

    def _read_track(self):
        devtools_state = {
            "enabled": bool(self._settings.get("amazon_devtools_enabled")),
            "status": "off",
            "detail": "Enhanced metadata is disabled",
            "source": "amazon_devtools",
        }
        track = None
        if self._settings.get("amazon_devtools_enabled"):
            raw = self.dependencies.devtools_track(
                self._settings.get("amazon_music_link_region", "com")
            )
            devtools_state = {"enabled": True, **(raw if isinstance(raw, dict) else {})}
            track = _normalise_track(raw, "amazon_devtools") if raw and raw.get("status") == "found" else None
            if not track and self._settings.get("amazon_devtools_auto_launch"):
                if not self.dependencies.amazon_running():
                    result = self.dependencies.devtools_launch()
                    devtools_state = {
                        "enabled": True,
                        "status": result.get("status", "launching"),
                        "detail": result.get("error") or "Launching Amazon Music for enhanced metadata",
                        "port": result.get("port"),
                    }
                else:
                    devtools_state = {
                        "enabled": True,
                        "status": "restart_required",
                        "detail": "Amazon Music needs your approval for a one-time DevTools restart",
                    }
        if not track:
            track = _normalise_track(self.dependencies.now_playing_track(), "macos_now_playing")
        return track, devtools_state

    def _resolve_art(self, track):
        key = f"{track['title']}|{track['artist']}"
        if key == self._art_key:
            return
        self._art_key = key
        self._art_url = track.get("art_url", "")
        self._album = track.get("album", "")
        self._deezer_link = ""
        if not self._art_url:
            self.dependencies.network_event("artwork", "lookup", "started", "new track")
            try:
                art, album, link, duration = self.dependencies.art_lookup(
                    track["title"],
                    track["artist"],
                    deezer_enabled=self._settings.get("deezer_lookup_enabled", True),
                    itunes_enabled=self._settings.get("itunes_lookup_enabled", True),
                )
                self._art_url = art or ""
                self._album = album or self._album
                self._deezer_link = link or ""
                if duration and not track.get("duration"):
                    track["duration"] = _number(duration)
                self.dependencies.network_event("artwork", "lookup", "success", "completed")
            except Exception as error:
                self.dependencies.network_event("artwork", "lookup", "error", type(error).__name__)
        custom = _custom_art(self._settings, self._album or track.get("album"))
        if custom:
            self._art_url, self._album = custom

    def _buttons(self, track):
        if not self._settings.get("song_link_enabled"):
            return None
        provider = self._settings.get("song_link_provider", "amazon")
        if provider == "deezer" and self._deezer_link:
            return [{"label": "Listen on Deezer", "url": self._deezer_link}]
        link = track.get("track_link") or amazon_devtools.amazon_music_search_link(
            track.get("title"),
            track.get("artist"),
            self._settings.get("amazon_music_link_region"),
        )
        return [{"label": "Listen on Amazon Music", "url": link}] if link else None

    def _scrobbling_status(self):
        if self._settings.get("lastfm_enabled"):
            lastfm = "active" if self._lastfm else "not_authenticated"
        else:
            lastfm = "disabled"
        if self._settings.get("listenbrainz_enabled"):
            listenbrainz = "active" if self._listenbrainz else "missing_token"
        else:
            listenbrainz = "disabled"
        return {"lastfm": lastfm, "listenbrainz": listenbrainz}

    def _new_track(
        self,
        track,
        allow_scrobbling=True,
        start_scrobble_fresh=False,
        allow_artwork=True,
    ):
        self._track_key = f"{track['title']}|{track['artist']}"
        position = track.get("position")
        if start_scrobble_fresh:
            self._track_started_at = self.dependencies.clock()
            self._scrobble_position_baseline = _number(position)
        else:
            self._track_started_at = (
                self.dependencies.clock() - position
                if position is not None
                else self.dependencies.clock()
            )
            self._scrobble_position_baseline = 0.0
        self._scrobbled = False
        if allow_artwork:
            self._resolve_art(track)
        else:
            # Preserve metadata already supplied locally, but never send a
            # hidden title/artist to an artwork provider.
            self._art_key = ""
            self._art_url = track.get("art_url", "")
            self._album = track.get("album", "")
            self._deezer_link = ""
        duration = track.get("duration") or 0
        for service in (self._lastfm, self._listenbrainz) if allow_scrobbling else ():
            if service:
                try:
                    service.update_now_playing(
                        track["title"], track["artist"], self._album, duration
                    )
                except Exception:
                    pass

    def _try_scrobble(self, track):
        if self._scrobbled or not self._track_started_at:
            return
        if self._settings.get("privacy_private_session") and self._settings.get(
            "privacy_disable_scrobbling", True
        ):
            return
        elapsed = (
            max(
                0.0,
                _number(track.get("position")) - self._scrobble_position_baseline,
            )
            if track.get("position") is not None
            else self.dependencies.clock() - self._track_started_at
        )
        duration = _number(track.get("duration"))
        if not scrobble_eligible(elapsed, duration):
            return
        for service in (self._lastfm, self._listenbrainz):
            if service:
                try:
                    service.scrobble(
                        track["title"],
                        track["artist"],
                        int(self._track_started_at),
                        self._album,
                        duration,
                    )
                except Exception:
                    pass
        self._scrobbled = True

    def _clear_presence(self):
        if self._rpc and self._presence_visible:
            try:
                self._rpc.clear()
            except Exception:
                pass
        self._presence_visible = False

    def tick(self):
        self._reload_if_changed()
        self._ensure_services()

        if not self._rpc_enabled:
            self._clear_presence()
            self._publish(
                rpc_status="stopped",
                rpc="off",
                discord_status="disconnected",
                discord="Disconnected",
                presence_visible=False,
                correction_suggested=False,
            )
            return self.snapshot()

        track, devtools = self._read_track()
        if not track:
            self._clear_presence()
            self._track_key = ""
            self._track_started_at = None
            self._scrobble_position_baseline = 0.0
            self._scrobbled = False
            if not self._settings.get("privacy_private_session"):
                self._scrobbling_was_blocked = False
            self._art_key = ""
            self._art_url = ""
            self._album = ""
            self._deezer_link = ""
            self._publish(
                rpc_status="running",
                rpc="on",
                track=None,
                title="",
                artist="",
                album="",
                raw_track={},
                album_art_url="",
                track_link="",
                time="",
                source="Waiting",
                source_detail=devtools.get("detail") or "Waiting for Amazon Music",
                amazon_devtools=devtools,
                devtools_status=devtools.get("status", "waiting"),
                presence_visible=False,
                discord_status="connected" if self._rpc and self._rpc.connected else "waiting",
                discord="Connected" if self._rpc and self._rpc.connected else "Waiting",
                scrobbling=self._scrobbling_status(),
                private=bool(self._settings.get("privacy_private_session")),
                game_mode="on" if self.game_mode_active() else "off",
                correction_suggested=False,
                last_error=self._last_error,
            )
            return self.snapshot()

        raw_title, raw_artist = track["title"], track["artist"]
        with self._lock:
            session_mappings = dict(self._session_track_mappings)
        session_mapping = remembered_track_mapping(
            session_mappings, raw_title, raw_artist
        )
        saved_mapping = session_mapping or remembered_track_mapping(
            self._settings, raw_title, raw_artist
        )
        track = _mapping(
            session_mappings if session_mapping else self._settings,
            track,
        )
        privacy_reason = _privacy_reason(self._settings, track)
        correction_suggested = bool(
            not privacy_reason
            and not saved_mapping
            and same_track_field(raw_title, raw_artist)
            and not self.game_mode_active()
        )
        allow_scrobbling = not privacy_reason or not self._settings.get(
            "privacy_disable_scrobbling", True
        )
        track_key = f"{track['title']}|{track['artist']}"
        scrobbling_blocked = bool(privacy_reason and not allow_scrobbling)
        resume_after_privacy = bool(
            not scrobbling_blocked and self._scrobbling_was_blocked
        )
        if scrobbling_blocked:
            self._scrobbling_was_blocked = True
            self._track_started_at = None
            self._scrobble_position_baseline = 0.0
            self._scrobbled = False
        elif track_key != self._track_key or resume_after_privacy:
            self._scrobbling_was_blocked = False
            self._new_track(
                track,
                allow_scrobbling=allow_scrobbling,
                start_scrobble_fresh=resume_after_privacy,
                allow_artwork=not privacy_reason,
            )
        elif track.get("album") and not self._album:
            self._album = track["album"]
        if not privacy_reason and self._art_key != track_key:
            self._resolve_art(track)

        paused = track["status"] == "paused"
        should_show = not privacy_reason and (not paused or self._settings.get("show_paused", True))
        if should_show:
            start_ts = None
            duration = track.get("duration") or 0
            if track.get("position") is not None:
                start_ts = int(self.dependencies.clock() - track["position"])
            elif not paused:
                start_ts = int(self._track_started_at or self.dependencies.clock())
            self._rpc.update(
                title=track["title"],
                artist=track["artist"],
                album_art_url=self._art_url,
                album_name=self._album,
                start_ts=start_ts,
                duration=duration,
                buttons=self._buttons(track),
                small_image=PAUSE_ICON_URL if paused else None,
                small_text="Paused" if paused else None,
                status_display=self._settings.get("discord_status_display", "artist"),
            )
            self._presence_visible = bool(self._rpc.connected)
        else:
            self._clear_presence()

        if not paused and allow_scrobbling:
            self._try_scrobble(track)

        position = track.get("position")
        duration = track.get("duration") or 0
        time_label = ""
        if position is not None:
            def stamp(seconds):
                seconds = int(max(0, seconds))
                return f"{seconds // 60}:{seconds % 60:02d}"

            time_label = stamp(position)
            if duration:
                time_label += f" / {stamp(duration)}"
        public_track = dict(track)
        public_track["album"] = self._album or track.get("album", "")
        if privacy_reason:
            public_track = {
                "title": "Hidden by privacy controls",
                "artist": "",
                "album": "",
                "status": track["status"],
                "position": track.get("position"),
                "duration": track.get("duration"),
                "source": track.get("source"),
            }
        source_label = "Amazon metadata" if track["source"] == "amazon_devtools" else "macOS fallback"
        self._publish(
            rpc_status="running",
            rpc="on",
            discord_status="connected" if self._rpc.connected else "retrying",
            discord="Connected" if self._rpc.connected else "Retrying",
            track=public_track,
            raw_track=(
                {}
                if privacy_reason
                else {"title": raw_title, "artist": raw_artist}
            ),
            title=public_track["title"],
            artist=public_track.get("artist", ""),
            album=public_track.get("album", ""),
            time=time_label,
            source="Paused" if paused else source_label,
            source_detail=devtools.get("detail") or source_label,
            amazon_devtools=(
                _privacy_safe_devtools_state(devtools)
                if privacy_reason
                else devtools
            ),
            devtools_status=devtools.get("status", "waiting"),
            presence_visible=self._presence_visible,
            album_art_url=self._art_url if not privacy_reason else "",
            track_link=track.get("track_link", "") if not privacy_reason else "",
            scrobbling=self._scrobbling_status(),
            privacy={
                "private_session": bool(self._settings.get("privacy_private_session")),
                "hidden": bool(privacy_reason),
                "reason": privacy_reason,
            },
            private=bool(self._settings.get("privacy_private_session")),
            game_mode="on" if self.game_mode_active() else "off",
            correction_suggested=correction_suggested,
            last_error=self._last_error,
        )
        return self.snapshot()

    def _publish(self, **changes):
        with self._lock:
            self._snapshot.update(changes)
            self._snapshot["updated_at"] = self.dependencies.clock()
            snapshot = json.loads(json.dumps(self._snapshot, default=str))
            listeners = list(self._listeners)
        self._write_diagnostics(snapshot)
        for callback in listeners:
            try:
                callback(snapshot)
            except Exception:
                pass

    def _write_diagnostics(self, snapshot):
        path = Path(config.DIAGNOSTICS_PATH)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(config.redact_data(snapshot, self._settings), indent=2),
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        except OSError:
            pass
