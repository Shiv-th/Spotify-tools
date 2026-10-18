from monkey_patch import sp
import json, re
import os

EXISTING_PLAYLISTS_FILE = "json-files/existing_playlists.json"

# --- Load or create JSON file for existing playlists ---
if os.path.exists(EXISTING_PLAYLISTS_FILE):
    with open(EXISTING_PLAYLISTS_FILE, "r", encoding="utf-8") as f:
        existing_playlists = json.load(f)
else:
    existing_playlists = []


# --- Save or Update Playlist Tracks in JSON ---
def save_playlist_tracks(playlist_id, playlist_name, track_dict):
    # Remove existing entry if present
    existing_playlists[:] = [pl for pl in existing_playlists if pl["id"] != playlist_id]

    # Add updated entry with full metadata
    existing_playlists.append(
        {
            "id": playlist_id,
            "name": playlist_name,
            "tracks": len(track_dict),
            "track_dict": track_dict,
        }
    )

    with open(EXISTING_PLAYLISTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_playlists, f, indent=2, ensure_ascii=False)


# --- Load liked tracks (returns dict of track_id -> info) ---
def load_liked_tracks(filename):
    with open(f"json-files/{filename}", "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tracks", {})


# --- Get all tracks from playlist ---
def get_playlist_tracks(playlist_id, use_json=False):
    if use_json:
        for pl in existing_playlists:
            if pl["id"] == playlist_id:
                if not pl.get("track_dict"):
                    break
                print(f"Loaded playlist '{pl['name']}' from JSON.")
                return pl.get("track_dict", {})
        print("⚠ No cached data, fetching from Spotify...")

    track_dict = {}
    offset = 0
    while True:
        response = sp.playlist_items(playlist_id, offset=offset, limit=100)
        items = response.get("items", [])
        if not items:
            break
        for item in items:
            track = item.get("track")
            if track and track["id"]:
                track_dict[track["id"]] = {
                    "name": track["name"],
                    "artists": {a["id"]: a["name"] for a in track["artists"]},
                    "album": {track["album"]["id"]: track["album"]["name"]},
                    "source": playlist_id,
                    "disc_number": track.get("disc_number", 0),
                    "track_number": track.get("track_number", 0),
                }
        offset += len(items)

    # Save fresh snapshot
    playlist_name = sp.playlist(playlist_id)["name"]
    save_playlist_tracks(playlist_id, playlist_name, track_dict)

    return track_dict


def extract_playlist_id(url: str) -> str:
    # Regular expression to match playlist ID in a Spotify URL
    match = re.search(r"playlist/([a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    else:
        raise ValueError("Invalid Spotify playlist URL")


# --- Remove liked tracks from playlist ---
def remove_liked_from_playlist(playlist_id, liked_tracks):
    playlist_tracks = get_playlist_tracks(playlist_id, use_json=False)
    liked_ids = set(liked_tracks.keys())

    tracks_to_remove = [tid for tid in playlist_tracks.keys() if tid in liked_ids]

    print(f"Found {len(tracks_to_remove)} liked songs in playlist '{playlist_id}'.")

    for i in range(0, len(tracks_to_remove), 100):
        sp.playlist_remove_all_occurrences_of_items(
            playlist_id, tracks_to_remove[i : i + 100]
        )

    # Save updated playlist tracks (after removal)
    remaining_tracks = {
        tid: data for tid, data in playlist_tracks.items() if tid not in liked_ids
    }
    playlist_name = sp.playlist(playlist_id)["name"]
    save_playlist_tracks(playlist_id, playlist_name, remaining_tracks)

    print(f"Removed liked songs from playlist '{playlist_name}'.")


# --- Main Program ---
if __name__ == "__main__":
    liked_songs_file = "Liked_Songs.json"
    liked_tracks = load_liked_tracks(liked_songs_file)

    print(f"Fetched {len(liked_tracks)} liked songs\n")

    pid_list = [
        "https://open.spotify.com/playlist/05QmZnQLORap3vNwaZEicn?si=1f88a6e85a68449d",  # Currently Listening
        "https://open.spotify.com/playlist/3rz1ulF2y2k88OlJD1Xafn?si=c34dd3c6434247df",  # Artist Completes 4
        # "https://open.spotify.com/playlist/1mewwylzEOiGGF0IbweBJI?si=95476efbc88d41ed",   #Artist Completes 1
        # "https://open.spotify.com/playlist/4EUyjFYmbLKptsLixtG0Yw?si=4253d5307f5a465f",   #Artist Completes 2
        # "https://open.spotify.com/playlist/4BMLE1pXSMa3DWgJWYkr1L?si=6d13f3b5f2b44c39",   #Artist Completes 3
    ]

    for playlist_id in pid_list:
        remove_liked_from_playlist(extract_playlist_id(playlist_id), liked_tracks)
