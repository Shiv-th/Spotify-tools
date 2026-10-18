from monkey_patch import sp
import re
from collections import defaultdict
import time, os, json, subprocess, sys, signal
from spotipy.exceptions import SpotifyException

subprocess.run(["python", "unlike.py"], check=True)

user_id = sp.current_user()["id"]
MAX_LIMIT = 200

# File Paths
PLAYLISTS_JSON = "json-files/existing_playlists.json"
STATE_JSON = "json-files/pipeline_state.json"

# Global state tracking
global_state = {
    "step": 1,
    "grouped_tracks": defaultdict(lambda: {"liked": [], "others": []}),
    "seen_track_ids": set(),
    "final_output_payload": [],
    "chunk_index": 1,
    "batches_since_last_save": 0,
    "processed_titles": set(),
    "created_playlists_manifest": set(),  # Tracks exact string names ("Unique - 1", etc.) deployed to Spotify
    "_fetched_playlist_ids": [],
}


def save_metadata_file():
    """Utility to safely overwrite the main playlist JSON."""
    with open(PLAYLISTS_JSON, "w", encoding="utf-8") as f:
        json.dump(global_state["final_output_payload"], f, indent=4, ensure_ascii=False)
    print(f"-> Saved incremental progress to '{PLAYLISTS_JSON}'.")


def save_pipeline_state():
    """Serializes the current in-memory processing structures for resumption."""
    serializable_groups = {k: v for k, v in global_state["grouped_tracks"].items()}
    state_payload = {
        "step": global_state["step"],
        "grouped_tracks": serializable_groups,
        "seen_track_ids": list(global_state["seen_track_ids"]),
        "final_output_payload": global_state["final_output_payload"],
        "chunk_index": global_state["chunk_index"],
        "batches_since_last_save": global_state["batches_since_last_save"],
        "processed_titles": list(global_state["processed_titles"]),
        "created_playlists_manifest": list(global_state["created_playlists_manifest"]),
        "_fetched_playlist_ids": global_state.get("_fetched_playlist_ids", []),
        "_target_artists": global_state.get("_target_artists", []),
    }
    with open(STATE_JSON, "w", encoding="utf-8") as f:
        json.dump(state_payload, f, indent=4, ensure_ascii=False)
    print(f"\n[CHECKPOINT] Core pipeline state securely saved to '{STATE_JSON}'.")


def handle_interrupt(signum, frame):
    """Graceful interceptor for Ctrl+C keyboard interrupts."""
    print("\n[!] Execution interrupted! Running emergency state dump...")

    # Check if we were interrupted inside Step 3 while fetching an active playlist
    # We do NOT mark the current playlist as fetched, so it drops and retries next time.
    if global_state["step"] == 3 and "current_fetching_playlist_id" in global_state:
        bad_pl = global_state["current_fetching_playlist_id"]
        print(f"[!] Dropping tracks collected from interrupted playlist ID: {bad_pl}")

        # Prune out tracks added during this interrupted playlist session
        clean_grouped = defaultdict(lambda: {"liked": [], "others": []})
        for title, variations in global_state["grouped_tracks"].items():
            if variations["liked"]:
                clean_grouped[title]["liked"] = variations["liked"]

            # Filter out any track variants whose source belongs to the bad playlist
            clean_others = [
                tup for tup in variations["others"] if tup[1].get("source") != bad_pl
            ]
            if clean_others:
                clean_grouped[title]["others"] = clean_others

            # Re-sync tracking structures
            if not clean_grouped[title]["liked"] and not clean_grouped[title]["others"]:
                del clean_grouped[title]

        global_state["grouped_tracks"] = clean_grouped

        # Rebuild seen track ids from clean set
        global_state["seen_track_ids"] = set()
        for title, var in global_state["grouped_tracks"].items():
            for t_id, _ in var["liked"]:
                global_state["seen_track_ids"].add(t_id)
            for t_id, _ in var["others"]:
                global_state["seen_track_ids"].add(t_id)

    save_pipeline_state()
    save_metadata_file()
    print("[!] Exiting safely. Rerun script to resume from last stable checkpoint.")
    sys.exit(0)


# Register the signal hook
signal.signal(signal.SIGINT, handle_interrupt)


def simplify_title(title):
    while (
        ("(" in title and ")" in title)
        or ("[" in title and "]" in title)
        or "-" in title
    ):
        title = re.sub(r"\(.*?\)|\[.*?\]|-.*", "", title)
    return title.strip().lower()


