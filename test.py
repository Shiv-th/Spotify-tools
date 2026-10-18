import json
from monkey_patch import sp

# ============================================================
# CONFIGURATION
# ============================================================

JSON_FILE = "json-files/existing_playlists.json"

SOURCE_PLAYLIST_ID = "5XVqWCH2rncBPVBRswAGhf"

NEW_PLAYLIST_NAME = "Recovered Playlist"
NEW_PLAYLIST_DESCRIPTION = "Restored from a local Spotify playlist backup."


# ============================================================
# JSON
# ============================================================

def load_playlist_from_json():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    for playlist in data:
        if playlist["id"] == SOURCE_PLAYLIST_ID:
            return playlist

    raise ValueError(
        f"Playlist {SOURCE_PLAYLIST_ID} not found in JSON"
    )


# ============================================================
# CREATE NEW PLAYLIST
# ============================================================

def create_new_playlist(source_playlist):
    user_id = sp.current_user()["id"]

    new_playlist = sp.user_playlist_create(
        user=user_id,
        name=NEW_PLAYLIST_NAME,
        public=False,
        description=NEW_PLAYLIST_DESCRIPTION
    )

    playlist_id = new_playlist["id"]

    print(f"Created playlist: {new_playlist['name']}")
    print(f"New playlist ID: {playlist_id}")

    return playlist_id


# ============================================================
# COPY PLAYLIST CONTENTS
# ============================================================

def copy_playlist_contents(playlist_id, track_ids):
    total = len(track_ids)

    print(f"Total tracks to copy: {total}")

    for i in range(0, total, 100):
        batch = track_ids[i:i + 100]

        uris = [
            f"spotify:track:{track_id}"
            for track_id in batch
        ]

        sp.playlist_add_items(playlist_id, uris)

        print(f"Added {min(i + len(batch), total)}/{total}")

    print("Playlist copy complete.")


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
            f"WARNING: tracks field says "
            f"{source_playlist['tracks']}, but track_dict "
            f"contains {len(track_ids)} tracks."
        )

    if not track_ids:
        print("No tracks found. Aborting.")
        return

    new_playlist_id = create_new_playlist(source_playlist)

    copy_playlist_contents(new_playlist_id, track_ids)

    print("\nRecovery playlist created successfully.")
    print(
        f"Open it at: "
        f"https://open.spotify.com/playlist/{new_playlist_id}"
    )


if __name__ == "__main__":
    main()