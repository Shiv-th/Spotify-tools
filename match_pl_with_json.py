from monkey_patch import sp
import json

# ============================================================
# CONFIGURATION
# ============================================================

JSON_FILE = "json-files/existing_playlists.json"

PLAYLIST_ID = "1mewwylzEOiGGF0IbweBJI"

REPLACE_EXISTING_PLAYLIST = True

NEW_PLAYLIST_NAME = "Recovered Playlist"
NEW_PLAYLIST_DESCRIPTION = "Restored from a local Spotify playlist backup."


# ============================================================
# JSON
# ============================================================

def load_playlist_from_json():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for playlist in data:
        if playlist["id"] == PLAYLIST_ID:
            return playlist

    raise ValueError(f"Playlist {PLAYLIST_ID} not found in JSON")


# ============================================================
# PLAYLIST CREATION / SELECTION
# ============================================================

def get_target_playlist(source_playlist):
    if REPLACE_EXISTING_PLAYLIST:
        print(f"Using existing playlist: {source_playlist['name']}")
        return PLAYLIST_ID

    user_id = sp.current_user()["id"]

    new_playlist = sp.user_playlist_create(
        user=user_id,
        name=NEW_PLAYLIST_NAME,
        public=False,
        description=NEW_PLAYLIST_DESCRIPTION
    )

    print(f"Created new playlist: {new_playlist['name']}")
    print(f"New playlist ID: {new_playlist['id']}")

    return new_playlist["id"]


# ============================================================
# REPLACE / COPY PLAYLIST CONTENTS
# ============================================================

def update_playlist_contents(playlist_id, track_ids):
    total = len(track_ids)

    print(f"Total tracks to process: {total}")

    if REPLACE_EXISTING_PLAYLIST:
        print("Clearing existing playlist...")
        sp.playlist_replace_items(playlist_id, [])

    print("Adding tracks from JSON...")

    for i in range(0, total, 100):
        batch = track_ids[i:i + 100]

        uris = [
            f"spotify:track:{track_id}"
            for track_id in batch
        ]

        sp.playlist_add_items(playlist_id, uris)

        print(f"Added {min(i + len(batch), total)}/{total}")

    print("Playlist update complete.")


# ============================================================
# MAIN
# ============================================================

def main():
    source_playlist = load_playlist_from_json()

    print(f"Source playlist: {source_playlist['name']}")
    print(f"JSON track count: {source_playlist['tracks']}")

    track_ids = list(source_playlist["track_dict"].keys())

    if len(track_ids) != source_playlist["tracks"]:
        print(
            f"WARNING: tracks field says {source_playlist['tracks']}, "
            f"but track_dict contains {len(track_ids)} tracks."
        )

    if not track_ids:
        print("No tracks found. Aborting.")
        return

    target_playlist_id = get_target_playlist(source_playlist)

    update_playlist_contents(target_playlist_id, track_ids)

    print("\nOperation completed.")
    print(
        "Open playlist: "
        f"https://open.spotify.com/playlist/{target_playlist_id}"
    )


if __name__ == "__main__":
    main()