filter_keywords = [
    "jhankar",
    "pop",
    "afro",
    "beats",
    "stripped",
    "lofi",
    "remix",
    "edit",
    "mix",
    "mashup",
    "bootleg",
    "cut",
    "version",
    "radio edit",
    "extended",
    "club",
    "vip",
    "rework",
    "instrumental",
    "karaoke",
    "demo",
    "acoustic",
    "orchestral",
    "chill",
    "reprise",
    "reimagined",
    "from",
    "live",
    "session",
    "cover",
    "dj",
    "re-edit",
    "remastered",
    "alternate",
    "nightcore",
    "sped up",
    "slowed",
    "8d",
    "3d audio",
    "performance",
    "medley",
    "tribute",
    "theme",
    "score",
    "soundtrack",
    "trap",
    "movie",
    "trailer",
    "rendition",
]


def preference_score(name, title):
    name = name.lower()
    if name == title:
        return 0
    return sum(1 for word in filter_keywords if word in name)


def commit_current_chunks(
    index, chunk_unique, chunk_combined, chunk_combined_for_liked, current_batch_titles
):
    """Uploads track subsets to Spotify dynamically verifying granular completion status."""
    categories = [
        ("Unique", chunk_unique),
        ("Combined", chunk_combined),
        ("Combined for liked", chunk_combined_for_liked),
    ]

    created_any = False
    for cat_name, track_dict in categories:
        if not track_dict:
            continue
        pl_name = f"{cat_name} - {index}"

        if pl_name in global_state["created_playlists_manifest"]:
            print(f"   [Resume Skip] Playlist '{pl_name}' already verified on Spotify.")
            continue

        print(f"   Creating playlist: '{pl_name}' ({len(track_dict)} tracks)...")
        try:
            new_pl = sp.user_playlist_create(user=user_id, name=pl_name, public=False)
            new_pl_id = new_pl["id"]

            for t_id in track_dict.keys():
                track_dict[t_id]["source"] = new_pl_id

            track_ids = list(track_dict.keys())
            for i in range(0, len(track_ids), 100):
                batch_slice = track_ids[i : i + 100]
                sp.playlist_add_items(new_pl_id, batch_slice)
                # Introduce a small artificial delay to stay under Spotify's rate limits
                time.sleep(1.5)

            global_state["final_output_payload"].append(
                {
                    "id": new_pl_id,
                    "name": pl_name,
                    "tracks": len(track_ids),
                    "track_dict": track_dict,
                }
            )

            global_state["created_playlists_manifest"].add(pl_name)
            created_any = True
            print(f"   Successfully deployed and logged '{pl_name}'.")
        except SpotifyException as exc:
            print(f"   [ERROR] Failed to push chunks for '{pl_name}': {exc}")

    if created_any:
        # Crucial Fix: Only consider these titles safely "processed" now that the API didn't crash/interrupt
        global_state["processed_titles"].update(current_batch_titles)

        global_state["batches_since_last_save"] += 1
        if global_state["batches_since_last_save"] % 5 == 0:
            print(
                f"-> [Interval Match] Deployed {global_state['batches_since_last_save']} batches. Saving to JSON..."
            )
            save_metadata_file()


