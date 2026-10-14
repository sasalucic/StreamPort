# StreamPort

**Self-hosted personal media library, playback and request management.** StreamPort serves movies and television episodes from folders you control. It offers a web UI, Android phone and Android TV clients, and a native Roku channel. It can enrich titles with metadata, show Radarr/Sonarr activity, and submit moderated requests to **Seerr**.

> **Project status:** Independent community project; server/web **v0.7.5**, Android phone **v1.7.0**, Android TV **v1.6.0**, Roku **v1.1.0** (source snapshot). Self-hosted software, **not** a streaming catalog or source of media. The project does not download torrents or provide indexers, credentials, media files or access to third-party content. Use only media you are authorized to access.

## Contents

- [Features](#features)
- [How the services fit together](#how-the-services-fit-together)
- [Requirements](#requirements)
- [Quick start: Ubuntu + Docker Compose](#quick-start-ubuntu--docker-compose)
- [Connect Seerr, Radarr, Sonarr and qBittorrent](#connect-seerr-radarr-sonarr-and-qbittorrent)
- [Metadata and subtitles](#metadata-and-subtitles)
- [Phone, TV and Roku clients](#phone-tv-and-roku-clients)
- [Running without Docker](#running-without-docker)
- [Maintenance, upgrades and backups](#maintenance-upgrades-and-backups)
- [Development and tests](#development-and-tests)
- [Security and limitations](#security-and-limitations)
- [License and contributing](#license-and-contributing)

## Features

- **Library:** Scan multiple movie/TV folders without moving or renaming files; organize films, shows, seasons, and episodes; posters, collections, watch history, favorites, and playback resume.
- **Playback:** Direct Play when the client supports the source codecs; server-side FFmpeg conversion to compatible H.264/AAC MP4 when necessary; seek, audio selection and subtitle support.
- **Accounts:** First-run administrator setup, viewer accounts, per-user viewing history, session cookies and server-side protection for credentials.
- **Requests:** Search and submit through Seerr; viewer submissions go into a **local admin approval queue** before being forwarded; administrators can review them. Avoids duplicate requests and tracks local/requested availability.
- **Arr status:** Optional direct connection to Radarr and Sonarr for media file metadata/path reconciliation, connection tests and queue status.
- **Metadata:** TMDb matching plus optional OMDb ratings and Fanart.tv assets. Optional OpenSubtitles.com text subtitle search and downloads.
- **Clients:** Responsive web UI, Android WebView apps for phone and Android TV, native Roku SceneGraph/BrightScript client.

StreamPort is **not** Jellyfin, Plex, a torrent client, an indexer, a Seerr replacement or a downloader. It works alongside those services; it does not need a Jellyfin/Plex server.

## Repository layout

| Path | Contents |
| --- | --- |
| `server/` | Python HTTP server, SQLite state, FFmpeg pipeline, web UI (`static/`), Docker deployment, automated tests |
| `android/` | Java Android phone client, Gradle project and tests |
| `android-tv/` | Java Android TV client, Gradle project and tests |
| `roku/` | Roku SceneGraph/BrightScript source, package manifest and tests |
| `docs/INTEGRATIONS.md` | Detailed Seerr, Radarr, Sonarr, qBittorrent, storage/path mapping and troubleshooting |
| `docs/SECURITY.md` | Network deployment, secrets, backups and release safety |
| `LICENSE` | MIT license for the project's own code (third-party dependencies retain their own licenses) |

## How the services fit together

```text
Browsers / Android phone / Android TV / Roku
                       |
                       v
              StreamPort :8097
              |        |         \
       /media/movies  /media/tv   SQLite data directory
              |
       metadata & playback
              |
              +--> TMDb / OMDb / Fanart.tv / OpenSubtitles (optional)
              +--> Radarr :7878 (movie file metadata / queue)
              +--> Sonarr :8989 (TV file metadata / queue)
              +--> Seerr :5055 (search and approved requests)
                         |
                  Radarr / Sonarr
                         |
                qBittorrent Web UI (configured in *Arr)
                         |
                   downloads / import
                         |
                   media directories
                         |
                 StreamPort rescans
```

**Important:** There is **no direct StreamPort → qBittorrent API integration** in this version. Add qBittorrent as a *download client* in **Radarr and Sonarr**. Configure Seerr to talk to Radarr/Sonarr; StreamPort then talks to Seerr for requests. StreamPort does not configure those other products for you.

## Requirements

- Ubuntu/Linux host with Docker Engine and **Docker Compose v2** (recommended). Other Linux hosts with Compose can work, but aren't the primary documented target.
- Existing folders containing media you own or are authorized to use, accessible by the Docker user. Paths must be **absolute paths on the host**.
- Port **8097/TCP** for StreamPort (configurable on the host), sufficient disk space for SQLite/cache/subtitles, and a CPU capable of FFmpeg conversion if Direct Play is not possible.
- Optional services: Seerr (often port `5055`), Radarr (`7878`), Sonarr (`8989`), and qBittorrent (Web UI port is configurable; commonly `8080`). These are examples, **not** hard-coded endpoints.
- For standalone development: Python 3.11+ (Docker uses 3.12), `ffmpeg`, `ffprobe`, Python package `cryptography`; Node.js for JavaScript tests; JDK 17/Android SDK 35 for Android builds; Node.js/npm for Roku builds.

### Quick start: Ubuntu + Docker Compose

**1. Install Docker Engine and the Compose plugin**, following the [official Ubuntu guide](https://docs.docker.com/engine/install/ubuntu/). Confirm they work:

```bash
docker --version
docker compose version
docker info
```

**2. Clone the repository**, or download and extract its source ZIP. Replace the URL below with your own GitHub repository URL if using a fork:

```bash
git clone https://github.com/YOUR_USERNAME/StreamPort.git
cd StreamPort/server
```

**3. Configure private host paths.** The interactive setup helper can create `.env` for you:

```bash
bash setup.sh
```

Alternatively:

```bash
cp .env.example .env
nano .env
```

Example `.env` values (replace paths and IDs as needed):

```dotenv
MOVIES_PATH=/srv/media/movies
TV_PATH=/srv/media/tv
PUID=1000
PGID=1000
STREAMPORT_PORT=8097
BIND_ADDRESS=0.0.0.0
MAX_TRANSCODES=1
COOKIE_SECURE=false
OPENSUBTITLES_API_KEY=
```

Create the two folders before starting; Docker Compose is intentionally configured not to silently create missing host media directories. `PUID`/`PGID` should identify a user that **can read both media folders** and **write to `server/data/`**. Check via `id -u`, `id -g`, `ls -ld /srv/media/movies /srv/media/tv`. `BIND_ADDRESS=0.0.0.0` allows LAN access; prefer `127.0.0.1` if a reverse proxy runs on the host. The files in `.env` and `data/` are private and excluded by `.gitignore`.

**4. Start the service** (skip this if `setup.sh` already started it):

```bash
mkdir -p data
chmod 700 data
docker compose config --quiet
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail=100 streamport
```

**5. Open StreamPort** in a browser at `http://YOUR_SERVER_HOST:8097`. Use your host's reachable LAN DNS name or IP address. On first launch create the **administrator** account with a strong password (minimum 10 characters), then open **Settings** and configure integrations. Start a library scan from the dashboard; the background maintenance loop also scans periodically. A local check from the host is:

```bash
curl http://127.0.0.1:8097/api/health
```

The server maps host movie/TV folders **read-only** to `/media/movies` and `/media/tv` inside the container. `server/data/` stores the SQLite database, encryption key, subtitle downloads and generated thumbnails. **Do not put `data/` in Git.**

### Connect Seerr, Radarr, Sonarr and qBittorrent

Complete the following in order. See [detailed service configuration](docs/INTEGRATIONS.md) for host vs. Docker DNS, media path mapping and failure diagnostics.

**1. Set up Radarr and Sonarr independently.** Configure their root folders and indexers (if used) and verify they can import your existing media. Their movie/series directories must be accessible to StreamPort via `MOVIES_PATH` and `TV_PATH`. StreamPort does not share authentication with them.

**2. Set up qBittorrent inside Radarr and Sonarr, not StreamPort.** In each *Arr app go to **Settings → Download Clients → + → qBittorrent**, set the Web UI hostname/port and qBittorrent credentials, and test the connection. Prefer distinct categories such as `radarr` and `sonarr`, with sensible completed-download/import handling. Ensure *Arr can see completed files; misaligned Docker volume paths are a common cause of import failures. Do not expose the qBittorrent Web UI directly to the internet.

**3. Set up Seerr.** Under its **Settings → Services**, add Radarr and Sonarr with their API keys, root folders, quality profiles and required defaults. Confirm that a request made **inside Seerr** successfully reaches the appropriate *Arr app before integrating StreamPort.

**4. Connect Seerr to StreamPort.** Sign in to StreamPort as the administrator, open **Settings → Seerr · Requests**, enter the **Seerr base URL** (for example `http://host.docker.internal:5055` when it runs on the Docker host and that address is reachable from the StreamPort container) and the **Seerr API key** from Seerr **Settings → General**, then choose **Save connection** and **Test saved connection**. Do not add `/api/v1` to the base URL. Viewer requests will wait in StreamPort's admin queue; StreamPort forwards only approved requests. Seerr's own API account settings determine further handling.

**5. Connect Radarr and Sonarr directly to StreamPort (optional but recommended).** In StreamPort **Settings**, enter each service URL and its API key (typically **Settings → General → Security** in the *Arr application). Save, then use **Test**, **Sync**, or **Queue**. These direct connections help match files and show download status; **Seerr requests do not require them**. When a media path returned by *Arr differs from StreamPort's container path, configure the corresponding **remote path → local path** mapping in StreamPort's settings. Example: `/movies` → `/media/movies`; use your *actual* paths.

**6. Verify end to end.** Submit a sample request from a StreamPort viewer account, approve it in StreamPort Requests as admin, confirm arrival in Seerr/Radarr/Sonarr, complete an authorized media import, and rescan StreamPort. Check playback only after the file appears in your configured media folder. The service can read imported files but doesn't perform the download/import itself.

### Metadata and subtitles

- **TMDb (recommended):** Create your own [TMDb API key / read-access token](https://www.themoviedb.org/settings/api). Set it in **Settings → Metadata providers**, choose a language and run **Refresh metadata**. Ambiguous matches can be identified manually. TMDb usage is subject to its terms; StreamPort is not endorsed by TMDb.
- **OMDb (optional):** Get a key at [OMDb](https://www.omdbapi.com/apikey.aspx) to supplement rating and plot data.
- **Fanart.tv (optional):** Get your own key at [Fanart.tv](https://fanart.tv/get-an-api-key/) for certain backgrounds and logos.
- **OpenSubtitles.com (optional):** Create an [API application key](https://www.opensubtitles.com/consumers), enter it in StreamPort **Settings → OpenSubtitles** (or `OPENSUBTITLES_API_KEY` in `.env`) and separately sign into your OpenSubtitles account in the UI. **An API key and an account login are separate requirements.** The service stores downloaded text subtitles under `data/subtitles/`; provider quotas apply.

No API keys, provider logins or shared media credentials are bundled with this repo.

### Phone, TV and Roku clients

**Android phone:** open `android/` in Android Studio with **JDK 17**, **Android SDK 35** and Android Gradle Plugin 8.7.3 (defined in the project). Build:

```bash
cd android
./gradlew assembleDebug
```

**Android TV:** the corresponding project is `android-tv/`:

```bash
cd android-tv
./gradlew assembleDebug
```

Both outputs are under `app/build/outputs/apk/debug/`. Install the resulting debug build on your device, enter the **address of your StreamPort server** manually in the connection screen and sign in with your StreamPort account. Use HTTPS for public/remote networks. The apps are WebView-based; Direct Play depends on available device codecs.

**IMPORTANT Android migration notice:** The public source replaces a personal application namespace with `org.streamport.mobile` and `org.streamport.tv`. Builds from this repository have **different Android application IDs** from earlier private APK distributions and **will not update those apps in place**. They may install alongside them, with separate app data. No private signing keys are distributed. The optional `build-sdk.sh` requires *your own* signing keystore and signing environment variables; see [build guidance](docs/DEVELOPMENT.md).

**Roku:** open `roku/`, run `npm ci && npm run build`; inspect the produced package and sideload it through [Roku developer mode](https://developer.roku.com/dev/docs/developer-setup). Enter the StreamPort URL and your account inside the channel. Roku uses its own native codec/player capabilities; Seerr request discovery isn't implemented in the Roku client. The Roku build is **not** a Roku emulator or a guarantee of device behavior.

### Running without Docker

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# ffmpeg and ffprobe must also be installed on the host
export DATA_DIR="$PWD/data"
export MEDIA_DIRS="/absolute/path/to/movies:/absolute/path/to/tv"
export PORT=8097
python server.py
```

The Python process listens on all interfaces; protect it with local firewall policy, a private network or a reverse proxy. Avoid running the process as root. Use **absolute media folder paths**, not URLs. This route is intended for developers and experienced administrators; the Compose recipe provides a more constrained runtime.

### Maintenance, upgrades and backups

```bash
cd server
docker compose ps
docker compose logs --tail=100 streamport
docker compose restart streamport
# After updating the checked-out source:
docker compose up -d --build --wait
# To stop only StreamPort:
docker compose down
```

**Back up before upgrades:** stop StreamPort briefly and make a private copy of **`server/data/` together with `server/.env`**, including both `streamport.db` and `secret.key`. The Fernet key is needed to decrypt saved integration secrets; protect the entire backup and never commit it. For upgrades, retain the same `.env` and `data/` directories, review changes in Compose and rebuild. Do not copy a sample `.env` over production settings. The previous privately tailored `upgrade.sh` is intentionally not included in this public release.

Media deletion is **disabled by default**. A separate `server/enable-deletion.sh` can make the two media mounts writable and explicitly enable the deletion feature; **do not run it unless you intend to allow irreversible deletion**. Only administrators may delete, and confirmation requires their password. Review [SECURITY.md](docs/SECURITY.md) first.

### Development and tests

See [DEVELOPMENT.md](docs/DEVELOPMENT.md) for platform builds and test commands. Basic Python and JavaScript checks:

```bash
cd server
python3 -m unittest discover -s tests -p 'test_*.py'
for test in tests/*.cjs; do node "$test"; done
```

Some UI tests require optional browser/DOM dependencies; the Python suite uses FFmpeg and tests local HTTP behavior. Never run integration tests against a production media/data directory.

### Security and limitations

- **Do not expose port 8097 directly to the public internet.** Prefer a VPN for remote devices, or an authenticated, TLS-terminating reverse proxy with correct forwarding, backend firewall rules and `COOKIE_SECURE=true`. This is a self-hosted Python HTTP service rather than a hardened internet-facing edge gateway.
- The first admin is created on first-run; create a strong password. Don't give StreamPort unnecessarily broad filesystem access. `data/` includes user accounts and potentially sensitive history as well as encrypted service credentials.
- Do not paste API keys into bug reports or store `.env`, databases, encryption keys, keystores, `.apk` files or private packages in the Git repository. Consider rotating keys that were ever shared or published.
- Direct Play is codec-dependent. Software conversion can be resource-intensive; **hardware transcoding, adaptive HLS/DASH, comprehensive embedded/image subtitle support and offline downloads are not implemented**. OpenSubtitles text subtitles use provider quotas. Per-library ACLs and parental controls are not implemented.
- Integration URL settings are supplied by the administrator; only connect to services you control on a trusted network. Make backups before enabling deletion.
- Third-party trademarks, services and APIs remain the property of their owners. This software does not provide media or authorization to obtain it.

More detailed threat-model and deployment guidance: [docs/SECURITY.md](docs/SECURITY.md).

### License and contributing

The original StreamPort code in this repository is provided under the **[MIT License](LICENSE)** (copyright 2026 StreamPort contributors). Dependencies and bundled tooling (including the Gradle wrapper and third-party APIs) have their own terms and licenses. Contributions, security fixes, reproducible bug reports and documentation improvements are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md). Do not commit live configuration, personal device addresses, signing keys or media files.
