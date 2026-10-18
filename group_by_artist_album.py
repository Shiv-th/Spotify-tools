from monkey_patch import sp
import json
import os
import random, time
from tqdm import tqdm

SOURCE_PLAYLIST_IDS = [
    "1mewwylzEOiGGF0IbweBJI",  # Artist Completes 1
]

TARGET_PLAYLIST_IDS = [
    "1mewwylzEOiGGF0IbweBJI",  # Artist Completes 1
]


JSON_PATH = "json-files/existing_playlists.json"
BASE_PLAYLIST_NAME = "Artist Ordered Playlist"
MAX_TRACKS_PER_PLAYLIST = 8000
BATCH_SIZE = 100
USE_LOCAL_CACHE = False  # Set to True to read from JSON if available

# =========================
# FETCH & STORAGE
# =========================


def save_tracks_to_json(playlist_id, tracks, playlist_name):
    """Saves fetched tracks into the specific JSON format provided."""
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)

    all_playlists_data = []
    if os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            try:
                all_playlists_data = json.load(f)
            except json.JSONDecodeError:
                all_playlists_data = []

    # Map Spotify track objects to your custom JSON schema
    track_dict = {}
    for t in tracks:
        track_dict[t["id"]] = {
            "name": t["name"],
            "artists": {a["id"]: a["name"] for a in t["artists"]},
            "album": {t["album"]["id"]: t["album"]["name"]},
            "source": playlist_id,
            "disc_number": t.get("disc_number", 0),
            "track_number": t.get("track_number", 0),
        }

    new_entry = {
        "id": playlist_id,
        "name": playlist_name or f"Playlist {playlist_id}",
        "tracks": len(tracks),
        "track_dict": track_dict,
    }

    # Update entry if exists, otherwise append
    existing_idx = next(
        (i for i, p in enumerate(all_playlists_data) if p["id"] == playlist_id), -1
    )
    if existing_idx > -1:
        all_playlists_data[existing_idx] = new_entry
    else:
        all_playlists_data.append(new_entry)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(all_playlists_data, f, indent=2, ensure_ascii=False)


def fetch_playlist_tracks(playlist_id, use_local=False):
    """Fetches from JSON if flag is True and file exists, else fetches from API."""
    if use_local and os.path.exists(JSON_PATH):
        with open(JSON_PATH, "r", encoding="utf-8") as f:
            local_data = json.load(f)
            playlist_data = next(
                (p for p in local_data if p["id"] == playlist_id), None
            )

            if playlist_data:
                print(
                    f"\n[Local] Loading {len(playlist_data['track_dict'])} tracks for {playlist_id}"
                )
                reconstructed = []
                for t_id, t_info in playlist_data["track_dict"].items():
                    reconstructed.append(
                        {
                            "id": t_id,
                            "uri": f"spotify:track:{t_id}",
                            "name": t_info["name"],
                            "artists": [
                                {"id": k, "name": v}
                                for k, v in t_info["artists"].items()
                            ],
                            "album": {
                                "id": list(t_info["album"].keys())[0],
                                "name": list(t_info["album"].values())[0],
                            },
                            "disc_number": t_info.get("disc_number", 0),
                            "track_number": t_info.get("track_number", 0),
                        }
                    )
                return reconstructed

    # API Fetch Logic
    print(f"\n[API] Fetching tracks for {playlist_id}...")
    tracks = []
    offset = 0
    while True:
        resp = sp.playlist_items(
            playlist_id, offset=offset, limit=100, additional_types=["track"]
        )
        tracks.extend(
            item["track"]
            for item in resp["items"]
            if item["track"] and item["track"]["artists"]
        )
        if resp["next"] is None:
            break
        offset += 100

    playlist_meta = sp.playlist(playlist_id)
    playlist_name = playlist_meta["name"]
    save_tracks_to_json(playlist_id, tracks, playlist_name)
    return tracks


# =========================
# CORE LOGIC
# =========================


def artist_id_set(track):
    return {a["id"] for a in track["artists"]}


def build_contiguous_artist_groups(tracks):
    groups = []
    current_group = []
    common_artists = None

    for track in tracks:
        artists = artist_id_set(track)
        if not current_group:
            current_group = [track]
            common_artists = artists.copy()
            continue

        intersection = common_artists & artists
        if intersection:
            current_group.append(track)
            common_artists = intersection
        else:
            groups.append(current_group)
            current_group = [track]
            common_artists = artists.copy()

    if current_group:
        groups.append(current_group)
    return groups


def reorder_group_by_album(group):
    albums = {}
    for track in group:
        album_id = track["album"]["id"]
        albums.setdefault(album_id, []).append(track)

    for album in albums.values():
        album.sort(key=lambda t: (t["disc_number"], t["track_number"]))

    album_groups = list(albums.values())
    random.shuffle(album_groups)
    return [t for album in album_groups for t in album]


