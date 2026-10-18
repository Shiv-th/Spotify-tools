from monkey_patch import sp
import re
from collections import defaultdict
import os, json, subprocess

subprocess.run(["python", "artist_liked_songs.py"], check=True)


def load_cache(Filename):
    if not os.path.exists(f"json-files/{Filename}"):
        return None
    with open(f"json-files/{Filename}", "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(Filename, data):
    with open(f"json-files/{Filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_liked_tracks(cache_file="liked_songs.json"):
    return load_cache(cache_file)["tracks"]


def get_followed_artists(cache_file="Followed_Artists.json"):
    return load_cache(cache_file)


def get_playlist_tracks(playlist_id, name):
    tracks_data = []
    results = None
    offset = 0
    limit = 100
    count = 0

    while True:
        results = sp.playlist_items(
            playlist_id,
            fields="items.track(id,name),next,total,duration_ms",
            limit=limit,
            offset=offset,
        )
        count += 1

        for item in results["items"]:
            track = item.get("track")
            if track:
                if track.get("duration_ms", 0) > 600000:
                    continue
                track_id = track.get("id")
                track_name = track.get("name")
                artist_ids = []
                artists_list = track.get("artists", [])
                for artist in artists_list:
                    if artist.get("id"):
                        artist_ids.append(artist["id"])

                if track_id and track_name:
                    tracks_data.append(
                        {
                            "id": track_id,
                            "name": track_name,
                            "artists": artist_ids,
                        }
                    )

        offset += limit
        if results["next"] is None:
            break  # No more pages

    print(f"Successfully fetched {len(tracks_data)} tracks for {name}.")
    return tracks_data, count


def update_playlist(name, track_ids, stored_playlist):
    count = 0
    user_id = sp.current_user()["id"]

    if not stored_playlist:
        stored_playlist = sp.user_playlist_create(
            user=user_id, name=name, public=False
        )["id"]
        count += 1
    sp.playlist_replace_items(stored_playlist, [])
    count += 1

    for i in range(0, len(track_ids), 100):
        sp.playlist_add_items(stored_playlist, track_ids[i : i + 100])
        count += 1

    print(f"Updated playlist: {name} with {len(track_ids)} tracks")
    return stored_playlist, count


def refactor(artist, all_tracks):
    count = 0
    artist_name = artist["name"]
    playlists = artist.get("playlists", {})

    grouped_tracks = defaultdict(lambda: {"liked": [], "others": []})

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
        "lo fi",
        "lo-fi",
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
    n = 0

    def preference_score(name, title):
        name = name.lower()
        if name == title:
            return 0
        normalized = re.sub(r"[^a-z0-9\s-]", "", name)
        return sum(1 for word in filter_keywords if word in normalized) + sum(
            0.5 for word in filter_keywords if word in normalized
        )

    for track_id, track_name in artist.get("liked_tracks", {}).items():
        title = simplify_title(track_name)
        grouped_tracks[title]["liked"].append(track_id)
        n += 1

    for track in all_tracks:
        track_id = track["id"]
        if track_id in artist.get("liked_tracks", {}).keys():
            continue
        track_name = track["name"].lower()
        title = simplify_title(track_name)
        grouped_tracks[title]["others"].append((track_id, track_name))
        n += 1

    print(f"\nProcessing {n} tracks")

    unique_songs = []
    unique_songs_seen = set()  # To track uniqueness while preserving order

    combined_songs = []
    combined_songs_seen = set()

    rejected_liked = []
    rejected_liked_seen = set()

    liked_songs = []
    liked_songs_seen = set()

    for title in sorted(grouped_tracks):
        versions = grouped_tracks[title]

        if versions["liked"]:
            if versions["others"]:
                for track_id in versions["liked"]:
                    if track_id not in rejected_liked_seen:
                        rejected_liked.append(track_id)
                        rejected_liked_seen.add(track_id)
                    if track_id not in unique_songs_seen:
                        unique_songs.append(track_id)
                        unique_songs_seen.add(track_id)
                    if track_id not in liked_songs_seen:
                        liked_songs.append(track_id)
                        liked_songs_seen.add(track_id)
                for track_id, _ in versions["others"]:
                    if track_id not in rejected_liked_seen:
                        rejected_liked.append(track_id)
                        rejected_liked_seen.add(track_id)

            else:
                for track_id in versions["liked"]:
                    if track_id not in unique_songs_seen:
                        unique_songs.append(track_id)
                        unique_songs_seen.add(track_id)
                    if track_id not in liked_songs_seen:
                        liked_songs.append(track_id)
                        liked_songs_seen.add(track_id)

        elif versions["others"]:
            sorted_others = sorted(
                versions["others"], key=lambda x: preference_score(x[1], title)
            )
            best_track_id = sorted_others[0][0]
            if best_track_id not in unique_songs_seen:
                unique_songs.append(best_track_id)
                unique_songs_seen.add(best_track_id)

            if len(sorted_others) > 1:
                for track_id, _ in sorted_others:
                    if track_id not in combined_songs_seen:
                        combined_songs.append(track_id)
                        combined_songs_seen.add(track_id)

    playlist_data = {
        "unique": (unique_songs, playlists.get("unique", None)),
        "combined": (combined_songs, playlists.get("combined", None)),
        "combined for liked": (
            rejected_liked,
            playlists.get("combined for liked", None),
        ),
        "liked": (liked_songs, playlists.get("liked", None)),
    }
    artist["playlists"] = {}
    for name, songs in playlist_data.items():
        if len(songs[0]) > 0:
            artist["playlists"][name], icount = update_playlist(
                f"{artist_name} - {name.capitalize()}", songs[0], songs[1]
            )
            count += icount
    return count


artists = get_followed_artists()
count = 0
for artist in list(artists.values()):
    playlists = artist.get("playlists", {})
    if len(playlists) > 1:
        # if artist["name"] in ["Dua Lipa", "Ed Sheeran", "Justin Bieber"]:
        print(f"Processing {artist['name']}")
        all_tracks = []
        for pl, pl_id in playlists.items():
            temp_tracks, icount = get_playlist_tracks(pl_id, pl)
            all_tracks.extend(temp_tracks)
            count += icount
        seen_ids = set()
        unique_tracks = []
        for track in all_tracks:
            if track["id"] not in seen_ids:
                unique_tracks.append(track)
                seen_ids.add(track["id"])
        all_tracks = unique_tracks
        count += refactor(artist, all_tracks)
        # save_cache("Followed_Artists.json", artists)
print(count)
