from monkey_patch import sp
import json, subprocess

# --- Load liked songs ---
with open("json-files/Liked_Songs.json", "r", encoding="utf-8") as f:
    liked_data = json.load(f)

original_tracks = liked_data.get("tracks", {})
print(f"Original liked songs: {len(original_tracks)}")

# --- Get 'Unlike' playlist ID ---
unlike_id = "3Ptven2vATpDoKP0GxiTaI"

# --- Extract track IDs from playlist in batches ---
unlike_track_ids = []
track_id_to_uri = {}

offset = 0
fetch_batch_size = 100

while True:
    response = sp.playlist_items(
        unlike_id,
        offset=offset,
        limit=fetch_batch_size,
        fields="items.track(id,uri),total",
        additional_types=["track"],
    )

    items = response["items"]

    if not items:
        break

    for item in items:
        track = item.get("track")

        if track and track.get("id"):
            tid = track["id"]
            unlike_track_ids.append(tid)
            track_id_to_uri[tid] = track["uri"]

    print(
        f"Fetched {len(items)} tracks "
        f"(total fetched: {len(unlike_track_ids)}/{response['total']})"
    )

    offset += len(items)

    # Stop once all tracks have been fetched
    if offset >= response["total"]:
        break

print(f"Total tracks in 'Unlike' playlist: {len(unlike_track_ids)}")

# --- Check if tracks are still liked ---
to_remove_from_json = []

check_batch_size = 40

for i in range(0, len(unlike_track_ids), check_batch_size):
    batch = unlike_track_ids[i : i + check_batch_size]

    result = sp.current_user_saved_tracks_contains(batch)

    for tid, is_liked in zip(batch, result):
        if not is_liked:
            to_remove_from_json.append(tid)

    print(
        f"Checked {min(i + check_batch_size, len(unlike_track_ids))}"
        f"/{len(unlike_track_ids)} tracks"
    )

print(f"Tracks to delete: {len(to_remove_from_json)}")

# --- Delete from liked_data ---
for tid in to_remove_from_json:
    liked_data["tracks"].pop(tid, None)

print(f"Remaining liked songs: {len(liked_data['tracks'])}")

# --- Save Liked_Songs.json ---
with open("json-files/Liked_Songs.json", "w", encoding="utf-8") as f:
    json.dump(liked_data, f, indent=2, ensure_ascii=False)

# --- Remove from playlist in batches of 100 ---
sp.playlist_replace_items(unlike_id, [])

# --- Re-cache liked songs ---
subprocess.run(["python", "cache-liked-songs.py"], check=True)