def run_pipeline():
    if os.path.exists(STATE_JSON):
        print(
            "-> Found a previously interrupted pipeline run state. Resuming status..."
        )
        with open(STATE_JSON, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        global_state["step"] = state_data["step"]
        global_state["seen_track_ids"] = set(state_data["seen_track_ids"])
        global_state["final_output_payload"] = state_data["final_output_payload"]
        global_state["chunk_index"] = state_data["chunk_index"]
        global_state["batches_since_last_save"] = state_data.get(
            "batches_since_last_save", 0
        )
        global_state["processed_titles"] = set(state_data["processed_titles"])
        global_state["created_playlists_manifest"] = set(
            state_data.get("created_playlists_manifest", [])
        )
        global_state["_fetched_playlist_ids"] = state_data.get(
            "_fetched_playlist_ids", []
        )
        global_state["_target_artists"] = state_data.get("_target_artists", [])

        global_state["grouped_tracks"] = defaultdict(
            lambda: {"liked": [], "others": []}
        )
        for k, v in state_data["grouped_tracks"].items():
            global_state["grouped_tracks"][k] = v

        print(f"-> Resumed successfully at Step [{global_state['step']}/5].")
    else:
        print("-> Starting fresh pipeline run.")
        with open(PLAYLISTS_JSON, "r", encoding="utf-8") as f:
            global_state["final_output_payload"] = json.load(f)

    # STEP 1 & 2: Structural parsing and initial target filtering
    if global_state["step"] == 1:
        print(
            "[1/5] Extracting current playlists and building target artist filters..."
        )
        target_playlists = []
        target_artists = set()
        other_playlists = []

        for pl in global_state["final_output_payload"]:
            name_lower = pl["name"].lower()
            if "unique" in name_lower or "combined" in name_lower:
                target_playlists.append(pl)
                target_artists.add(pl["name"].rsplit(" - ", 1)[0].strip())
            else:
                other_playlists.append(pl)

        global_state["_target_playlists"] = target_playlists
        global_state["_target_artists"] = list(target_artists)
        global_state["_other_playlists"] = other_playlists
        global_state["step"] = 2

    if global_state["step"] == 2:
        print("[2/5] Filtering Liked Songs against target artists...")
        target_artists = set(global_state.get("_target_artists", []))

        with open("json-files/Liked_Songs.json", "r", encoding="utf-8") as f:
            liked_data = json.load(f)

        filtered_liked_tracks = {}
        for track_id, track in liked_data.get("tracks", {}).items():
            track_artists = track.get("artists", {}).values()
            if any(artist_name in target_artists for artist_name in track_artists):
                filtered_liked_tracks[track_id] = track

        global_state["_filtered_liked_tracks"] = filtered_liked_tracks
        global_state["step"] = 3
        save_pipeline_state()  # Save before starting Step 3 loop

    # STEP 3: Map components and group variants
    if global_state["step"] == 3:
        # Re-derive list structures if lost on state memory clear
        if not global_state.get("_target_playlists"):
            target_playlists = []
            target_artists = set(global_state.get("_target_artists", []))
            other_playlists = []
            for pl in global_state["final_output_payload"]:
                name_lower = pl["name"].lower()
                if not ("unique" in name_lower or "combined" in name_lower):
                    other_playlists.append(pl)
                else:
                    target_playlists.append(pl)
            global_state["_target_playlists"] = target_playlists
            global_state["_other_playlists"] = other_playlists

        filtered_liked_tracks = global_state.get("_filtered_liked_tracks", {})
        other_playlists = global_state.get("_other_playlists", [])
        target_playlists = global_state.get("_target_playlists", [])
        target_artists = set(global_state.get("_target_artists", []))

        if not global_state["seen_track_ids"]:
            print("-> Priority 1: Mapping Filtered Liked Songs...")
            for track_id, track_meta in filtered_liked_tracks.items():
                title = simplify_title(track_meta["name"])
                global_state["grouped_tracks"][title]["liked"].append(
                    (track_id, track_meta)
                )
                global_state["seen_track_ids"].add(track_id)

            print("-> Priority 2: Mapping Other Static Local Playlists...")
            for pl in other_playlists:
                track_dict = pl.get("track_dict", {})
                for track_id, track in track_dict.items():
                    if track_id in global_state["seen_track_ids"]:
                        continue
                    track_artists = track.get("artists", {}).values()
                    if any(
                        artist_name in target_artists for artist_name in track_artists
                    ):
                        title = simplify_title(track["name"])
                        global_state["grouped_tracks"][title]["others"].append(
                            (track_id, track)
                        )
                        global_state["seen_track_ids"].add(track_id)

        print(f"-> Priority 3: Fetching live track metadata for target playlists...")

        for _, pl in enumerate(target_playlists):
            if pl["id"] in global_state.get("_fetched_playlist_ids", []):
                continue

            print(f"   - Pulling tracks from online playlist: '{pl['name']}'")
            playlist_id = pl["id"]

            # Setup the current active context tracking item for interrupt handlers
            global_state["current_fetching_playlist_id"] = playlist_id

            offset = 0
            limit = 100
            while True:
                response = sp.playlist_tracks(playlist_id, limit=limit, offset=offset)
                items = response.get("items", [])
                if not items:
                    break
                for item in items:
                    track = item.get("track")
                    if not track or not track.get("id"):
                        continue
                    track_id = track["id"]
                    if track_id in global_state["seen_track_ids"]:
                        continue
                    track_meta = {
                        "name": track["name"],
                        "artists": {a["id"]: a["name"] for a in track["artists"]},
                        "album": {track["album"]["id"]: track["album"]["name"]},
                        "source": playlist_id,
                        "disc_number": track.get("disc_number", 0),
                        "track_number": track.get("track_number", 0),
                    }
                    title = simplify_title(track["name"])
                    global_state["grouped_tracks"][title]["others"].append(
                        (track_id, track_meta)
                    )
                    global_state["seen_track_ids"].add(track_id)
                offset += limit

            # Playlist processing finished completely without an interrupt hitting
            global_state["_fetched_playlist_ids"].append(playlist_id)
            global_state.pop("current_fetching_playlist_id", None)

            if (len(global_state["_fetched_playlist_ids"])) % 5 == 0:
                print(
                    f"-> [Interval Match] Fetched {len(global_state['_fetched_playlist_ids'])} playlists. Syncing metadata updates..."
                )
                save_metadata_file()
                save_pipeline_state()

        # ONLY advance step context when loop concludes safely!
        global_state["step"] = 4
        save_pipeline_state()

    # STEP 4: Evaluating variants and writing out playlist structures
    if global_state["step"] == 4:
        print("[4/5] Evaluating variants and synchronizing playlist chunks...")

        chunk_unique = {}
        chunk_combined = {}
        chunk_combined_for_liked = {}
        current_batch_titles = (
            []
        )  # Holds titles currently being packed into this chunk batch

        sorted_titles = sorted(global_state["grouped_tracks"].keys())
        total_titles = len(sorted_titles)

        for idx, title in enumerate(sorted_titles, start=1):
            if title in global_state["processed_titles"]:
                continue

            versions = global_state["grouped_tracks"][title]
            temp_unique = {}
            temp_combined = {}
            temp_combined_for_liked = {}

            if versions["liked"]:
                for track_id, meta in versions["liked"]:
                    temp_unique[track_id] = meta
                if versions["others"]:
                    for track_id, meta in versions["liked"]:
                        temp_combined_for_liked[track_id] = meta
                    for track_id, meta in versions["others"]:
                        temp_combined_for_liked[track_id] = meta
            elif versions["others"]:
                sorted_others = sorted(
                    versions["others"],
                    key=lambda x: preference_score(x[1]["name"], title),
                )
                best_track_id, best_meta = sorted_others[0]
                temp_unique[best_track_id] = best_meta
                if len(sorted_others) > 1:
                    for track_id, meta in sorted_others:
                        temp_combined[track_id] = meta

            # Check if adding this item would push us over the threshold boundary
            if (
                len(chunk_unique) + len(temp_unique) > MAX_LIMIT * 2
                or len(chunk_combined) + len(temp_combined) > MAX_LIMIT
                or len(chunk_combined_for_liked) + len(temp_combined_for_liked)
                > MAX_LIMIT
            ):
                print(
                    f"-> Batch processing limit reached ({idx}/{total_titles} processed). Committing to Spotify..."
                )
                commit_current_chunks(
                    global_state["chunk_index"],
                    chunk_unique,
                    chunk_combined,
                    chunk_combined_for_liked,
                    current_batch_titles,
                )

                expected_cats = []
                if chunk_unique:
                    expected_cats.append(f"Unique - {global_state['chunk_index']}")
                if chunk_combined:
                    expected_cats.append(f"Combined - {global_state['chunk_index']}")
                if chunk_combined_for_liked:
                    expected_cats.append(
                        f"Combined for liked - {global_state['chunk_index']}"
                    )

                if all(
                    name in global_state["created_playlists_manifest"]
                    for name in expected_cats
                ):
                    global_state["chunk_index"] += 1

                chunk_unique.clear()
                chunk_combined.clear()
                chunk_combined_for_liked.clear()
                current_batch_titles.clear()  # Empty out the staging list for the next index block

            chunk_unique.update(temp_unique)
            chunk_combined.update(temp_combined)
            chunk_combined_for_liked.update(temp_combined_for_liked)

            # Add to local batch list rather than updating global state immediately
            current_batch_titles.append(title)

        # Handle trailing leftover items
        if chunk_unique or chunk_combined or chunk_combined_for_liked:
            print(
                f"-> Committing final trailing chunk batch {global_state['chunk_index']} to Spotify..."
            )
            commit_current_chunks(
                global_state["chunk_index"],
                chunk_unique,
                chunk_combined,
                chunk_combined_for_liked,
                current_batch_titles,
            )

        global_state["step"] = 5

    # STEP 5: Metadata confirmation and state house-cleaning
    if global_state["step"] == 5:
        print("[5/5] Overwriting final local tracking metadata file...")
        save_metadata_file()

        if os.path.exists(STATE_JSON):
            os.remove(STATE_JSON)
            print("-> Successfully cleared state files.")

        print(f"\nPipeline execution finished. Successfully synced target split sets.")


if __name__ == "__main__":
    run_pipeline()
