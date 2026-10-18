from monkey_patch import sp
import subprocess

PLAYLIST_NAME = "All_Albums"
current_user = sp.current_user()["id"]

# Fetch all saved albums
print("Fetching saved albums...")
saved_albums = []
results = sp.current_user_saved_albums(limit=50)

while results:
    saved_albums.extend(results["items"])
    if results["next"]:
        results = sp.next(results)
    else:
        break

print(f"Found {len(saved_albums)} saved albums.")

# # Collect all tracks from albums
track_uris = set()
album_ids = set()
for album in saved_albums:
    if not album:
        continue
    album_data = album.get("album")
    if not album_data:  # Skip if album is None
        print("Skipping an album entry with no album data")
        continue

    album_id = album_data["id"]
    album_ids.add(album_id)
    album_name = album_data["name"]

    results = sp.album_tracks(album_id, limit=50)
    while results:
        for track in results["items"]:
            if track and track.get("uri"):  # extra safety
                track_uris.add(track["uri"])
        if results.get("next"):
            results = sp.next(results)
        else:
            break

    print(f"Collected tracks from album: {album_name}")

print(f"Total unique tracks collected: {len(track_uris)}")

# Create or find the playlist
playlist_id = "6B6dCpYT3himhgPK6z5LwQ"

if not playlist_id:
    playlist = sp.user_playlist_create(current_user, PLAYLIST_NAME, public=False)
    playlist_id = playlist["id"]
    print(f"Created new playlist: {PLAYLIST_NAME}")

# Add tracks in batches of 100
track_list = list(track_uris)
for i in range(0, len(track_list), 100):
    sp.playlist_add_items(playlist_id, track_list[i : i + 100])

print(f"Added {len(track_list)} tracks.")

album_ids = list(album_ids)
for i in range(0, len(album_ids), 20):
    batch = album_ids[i : i + 20]
    sp.current_user_saved_albums_delete(batch)
    sp.album
    print(f"Removed {len(batch)} albums.")
print("\nAll albums removed from your library.")


subprocess.run(["python", "Duplicate.py"], check=True)
