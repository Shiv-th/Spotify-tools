from monkey_patch import sp
import json
import os


def save_json(filename, data):
    os.makedirs("json-files", exist_ok=True)
    with open(f"json-files/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(filename):
    path = f"json-files/{filename}"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def store_playlists():
    user_id = sp.current_user()["id"]

    existing = load_json("existing_playlists.json")
    existing_by_id = {p["id"]: p for p in existing}

    current = []
    offset = 0

    while True:
        response = sp.current_user_playlists(limit=50, offset=offset)
        items = response.get("items", [])
        if not items:
            break

        for playlist in items:
            if playlist["owner"]["id"] == user_id:
                current.append(
                    {
                        "id": playlist["id"],
                        "name": playlist["name"],
                        "tracks": playlist["tracks"]["total"],
                    }
                )

        offset += len(items)
        if response["next"] is None:
            break

    current_ids = set(p["id"] for p in current)
    existing_ids = set(existing_by_id.keys())

    to_remove = existing_ids - current_ids
    for pid in to_remove:
        existing_by_id.pop(pid, None)

    for playlist in current:
        if playlist["id"] not in existing_by_id:
            existing_by_id[playlist["id"]] = playlist
        else:
            existing_by_id[playlist["id"]].update(
                {
                    "name": playlist["name"],
                    "tracks": playlist["tracks"],
                }
            )

    merged = list(existing_by_id.values())
    save_json("existing_playlists.json", merged)
    print(
        f"Saved {len(merged)} playlists (added {len(current_ids - existing_ids)}, removed {len(to_remove)})."
    )


store_playlists()
