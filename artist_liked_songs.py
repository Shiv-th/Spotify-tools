import json, subprocess, os

# Run dependent scripts
subprocess.run(["python", "unlike.py"], check=True)
subprocess.run(["python", "cache-followed-artists.py"], check=True)

LIKED_SONGS_FILE = "json-files/Liked_Songs.json"
FOLLOWED_ARTISTS_FILE = "json-files/Followed_Artists.json"
OTHER_ARTISTS_FILE = "json-files/Other_Artists.json"


def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    print(f"Warning: {filepath} could not be loaded.")
    return {}


def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {filepath}")


def update_artist_liked_songs():
    liked_data = load_json(LIKED_SONGS_FILE)
    followed_data = load_json(FOLLOWED_ARTISTS_FILE)
    other_data = load_json(OTHER_ARTISTS_FILE)

    all_liked_tracks = liked_data.get("tracks", {})

    # --- Transfer artist data from other -> followed ---
    for artist_id, followed_info in followed_data.items():
        if artist_id in other_data:
            other_info = other_data.pop(artist_id)
            # Merge old fields from other artist
            for key, value in other_info.items():
                if key not in followed_info:
                    followed_info[key] = value
                elif isinstance(value, dict) and isinstance(
                    followed_info.get(key), dict
                ):
                    followed_info[key].update(value)

    # --- Clear liked_tracks and reset count ---
    for artist_info in followed_data.values():
        artist_info["liked_tracks"] = {}
        artist_info["Number_of_liked_songs"] = 0

    for artist_info in other_data.values():
        artist_info["liked_tracks"] = {}
        artist_info["Number_of_liked_songs"] = 0

    # --- Re-assign liked tracks ---
    for track_id, track_info in all_liked_tracks.items():
        track_name = track_info["name"]
        artists = track_info.get("artists", {})

        for artist_id, artist_name in artists.items():
            if artist_id in followed_data:
                artist = followed_data[artist_id]
            else:
                artist = other_data.setdefault(artist_id, {"name": artist_name})

            if "liked_tracks" not in artist:
                artist["liked_tracks"] = {}
            artist["liked_tracks"][track_id] = track_name
            artist["Number_of_liked_songs"] = len(artist["liked_tracks"])

    # --- Sort other artists ---
    sorted_other = dict(
        sorted(
            other_data.items(),
            key=lambda x: x[1].get("Number_of_liked_songs", 0),
            reverse=True,
        )
    )
    followed_data = dict(
        sorted(
            followed_data.items(),
            key=lambda x: x[1].get("Number_of_liked_songs", 0),
            reverse=True,
        )
    )

    save_json(followed_data, FOLLOWED_ARTISTS_FILE)
    save_json(sorted_other, OTHER_ARTISTS_FILE)


if __name__ == "__main__":
    update_artist_liked_songs()