def group_artist_set(group):
    artists = set(artist_id_set(group[0]))
    for track in group[1:]:
        artists &= artist_id_set(track)
        if not artists:
            break
    return artists


def merge_groups_by_priority(groups):
    merged_groups = []
    merged_artist_sets = []

    for group in groups:
        g_artists = group_artist_set(group)
        merged = False
        for i, base_artists in enumerate(merged_artist_sets):
            if base_artists & g_artists:
                merged_groups[i].extend(group)
                merged_artist_sets[i] &= g_artists
                merged = True
                break
        if not merged:
            merged_groups.append(group[:])
            merged_artist_sets.append(g_artists.copy())
    return merged_groups


# =========================
# PLAYLIST WRITING
# =========================


def create_new_playlist(base_name, index):
    user_id = sp.me()["id"]
    playlist = sp.user_playlist_create(
        user=user_id,
        name=f"{base_name} ({index})",
        public=False,
        description="Auto-generated (artist-grouped, album-ordered)",
    )
    return playlist["id"]


def clear_playlist(pid):
    sp.playlist_replace_items(pid, [])


def add_tracks_batched(pid, uris):
    for i in range(0, len(uris), BATCH_SIZE):
        sp.playlist_add_items(pid, uris[i : i + BATCH_SIZE])


def write_groups_across_playlists(groups, initial_playlists):
    remaining_groups = groups[:]
    playlist_ids = initial_playlists[:]
    playlist_index = 0
    total_playlists_used = len(playlist_ids)

    BUFFER_THRESHOLD = 1000
    total_tracks = sum(len(g) for g in groups)
    pbar = tqdm(total=total_tracks, desc="Writing tracks", unit="track")

    #  NEW: store final tracks per playlist
    playlist_track_map = {}

    while remaining_groups:
        if playlist_index >= len(playlist_ids):
            total_playlists_used += 1
            pid = create_new_playlist(BASE_PLAYLIST_NAME, total_playlists_used)
            playlist_ids.append(pid)
            print(f"\nCreated: https://open.spotify.com/playlist/{pid}")
        else:
            pid = playlist_ids[playlist_index]
            clear_playlist(pid)
            print(f"\nFilling: https://open.spotify.com/playlist/{pid}")

        current_playlist_count = 0
        track_buffer = []

        # NEW: track objects (not just URIs)
        playlist_track_map[pid] = []

        while True:
            space_left = MAX_TRACKS_PER_PLAYLIST - current_playlist_count
            best_fit_idx = -1

            for i, group in enumerate(remaining_groups):
                if len(group) <= space_left:
                    best_fit_idx = i
                    break

            if best_fit_idx == -1:
                break

            selected_group = remaining_groups.pop(best_fit_idx)

            # ✅ store full track objects
            playlist_track_map[pid].extend(selected_group)

            group_uris = [t["uri"] for t in selected_group]
            track_buffer.extend(group_uris)
            current_playlist_count += len(selected_group)
            pbar.update(len(selected_group))

            if len(track_buffer) >= BUFFER_THRESHOLD:
                add_tracks_batched(pid, track_buffer)
                track_buffer = []
                time.sleep(0.3)

        if track_buffer:
            add_tracks_batched(pid, track_buffer)

        playlist_index += 1

    pbar.close()

    # ✅ NEW: Save each playlist separately
    print("\nSaving final playlist distributions to JSON...")
    for pid, tracks in playlist_track_map.items():
        playlist_meta = sp.playlist(pid)
        playlist_name = playlist_meta["name"]

        save_tracks_to_json(pid, tracks, playlist_name)

    return playlist_ids


# =========================
# MAIN EXECUTION
# =========================

if __name__ == "__main__":
    print("Fetching source playlists...")
    all_tracks = []
    for pid in tqdm(SOURCE_PLAYLIST_IDS, desc="Fetching Source"):
        all_tracks.extend(fetch_playlist_tracks(pid, use_local=USE_LOCAL_CACHE))

    print(f"\nTotal tracks fetched: {len(all_tracks)}")
    print("Building artist groups...")
    groups = build_contiguous_artist_groups(all_tracks)
    groups = merge_groups_by_priority(groups)

    print(f"Total groups after merge: {len(groups)}")
    print("Reordering groups internally and randomizing sequence...")
    groups = [reorder_group_by_album(g) for g in groups]
    random.shuffle(groups)

    print("Writing to target playlists...")
    write_groups_across_playlists(groups, TARGET_PLAYLIST_IDS)
    print("\nDone.")
