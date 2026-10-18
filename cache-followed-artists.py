from monkey_patch import sp
import json, os

FILENAME = "Followed_Artists.json"
TO_AVOID_FILE = "to_avoid.json"


def load_cache(filename):
    if not os.path.exists(f"json-files/{filename}"):
        return {} if filename == FILENAME else []
    with open(f"json-files/{filename}", "r", encoding="utf-8") as f:
        return json.load(f)


def save_cache(filename, data):
    with open(f"json-files/{filename}", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_current_followed_artists():
    """Fetch the complete current followed artist list from Spotify."""
    all_artists = {}
    after = None

    while True:
        response = sp.current_user_followed_artists(limit=50, after=after)
        items = response["artists"]["items"]
        if not items:
            break

        for artist in items:
            artist_id = artist["id"]
            all_artists[artist_id] = {"name": artist["name"]}

        if response["artists"]["next"] is None:
            break

        after = items[-1]["id"]
        # time.sleep(1.5)

    return all_artists


if __name__ == "__main__":
    # Load old data
    old_artists = load_cache(FILENAME)
    old_ids = set(old_artists.keys())

    # Load already avoided list
    to_avoid = set(load_cache(TO_AVOID_FILE))

    # Get full current followed artist list
    current_artists = get_current_followed_artists()
    current_ids = set(current_artists.keys())

    # Detect unfollowed artists
    unfollowed_ids = old_ids - current_ids
    if unfollowed_ids:
        print(
            f"{len(unfollowed_ids)} artists unfollowed. Moving them to {TO_AVOID_FILE}"
        )
        # Add to avoid list
        to_avoid.update(unfollowed_ids)
        save_cache(TO_AVOID_FILE, list(to_avoid))
        # Remove from Followed_Artists.json
        for uid in unfollowed_ids:
            old_artists.pop(uid, None)

    # Detect new artists
    new_ids = current_ids - old_ids
    if new_ids:
        print(f"Found {len(new_ids)} new artists.")
        for uid in new_ids:
            old_artists[uid] = current_artists[uid]
    else:
        print("No new artists found.")

    # Save updated Followed_Artists.json
    save_cache(FILENAME, old_artists)
