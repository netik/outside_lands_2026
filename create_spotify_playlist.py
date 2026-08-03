#!/usr/bin/env python3
"""
Create a Spotify playlist from schedule.json (Outside Lands 2026 picks).

Requirements:
  pip install spotipy

Setup:
  1. Create an app at https://developer.spotify.com/dashboard
  2. Add redirect URI: http://127.0.0.1:8888/callback
  3. Export credentials:
       export SPOTIFY_CLIENT_ID="..."
       export SPOTIFY_CLIENT_SECRET="..."

Run:
  python3 create_spotify_playlist.py

Opens a browser for one-time Spotify login, then creates:
  "Outside Lands 2026 — My Picks"
with each artist's top track (in set-time order, one track per artist).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("Install spotipy: pip install spotipy", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).parent
SCHEDULE = ROOT / "schedule.json"
PLAYLIST_NAME = "Outside Lands 2026 — My Picks"
PLAYLIST_DESC = "My Outside Lands 2026 picks — one top track per artist, in set order."
MARKET = "US"
SCOPES = "playlist-modify-private playlist-modify-public"

# Artists without Spotify URLs in schedule.json — search by name
SEARCH_FALLBACK = {
    "Vertigo": "Vertigo DJ San Francisco",
    "DJ Starr Noir": "DJ Starr Noir",
    "Bootie Mashup: Diva Pop w/ DJ Tyme": "Bootie Mashup",
    "Bootie Mashup: Hip Hop Fuego w/ DJ Airsun": "Bootie Mashup",
    "The Emo Night Tour": "Emo Night Tour",
}


def artist_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"artist/([A-Za-z0-9]+)", url)
    return m.group(1) if m else None


def load_artists_in_order() -> list[dict]:
    with open(SCHEDULE, encoding="utf-8") as f:
        shows = json.load(f)["shows"]
    shows.sort(key=lambda s: s["start"])

    seen_ids: set[str] = set()
    artists: list[dict] = []
    for show in shows:
        primary = show["artists"][0] if show.get("artists") else {}
        name = show["name"]
        aid = artist_id_from_url(primary.get("spotify_artist_url"))
        key = aid or name
        if key in seen_ids:
            continue
        seen_ids.add(key)
        artists.append(
            {
                "name": name,
                "spotify_artist_id": aid,
                "start": show["start"],
                "stage": show["stage"],
            }
        )
    return artists


def resolve_artist_id(sp: spotipy.Spotify, artist: dict) -> str | None:
    if artist["spotify_artist_id"]:
        return artist["spotify_artist_id"]
    query = SEARCH_FALLBACK.get(artist["name"], artist["name"])
    result = sp.search(q=query, type="artist", limit=1, market=MARKET)
    items = result.get("artists", {}).get("items", [])
    return items[0]["id"] if items else None


def top_track_uri(sp: spotipy.Spotify, artist_id: str) -> str | None:
    tracks = sp.artist_top_tracks(artist_id, country=MARKET)
    items = tracks.get("tracks", [])
    return items[0]["uri"] if items else None


def main() -> None:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print(
            "Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET.\n"
            "Create an app at https://developer.spotify.com/dashboard",
            file=sys.stderr,
        )
        sys.exit(1)

    auth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope=SCOPES,
        open_browser=True,
    )
    sp = spotipy.Spotify(auth_manager=auth)
    user_id = sp.current_user()["id"]

    artists = load_artists_in_order()
    track_uris: list[str] = []
    skipped: list[str] = []

    print(f"Resolving top tracks for {len(artists)} artists...")
    for artist in artists:
        aid = resolve_artist_id(sp, artist)
        if not aid:
            skipped.append(artist["name"])
            print(f"  ✗ {artist['name']} — artist not found")
            continue
        uri = top_track_uri(sp, aid)
        if not uri:
            skipped.append(artist["name"])
            print(f"  ✗ {artist['name']} — no top tracks")
            continue
        track_uris.append(uri)
        print(f"  ✓ {artist['name']}")

    if not track_uris:
        print("No tracks to add.", file=sys.stderr)
        sys.exit(1)

    playlist = sp.user_playlist_create(
        user_id, PLAYLIST_NAME, public=False, description=PLAYLIST_DESC
    )
    playlist_id = playlist["id"]
    sp.playlist_add_items(playlist_id, track_uris)

    url = playlist["external_urls"]["spotify"]
    print(f"\nCreated playlist ({len(track_uris)} tracks): {url}")
    if skipped:
        print(f"Skipped ({len(skipped)}): {', '.join(skipped)}")


if __name__ == "__main__":
    main()
