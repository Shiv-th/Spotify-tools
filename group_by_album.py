from monkey_patch import sp
import random

PLAYLIST_ID = "5XVqWCH2rncBPVBRswAGhf"

# 1. Fetch all tracks
tracks = []
offset = 0

while True:
    response = sp.playlist_items(
        PLAYLIST_ID, offset=offset, additional_types=["track"], limit=100
    )
    if response is None:
        raise RuntimeError(f"Playlist {PLAYLIST_ID} does not exist")
    tracks.extend(response["items"])
    if response["next"] is None:
        break
    offset += 100

# 2. Group by album
albums = {}

for item in tracks:
    track = item["track"]
    if not track or not track["album"]:
        continue

    album_id = track["album"]["id"]
    albums.setdefault(album_id, []).append(track)

# 3. Sort songs within each album by track number
for album_id in albums:
    albums[album_id].sort(key=lambda t: t["track_number"])

# 4. Shuffle albums
album_groups = list(albums.values())
# random.shuffle(album_groups)

# 5. Flatten track URIs
new_order = [track["uri"] for album in album_groups for track in album]

# 6. Replace playlist tracks
BATCH_SIZE = 100

# Replace first 100 tracks
sp.playlist_replace_items(PLAYLIST_ID, new_order[:BATCH_SIZE])

# Append remaining tracks in batches of 100
for i in range(BATCH_SIZE, len(new_order), BATCH_SIZE):
    sp.playlist_add_items(PLAYLIST_ID, new_order[i : i + BATCH_SIZE])

print("Playlist reordered successfully in batches of 100!")
