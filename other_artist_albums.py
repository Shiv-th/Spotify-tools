from monkey_patch import sp
import os, json, subprocess, copy
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


def get_artists(cache_file="Other_Artists.json"):
    return load_cache(cache_file)


def get_artist_albums_by_type(artist_id, album_type):
    global spc, spc_index
    offset = 0
    count = 0
    album_ids = []
    while True:
        try:
            response = sp.artist_albums(
                artist_id=artist_id,
                album_type=album_type,
                limit=50,
                offset=offset,
                country="IN",
            )
            count += 1
        except SpotifyException as e:
            if e.http_status == 429:
                print(f"{'-'*100}\nRate limit hit for client\n{'-'*100}")
                exit()
            continue
        except Exception as e:
            print(f"Non-Spotify exception: {e}")
            continue

        items = response.get("items", [])
        if not items:
            break
        album_ids.extend(item["id"] for item in items)
        offset += len(items)
        if count % 10 == 0:
            print(f"Collected {len(album_ids)} so far")
        if len(items) < 50:
            break
    return album_ids, count


artists_to_avoid = load_cache("to_avoid.json")
count_artist = 1
count = 0
all_artists = load_cache("Other_Artists.json")

for aid, artist in all_artists.items():
    try:
        atemp = copy.deepcopy(artist)
        if "unprocessed_album_ids" in artist or aid in artists_to_avoid:
            continue
        album_ids = set()
        for album_type in ["album", "single", "appears_on", "compilation"]:
            album_idsi, counti = get_artist_albums_by_type(aid, album_type)
            album_ids.update(album_idsi)
            count += counti
        artist["unprocessed_album_ids"] = list(album_ids)
        artist["unprocessed"] = len(album_ids)
        artist["last_updated"] = (datetime.now() - timedelta(days=4)).strftime(
            "%Y-%m-%d"
        )
        print(f"{count_artist}. {artist['name']} - {len(album_ids)} albums")
        if count_artist % 20 == 0:
            print(f"{'-'*100}\n{count} albums calls used\n{'-'*100}")
            save_cache("Other_Artists.json", all_artists)
        count_artist += 1

    except KeyboardInterrupt:
        all_artists[aid] = atemp
        save_cache("Other_Artists.json", all_artists)
        print(f"\nInterrupted! Processed {count}.")
        exit()

save_cache("Other_Artists.json", all_artists)
print(f"Finished. Total {count}.")
