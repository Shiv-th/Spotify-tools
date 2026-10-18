from monkey_patch import sp
import json
import os
import re, subprocess
from collections import defaultdict

LIKED_SONGS_FILE = "Liked_Songs.json"
subprocess.run(["python", "unlike.py"], check=True)

# === Utilities ===
EXISTING_PLAYLISTS_FILE = "json-files/existing_playlists.json"
if os.path.exists(EXISTING_PLAYLISTS_FILE):
    with open(EXISTING_PLAYLISTS_FILE, "r", encoding="utf-8") as f:
        existing_playlists = json.load(f)
else:
    existing_playlists = []


def save_playlist_tracks(playlist_id, playlist_name, track_dict):
    # Remove existing entry if present
    existing_playlists[:] = [pl for pl in existing_playlists if pl["id"] != playlist_id]

    # Add updated entry with full track metadata
    existing_playlists.append(
        {
            "id": playlist_id,
            "name": playlist_name,
            "tracks": len(track_dict),
            "track_dict": track_dict,
        }
    )

    with open(EXISTING_PLAYLISTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_playlists, f, indent=2, ensure_ascii=False)


def normalize_title(title: str) -> str:
    prev = title
    title = re.sub(r"\(.*?\)|\[.*?\]|-.*", "", title)
    while prev != title:
        prev = title
        title = re.sub(r"\(.*?\)|\[.*?\]|-.*", "", title)
    return title.strip().lower()


def fetch_liked_tracks():
    """Returns a dict of track_id -> track_data from liked songs."""
    path = f"json-files/{LIKED_SONGS_FILE}"
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("tracks", {})


def fetch_playlist_tracks(playlist_id: str, use_json=False) -> dict:
    # Normalize playlist_id (strip Spotify URL to get ID only)
    if playlist_id.startswith("http"):
        playlist_id = playlist_id.split("/")[-1].split("?")[0]

    print(f"Fetching playlist: {playlist_id}")
    # === Case 1: Load from JSON ===
    if use_json and existing_playlists:
        for pl in existing_playlists:
            if pl["id"] == playlist_id:
                if not pl.get("track_dict"):
                    break
                print(f"Loaded {pl['tracks']} tracks from JSON cache for {pl['name']}")
                return pl["track_dict"]
        print("No cached data for this playlist, fetching from Spotify instead...")

    # === Case 2: Fetch from Spotify ===
    track_dict = {}
    offset = 0
    limit = 100

    while True:
        response = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)
        items = response.get("items", [])
        if not items:
            break

        for item in items:
            track = item["track"]
            if not track:
                continue

            track_id = track["id"]
            track_dict[track_id] = {
                "name": track["name"],
                "artists": {a["id"]: a["name"] for a in track["artists"]},
                "album": {track["album"]["id"]: track["album"]["name"]},
                "source": playlist_id,
                "disc_number": track.get("disc_number", 0),
                "track_number": track.get("track_number", 0),
            }

        offset += limit
        print(f"Collected {len(track_dict)} tracks so far...")

    # Save results to JSON file
    try:
        playlist_name = sp.playlist(playlist_id)["name"]
    except Exception:
        playlist_name = f"Playlist {playlist_id}"

    save_playlist_tracks(playlist_id, playlist_name, track_dict)

    return track_dict


def group_same_base(track_dict: dict):
    """Returns 3 lists:
    - liked_only_duplicates
    - mixed_with_liked
    - mixed_no_liked
    """

    class UnionFind:
        def __init__(self):
            self.parent = {}

        def find(self, x):
            if self.parent.get(x, x) != x:
                self.parent[x] = self.find(self.parent[x])
            return self.parent.get(x, x)

        def union(self, x, y):
            xr, yr = self.find(x), self.find(y)
            if xr != yr:
                self.parent[yr] = xr

    grouped = defaultdict(list)
    for tid, track in track_dict.items():
        grouped[normalize_title(track["name"])].append((tid, track))

    liked_only_duplicates = []
    mixed_with_liked = []
    mixed_no_liked = []

    for _, tracks in grouped.items():
        if len(tracks) <= 1:
            continue

        uf = UnionFind()
        idx_to_tid = {i: tid for i, (tid, _) in enumerate(tracks)}
        artist_to_idx = defaultdict(list)

        for i, (tid, track) in enumerate(tracks):
            for artist_id in track["artists"].keys():
                artist_to_idx[artist_id].append(i)

        for indices in artist_to_idx.values():
            for i in range(1, len(indices)):
                uf.union(indices[0], indices[i])

        clusters = defaultdict(list)
        for i in range(len(tracks)):
            clusters[uf.find(i)].append(idx_to_tid[i])

        for group in clusters.values():
            if len(group) <= 1:
                continue
            sources = [track_dict[tid].get("source") for tid in group]
            if all(s == "liked" for s in sources):
                liked_only_duplicates.append(group)
            elif any(s == "liked" for s in sources):
                mixed_with_liked.append(group)
            else:
                mixed_no_liked.append(group)

    return liked_only_duplicates, mixed_with_liked, mixed_no_liked


