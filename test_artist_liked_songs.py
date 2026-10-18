import json
from monkey_patch import sp

JSON_FILE = "json-files/Liked_Songs.json"

TARGET_ARTIST_ID = "0Ey8TMIVvT6OSYiblEuyMh"

PLAYLIST_IDS = [
    "3Ptven2vATpDoKP0GxiTaI",
    "5XVqWCH2rncBPVBRswAGhf",
]

with open(JSON_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

# ==========================================
# FILTER TRACKS BY TARGET ARTIST ID
# ==========================================

tracks_dict = data.get("tracks", {})
track_ids = []
artist_name = None

for track_id, track_info in tracks_dict.items():
    artists = track_info.get("artists", {})
    if TARGET_ARTIST_ID in artists:
        track_ids.append(track_id)
        if not artist_name:
            artist_name = artists[TARGET_ARTIST_ID]

artist_name = artist_name or "Unknown Artist"

print(f"Target Artist: {artist_name}")
print(f"Target Artist ID: {TARGET_ARTIST_ID}")
print(f"Matching songs found: {len(track_ids)}")

if not track_ids:
    print("No matching songs found for this artist.")
    exit()

# Remove duplicate IDs while preserving order
track_ids = list(dict.fromkeys(track_ids))

# ==========================================
# ADD TARGET TRACKS TO PLAYLISTS
# ==========================================

print(f"\nAdding {len(track_ids)} tracks to {len(PLAYLIST_IDS)} playlists...")

for playlist_index, playlist_id in enumerate(PLAYLIST_IDS, 1):
    print(f"\nPlaylist {playlist_index}/{len(PLAYLIST_IDS)}: {playlist_id}")

    for i in range(0, len(track_ids), 100):
        batch = track_ids[i:i + 100]

        sp.playlist_add_items(
            playlist_id=playlist_id,
            items=batch
        )

        print(f"  Added {i + len(batch)}/{len(track_ids)} tracks")

    print(f"Finished playlist: {playlist_id}")

# ==========================================
# UNLIKE (REMOVE) ONLY TARGET TRACKS
# ==========================================

print("\nUnliking target tracks...")

for i in range(0, len(track_ids), 40):
    batch = track_ids[i:i + 40]

    sp.current_user_saved_tracks_delete(batch)

    print(f"Unliked {i + len(batch)}/{len(track_ids)} tracks")

print("\nDone!")
print(f"Processed and removed {len(track_ids)} songs by {artist_name}.")