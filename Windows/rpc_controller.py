class RpcController:
    def __init__(self, tasks, state, config_provider, diagnostics_writer, tray_updater, loop_target, default_client_id, running_setter):
        self._tasks = tasks
        self._state = state
        self._config_provider = config_provider
        self._diagnostics_writer = diagnostics_writer
        self._tray_updater = tray_updater
        self._loop_target = loop_target
        self._default_client_id = default_client_id
        self._running_setter = running_setter
        self._thread = None

    @property
    def thread(self):
        return self._thread

    def start(self):
        if self._state.rpc_running():
            return self._thread
        config = self._config_provider()
        self._running_setter(True)
        client_id = config.get("discord_client_id") if config.get("use_custom_client_id") and config.get("discord_client_id") else self._default_client_id
        enhanced = bool(config.get("amazon_devtools_enabled"))
        self._diagnostics_writer(
            rpc_status="starting",
            discord_status="unknown",
            client_id=client_id,
            track=None,
            presence_visible=False,
            album_art_url="",
            album_name="",
            track_link="",
            notification_enabled=bool(config.get("notification_enrichment_enabled")),
            notification=None,
            amazon_devtools={
                "enabled": enhanced,
                "status": "waiting" if enhanced else "off",
                "detail": "RPC is starting",
            },
            scrobbling={
                "lastfm": "starting" if config.get("lastfm_enabled") else "disabled",
                "listenbrainz": "starting" if config.get("listenbrainz_enabled") else "disabled",
            },
            privacy={
                "private_session": bool(config.get("privacy_private_session")),
                "blocked_keywords": config.get("privacy_blocked_keywords", ""),
                "hidden": False,
                "reason": "",
            },
            last_error="",
        )
        self._thread = self._tasks.start("rpc", self._loop_target, daemon=False)
        self._tray_updater()
        return self._thread

    def stop(self):
        self._running_setter(False)
        self._tray_updater()

    def restart(self, timeout=10):
        self.stop()
        if self._thread:
            self._thread.join(timeout=timeout)
        return self.start()

    def join(self, timeout=5):
        if self._thread:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True