def create_playlist(name, description="Duplicate Playlist"):
    user_id = sp.current_user()["id"]
    return sp.user_playlist_create(
        user=user_id, public=False, name=name, description=description
    )


def add_tracks_to_playlist(playlist_id, track_ids):
    for i in range(0, len(track_ids), 100):
        sp.playlist_add_items(playlist_id, track_ids[i : i + 100])


def remove_tracks_from_playlist(playlist_id, track_ids):
    if not track_ids:
        return
    print(
        f"Attempting to remove {len(track_ids)} tracks from playlist {playlist_id}..."
    )
    for i in range(0, len(track_ids), 100):
        try:
            sp.playlist_remove_all_occurrences_of_items(
                playlist_id, track_ids[i : i + 100]
            )
            print(f"Removed {len(track_ids[i : i + 100])} tracks successfully.")
        except Exception as e:
            print(f"Error removing tracks from {playlist_id}: {e}")


def filter_new_groups(groups, processed_set):
    """Keep the entire group if at least one track is new."""
    filtered = []
    for group in groups:
        if any(tid not in processed_set for tid in group):
            filtered.append(group)
    return filtered


def flatten(groups):
    return [tid for group in groups for tid in group]


def update_json_after_removal(playlist_id, removed_track_ids):
    for pl in existing_playlists:
        if pl["id"] == playlist_id and "track_dict" in pl:
            for tid in removed_track_ids:
                pl["track_dict"].pop(tid, None)
            pl["tracks"] = len(pl["track_dict"])
            break

    with open(EXISTING_PLAYLISTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_playlists, f, indent=2, ensure_ascii=False)


# === MAIN ===

