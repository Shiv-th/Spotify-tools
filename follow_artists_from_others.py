from monkey_patch import sp
import json, subprocess, os

subprocess.run(["python", "artist_liked_songs.py"], check=True)

FOLLOWED_ARTISTS_FILE = "json-files/Followed_Artists.json"
OTHER_ARTISTS_FILE = "json-files/Other_Artists.json"


def load_json(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


artists_to_avoid = load_json("json-files/to_avoid.json")


def get_artists_to_follow(other_artists):
    to_follow = []
    for artist_id, artist_info in other_artists.items():
        if artist_id in artists_to_avoid:
            continue
        liked_count = artist_info.get("Number_of_liked_songs", 0)
        album_count = len(artist_info.get("unprocessed_album_ids", []))

        if liked_count >= 20 or (album_count <= 5 and album_count != 0):
            to_follow.append((artist_id, artist_info["name"]))

    return to_follow


def follow_artists():
    followed_data = load_json(FOLLOWED_ARTISTS_FILE)
    other_data = load_json(OTHER_ARTISTS_FILE)

    to_follow = get_artists_to_follow(other_data)
    print(f"Found {len(to_follow)} artists to follow.")

    # Prepare list of artists to follow in bulk
    batch_ids = []
    batch_names = []
    for artist_id, artist_name in to_follow:
        if artist_id in followed_data:
            print(f"Already followed: {artist_name}")
            continue
        batch_ids.append(artist_id)
        batch_names.append(artist_name)

    # Follow in chunks of 20 (Spotify API limit)
    for i in range(0, len(batch_ids), 20):
        chunk_ids = batch_ids[i : i + 20]
        chunk_names = batch_names[i : i + 20]
        try:
            sp.user_follow_artists(chunk_ids)
            for aid, name in zip(chunk_ids, chunk_names):
                print(f"Followed: {name}")
                # Move to followed
                artist_info = other_data.pop(aid)
                followed_data[aid] = artist_info
        except Exception as e:
            print(f"Failed to follow some artists in batch: {e}")

    # Save updated files
    save_json(followed_data, FOLLOWED_ARTISTS_FILE)
    save_json(other_data, OTHER_ARTISTS_FILE)


if __name__ == "__main__":
    follow_artists()
