import os
import spotipy
import spotipy.oauth2
import urllib.parse
from dotenv import load_dotenv


# --- Monkey Patching ---
def fixed_get_authorize_url(self):
    params = {
        "client_id": self.client_id,
        "response_type": "code",
        "redirect_uri": self.redirect_uri,
        "scope": self.scope,
        **getattr(self, "_extra_auth_params", {}),  # safe fallback
    }
    return f"{self.OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


# Apply the patch immediately upon import
spotipy.oauth2.SpotifyOAuth.get_authorize_url = fixed_get_authorize_url

# --- Shared Client Setup ---
config_env = os.path.join(os.path.dirname(__file__), "config", ".env")
root_env = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(config_env):
    load_dotenv(config_env)
elif os.path.exists(root_env):
    load_dotenv(root_env)
else:
    load_dotenv()

SCOPES = [
    # Images
    "ugc-image-upload",
    # Spotify Connect
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    # Playback SDK
    "app-remote-control",
    "streaming",
    # Playlists
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
    # Follow
    "user-follow-read",
    "user-follow-modify",
    # Listening History
    "user-read-playback-position",
    "user-top-read",
    "user-read-recently-played",
    # Library
    "user-library-read",
    "user-library-modify",
    # Users
    "user-read-email",
    "user-read-private",
]

config_cache = os.path.join(os.path.dirname(__file__), "config", ".cache")

# Instantiate shared Spotipy client
sp = spotipy.Spotify(
    auth_manager=spotipy.oauth2.SpotifyOAuth(
        client_id=os.getenv("SPOTIPY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
        scope=" ".join(SCOPES),
        cache_path=config_cache,
        show_dialog=True,
    ),
    requests_timeout=30,
)
