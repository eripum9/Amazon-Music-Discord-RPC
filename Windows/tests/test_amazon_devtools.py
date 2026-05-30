import inspect
import os

import amazon_devtools


def test_devtools_payload_normalises_secondary_time_pause_and_link_region():
    payload = amazon_devtools._normalise_track_payload(
        {
            "status": "found",
            "title": "Treehome95 [Explicit]",
            "secondary": "Tyler, The Creator • Wolf [Explicit]",
            "art_url": "https://example.com/art.jpg",
            "track_asin": "B00C3O5D3A",
            "position_text": "2:18",
            "remaining_text": "-0:41",
            "playback_status": "paused",
        },
        "de",
    )
    assert payload["status"] == "found"
    assert payload["title"] == "Treehome95"
    assert payload["artist"] == "Tyler, The Creator"
    assert payload["album"] == "Wolf"
    assert payload["position"] == 138
    assert payload["duration"] == 179
    assert payload["playback_status"] == "paused"
    assert payload["track_link"] == "https://music.amazon.de/tracks/B00C3O5D3A"


def test_devtools_single_secondary_label_populates_artist():
    payload = amazon_devtools._normalise_track_payload(
        {
            "status": "found",
            "title": "Song",
            "secondary": "Artist Only",
        }
    )
    assert payload["status"] == "found"
    assert payload["artist"] == "Artist Only"
    assert payload["album"] == ""


def test_devtools_target_validation_and_search_links():
    good_target = {
        "type": "page",
        "url": "https://music.amazon.de/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    regional_target = {
        "type": "page",
        "url": "https://www.amazon.de/morpho/webapp/index.html#/home",
        "title": "Amazon Music Desktop",
    }
    bad_target = {
        "type": "page",
        "url": "https://example.com/morpho/webapp/index.html",
        "title": "Amazon Music",
    }
    assert amazon_devtools._is_amazon_music_target(good_target)
    assert amazon_devtools._is_amazon_music_target(regional_target)
    assert not amazon_devtools._is_amazon_music_target(bad_target)
    assert amazon_devtools.amazon_music_search_link("Noid", "Tyler, The Creator", "de") == "https://music.amazon.de/search/Noid%20Tyler%2C%20The%20Creator"


def test_devtools_launcher_candidate_ordering_and_fallbacks():
    existing_path = r"C:\Amazon Music\Amazon Music.exe"
    exists = lambda path: path == existing_path
    start_apps = [
        {"Name": "Amazon Music", "AppID": "Website.Package!AmazonMusic"},
        {"Name": "Amazon Music", "AppID": existing_path},
        {"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"},
        {"Name": "Amazon Music RPC", "AppID": r"C:\Amazon Music RPC\AmazonMusicRPC.exe"},
    ]
    appx_apps = [
        {"PackageFamilyName": "AmazonMobileLLC.AmazonMusic_alt", "AppId": "AmazonMusic"},
    ]
    candidates = amazon_devtools._launcher_candidates("Override.Package!App", start_apps, appx_apps, exists)
    assert [candidate["value"] for candidate in candidates[:4]] == [
        "Override.Package!App",
        "Website.Package!AmazonMusic",
        existing_path,
        "AmazonMobileLLC.AmazonMusic_alt!AmazonMusic",
    ]
    assert [candidate["method"] for candidate in candidates[:4]] == [
        "override-aumid",
        "auto-aumid",
        "auto-exe",
        "auto-aumid",
    ]
    assert candidates[-1]["method"] == "hardcoded-store"
    assert candidates[-1]["value"] == amazon_devtools.APP_USER_MODEL_ID
    assert not amazon_devtools._start_app_candidates(
        [{"Name": "Amazon Music", "AppID": r"C:\Missing\Amazon Music.exe"}],
        lambda path: False,
    )
    failure = amazon_devtools._attempt_failure(
        {"method": "auto-aumid", "value": "Missing.Package!App"},
        "Package was not found. 0x80073CF1",
    )
    assert "package was not found" in failure.lower()


def test_devtools_port_and_powershell_hardening():
    amazon_devtools.reset_devtools_port()
    port = amazon_devtools.get_devtools_port()
    env = amazon_devtools.devtools_environment({})
    powershell_path = amazon_devtools._powershell_executable()
    launch_source = inspect.getsource(amazon_devtools.launch_amazon_music_devtools)
    aumid_source = inspect.getsource(amazon_devtools._launch_aumid)
    assert amazon_devtools.DEVTOOLS_PORT_MIN <= port <= amazon_devtools.DEVTOOLS_PORT_MAX
    assert port != amazon_devtools.COMMON_DEVTOOLS_PORT
    assert int(env[amazon_devtools.DEVTOOLS_PORT_ENV]) == port
    assert f"--remote-debugging-port={amazon_devtools.COMMON_DEVTOOLS_PORT}" not in launch_source
    assert os.path.isabs(powershell_path) or powershell_path.lower() == "powershell.exe"
    assert '["powershell"' not in aumid_source
    amazon_devtools.reset_devtools_port()
