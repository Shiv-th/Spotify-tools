from monkey_patch import sp
import re
from collections import defaultdict
import os, json, subprocess
from datetime import datetime, timedelta
from spotipy.exceptions import SpotifyException

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


def get_artist_albums_by_type(artist_id, album_type, new_album_ids, last_updated):
    count = 0
    offset = 0
    limit = 50
    album_ids = []
    flag = False

    while True:
        try:
            response = sp.artist_albums(
                artist_id=artist_id,
                album_type=album_type,
                limit=limit,
                offset=offset,
                country="IN",
            )
        except SpotifyException as e:
            if e.http_status == 429:
                print(f"Rate limit hit for client.")
                exit()
        except Exception as e:
            print(e)
            continue
        count += 1
        items = response.get("items", [])
        if not items:
            break

        for item in items:
            release_date = item["release_date"]
            precision = item.get("release_date_precision", "day")
            try:
                if precision == "day":
                    date_obj = datetime.strptime(release_date, "%Y-%m-%d")
                elif precision == "month":
                    date_obj = datetime.strptime(release_date, "%Y-%m")
                else:
                    date_obj = datetime.strptime(release_date, "%Y")
            except ValueError:
                continue  # Skip malformed dates

            if last_updated and date_obj < last_updated:
                flag = True
                continue

            if item["id"] not in new_album_ids and item["id"] not in album_ids:
                album_ids.append(item["id"])

        offset += limit
        if len(items) < limit or flag:
            break

    return album_ids, count


def update_playlist(name, track_ids, stored_playlist):
    user_id = sp.current_user()["id"]

    if not stored_playlist:
        stored_playlist = sp.user_playlist_create(
            user=user_id, name=name, public=False
        )["id"]

    for i in range(0, len(track_ids), 100):
        sp.playlist_add_items(stored_playlist, track_ids[i : i + 100])

    print(f"Updated playlist: {name} with {len(track_ids)} tracks")
    return stored_playlist


def make_artist_playlist(artist_id, artist, liked_data):
    count = 0
    artist_name = artist["name"]
    last_updated = artist.get("last_updated", None)
    if last_updated:
        last_updated = datetime.strptime(last_updated, "%Y-%m-%d")
    old_album_ids = artist.get("processed_album_ids", [])
    new_album_ids = artist.get("unprocessed_album_ids", [])

    artist_playlists = artist.get("playlists", {})
    unique_playlist = artist_playlists.get("unique")
    combined_for_liked = artist_playlists.get("combined_for_liked")
    combined = artist_playlists.get("combined")

    print("Starting Album gathering")
    for album_type in ["album", "single", "appears_on", "compilation"]:
        new_album_idsi, counti = get_artist_albums_by_type(
            artist_id, album_type, old_album_ids + new_album_ids, last_updated
        )
        new_album_ids += new_album_idsi
        count += counti
    print(f"\nProcessing {len(new_album_ids)} new albums for {artist_name}")

    # if True:
    #     artist["unprocessed_album_ids"] = new_album_ids
    #     artist["unprocessed"] = len(new_album_ids)
    #     return count

    grouped_tracks = defaultdict(lambda: {"liked": [], "others": []})
    processed_combinations = set()

    def simplify_title(title):
        while (
            ("(" in title and ")" in title)
            or ("[" in title and "]" in title)
            or "-" in title
        ):
            title = re.sub(r"\(.*?\)|\[.*?\]|-.*", "", title)
        return title.strip().lower()

    def get_artist_names(track_id):
        return tuple(liked_data[track_id]["artists"].values())

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

    # Process liked songs
    for track_id, track in artist.get("liked_tracks", {}).items():
        track_name = track
        title = simplify_title(track_name)
        artist_names = get_artist_names(track_id)
        key = (track_name.lower(), artist_names)
        grouped_tracks[title]["liked"].append(track_id)
        processed_combinations.add(key)

    # Process albums
    failed_album_ids = []

    alb_num = 1
    no_of_albums = len(new_album_ids)
    for album_id in new_album_ids:
        if alb_num % 25 == 0:
            print(f"Processing album no. {alb_num} / {no_of_albums}")
        alb_num += 1
        count += 1
        try:
            album_tracks = sp.album_tracks(album_id=album_id)["items"]
        except SpotifyException as e:
            if e.http_status == 429:
                print(f"Rate limit hit for client.")
                exit()
            else:
                print(f"Skipping album {album_id} due to error: {e}")
            failed_album_ids.append(album_id)
            continue

        except Exception as e:
            print(f"Skipping album {album_id} due to error: {e}")
            failed_album_ids.append(album_id)
            continue

        for track in album_tracks:
            if artist_name not in [a["name"] for a in track["artists"]]:
                continue

            track_id = track["id"]
            duration_ms = track.get("duration_ms", 0)
            if duration_ms > 600_000:
                continue
            track_name = track["name"]
            title = simplify_title(track_name)
            artist_names = tuple([a["name"] for a in track["artists"]])
            key = (track_name.lower(), artist_names)
            if key in processed_combinations:
                continue
            grouped_tracks[title]["others"].append((track_id, track_name))
            processed_combinations.add(key)

    print(f"Processing {len(processed_combinations)} tracks")

    unique_songs = []
    unique_songs_seen = set()

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
        "unique": (unique_songs, unique_playlist),
        "combined": (combined_songs, combined),
        "combined for liked": (rejected_liked, combined_for_liked),
    }

    artist["playlists"] = {}

    songs_unique, playlist_unique = playlist_data["unique"]
    songs_combined, playlist_combined = playlist_data["combined"]
    songs_combined_for_liked, playlist_combined_for_liked = playlist_data[
        "combined for liked"
    ]
    songs_liked, _ = playlist_data["liked"]

    if len(songs_unique) > 0 and len(songs_unique) != len(songs_liked):
        artist["playlists"]["unique"] = update_playlist(
            f"{artist_name} - Unique", songs_unique, playlist_unique
        )

    if len(songs_combined) > 0:
        artist["playlists"]["combined"] = update_playlist(
            f"{artist_name} - Combined", songs_combined, playlist_combined
        )

    if len(songs_combined_for_liked) > 0:
        artist["playlists"]["combined for liked"] = update_playlist(
            f"{artist_name} - Combined for liked",
            songs_combined_for_liked,
            playlist_combined_for_liked,
        )

    artist["processed_album_ids"] = old_album_ids + new_album_ids
    artist["unprocessed_album_ids"] = failed_album_ids
    artist["unprocessed"] = len(failed_album_ids)
    return count


if __name__ == "__main__":
    count = 0
    liked_tracks = get_liked_tracks()
    artists = get_followed_artists()
    date_time = datetime.now() - timedelta(days=7)
    iso_date = date_time.strftime("%Y-%m-%d")
    artists = sorted(
        artists.items(), key=lambda x: -x[1].get("unprocessed", float("inf"))
    )
    for artist_id, artist in artists:
        if artist["unprocessed"] > 50:
            continue
        print(f"\nProcessing {artist['name']}")
        count += make_artist_playlist(artist_id, artist, liked_tracks)
        artist["last_updated"] = iso_date
        save_cache("Followed_Artists.json", dict(artists))
        print(count)
        # if count > 4500:
        #     break