if __name__ == "__main__":
    PROCESSED_TRACKS_FILE = "json-files/processed_tracks.json"
    USE_PROCESSED_TRACKS = True  # Set to False to skip tracking
    SAVE_PROCESSED_TRACKS = True  # Set False to skip saving
    USE_JSON = True  # Set to False to resave all tracks, For Artist Completes
    USE_JSON_FOR_OUTER = False  # For Currently Listening

    p_ids1 = [
        "53Mg7SHi0kuKcgCL0emiiw",   # Processed - 4
        "3QYSFCIq1VxVfZHu8s0C9e",   # Processed - 3
        "0qrNdWdNb5xgOuc2LUbUPp",   # Processed - 2
        "4uV9EPTPpjMswEeOs5myOu",   # Processed - 1
    ]

    p_ids2 = [
        "05QmZnQLORap3vNwaZEicn",   # Currently listening
        "5XVqWCH2rncBPVBRswAGhf",   # After  Classical
        "1mewwylzEOiGGF0IbweBJI",   # Artist Completes 1
    ]

    all_tracks = {}
    initial_removal_map = defaultdict(list)

    # Comment if liked songs to be excluded
    liked_tracks = fetch_liked_tracks()
    for tid, track in liked_tracks.items():
        track["source"] = "liked"
    all_tracks.update(liked_tracks)

    print("\n--- Processing p_ids1 (Artist Completes) ---")
    for pid in p_ids1:
        new_tracks = fetch_playlist_tracks(pid, USE_JSON)
        normalized_pid = pid.split("/")[-1].split("?")[0]

        for tid, d in new_tracks.items():
            d["source"] = normalized_pid

            if tid in all_tracks:
                # Action: Remove this duplicate copy from its source playlist (normalized_pid)
                initial_removal_map[normalized_pid].append(tid)

            else:
                # First time seeing this track ID, keep it.
                all_tracks[tid] = d
    print("\n--- Processing p_ids2 (Currently Listening) ---")
    for pid in p_ids2:
        new_tracks = fetch_playlist_tracks(pid, USE_JSON_FOR_OUTER)
        normalized_pid = pid.split("/")[-1].split("?")[0]

        for tid, d in new_tracks.items():
            d["source"] = normalized_pid

            if tid in all_tracks:
                # Action: Remove this duplicate copy from its source playlist (normalized_pid)
                initial_removal_map[normalized_pid].append(tid)

            else:
                # First time seeing this track ID, keep it.
                all_tracks[tid] = d

    print(f"Total unique tracks collected: {len(all_tracks)}")

    liked_only_duplicates, mixed_with_liked, mixed_no_liked = group_same_base(
        all_tracks
    )

    all_current_duplicates = set(
        flatten(liked_only_duplicates)
        + flatten(mixed_with_liked)
        + flatten(mixed_no_liked)
    )

    if USE_PROCESSED_TRACKS and os.path.exists(PROCESSED_TRACKS_FILE):
        with open(PROCESSED_TRACKS_FILE, "r", encoding="utf-8") as f:
            processed_tracks = set(json.load(f))
    else:
        processed_tracks = set()

    if USE_PROCESSED_TRACKS:
        liked_only_duplicates = filter_new_groups(
            liked_only_duplicates, processed_tracks
        )
        mixed_with_liked = filter_new_groups(mixed_with_liked, processed_tracks)
        mixed_no_liked = filter_new_groups(mixed_no_liked, processed_tracks)

    # Store the track groups before flattening for removal logic
    groups_to_remove = mixed_with_liked + mixed_no_liked

    liked_only_duplicates_flat = flatten(liked_only_duplicates)
    mixed_no_liked_flat = flatten(mixed_no_liked)
    mixed_with_liked_flat = flatten(mixed_with_liked)

    print(f"→ {len(liked_only_duplicates_flat)} liked-only duplicates")
    print(f"→ {len(mixed_with_liked_flat)} mixed duplicates (with liked songs)")
    print(f"→ {len(mixed_no_liked_flat)} mixed duplicates (no liked songs)")

    # --- Remove non-liked duplicates from their source playlists
    print("\n--- Removing Duplicates from Playlists ---")
    removal_map = defaultdict(list)

    for playlist_id, track_ids_to_remove in initial_removal_map.items():
        for tid in track_ids_to_remove:
            removal_map[playlist_id].append(tid)

    # Process mixed_no_liked and mixed_with_liked groups
    for group in groups_to_remove:
        for tid in group:
            track_source = all_tracks[tid]["source"]
            # Only remove if the source is a playlist ID (not the 'liked' placeholder)
            if track_source != "liked":
                removal_map[track_source].append(tid)

    # Execute removal
    for playlist_id, track_ids_to_remove in removal_map.items():
        remove_tracks_from_playlist(playlist_id, track_ids_to_remove)
        update_json_after_removal(playlist_id, track_ids_to_remove)

    print("--- Duplicate Removal Complete ---")

    if liked_only_duplicates_flat:
        pl = create_playlist(
            "Duplicate Songs (Liked Only)",
            "Songs from liked tracks that are duplicates",
        )
        add_tracks_to_playlist(pl["id"], liked_only_duplicates_flat)
        print(f"Added {len(liked_only_duplicates_flat)} to playlist {pl['name']}")

    if mixed_with_liked_flat:
        pl = create_playlist(
            "Duplicate Songs (Mixed with Liked)",
            "Groups that include both liked and playlist tracks",
        )
        add_tracks_to_playlist(pl["id"], mixed_with_liked_flat)
        print(f"Added {len(mixed_with_liked_flat)} to playlist {pl['name']}")

    if mixed_no_liked_flat:
        pl = create_playlist(
            "Duplicate Songs (Mixed No Liked)",
            "Groups that include duplicates across playlists only",
        )
        add_tracks_to_playlist(pl["id"], mixed_no_liked_flat)
        print(f"Added {len(mixed_no_liked_flat)} to playlist {pl['name']}")

    if SAVE_PROCESSED_TRACKS:
        with open(PROCESSED_TRACKS_FILE, "w", encoding="utf-8") as f:
            json.dump(list(all_current_duplicates), f, indent=2, ensure_ascii=False)
