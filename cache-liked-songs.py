from monkey_patch import sp
import json, os

FILENAME = "Liked_Songs.json"


def load_cache():
    if not os.path.exists(f"json-files/{FILENAME}"):
        return {"last_added": None, "tracks": {}}
    with open(f"json-files/{FILENAME}", "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(data):
    with open(f"json-files/{FILENAME}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_new_tracks(existing_ids):
    new_tracks = {}
    offset = 0
    limit = 50

    while True:
        response = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = response["items"]
        if not items:
            break

        for item in items:
            track = item["track"]
            track_id = track["id"]
            if track_id in existing_ids:
                return new_tracks

            new_tracks[track_id] = {
                "name": track["name"],
                "artists": {
                    artist["id"]: artist["name"] for artist in track.get("artists", [])
                },
                "album": {"id": track["album"]["id"], "name": track["album"]["name"]},
            }

        offset += limit
        print(f"Collected {len(new_tracks)} new tracks so far...")

    return new_tracks


if __name__ == "__main__":
    data = load_cache()
    existing_tracks = data["tracks"]
    existing_ids = set(existing_tracks.keys())

    new_tracks = get_new_tracks(existing_ids)

    if new_tracks:
        print(f"Found {len(new_tracks)} new liked songs.")
        data["tracks"].update(new_tracks)
        save_cache(data)
    else:
        print("No new liked songs found.")

    print(f"{len(data['tracks'])} total liked songs")
