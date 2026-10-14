# StreamPort service integration guide

This guide explains which product controls each part of the media workflow. Service dashboards/labels can vary by version. All hostnames and paths below are **illustrative**; use addresses reachable **from the application making the request**, not necessarily from your browser.

## Responsibility matrix

| Service | Role | Direct StreamPort integration? |
| --- | --- | --- |
| **Seerr** (formerly related Overseerr/Jellyseerr ecosystems) | Discovery, approval/request routing to Radarr/Sonarr | **Yes** — search, status, request forwarding via Seerr API |
| **Radarr** | Movie monitoring, download orchestration, file import | **Yes** — status, file metadata, queue |
| **Sonarr** | Series monitoring, download orchestration, file import | **Yes** — status, file metadata, queue |
| **qBittorrent** | Transfers approved/legal media from sources you configure | **No** — configure it as a download client in Radarr/Sonarr |
| **Prowlarr / indexers** | Indexer management for *Arr | **No** — configure inside your *Arr stack |
| **TMDb / OMDb / Fanart.tv** | Metadata providers | **Yes**, optional except TMDb for automatic title matching |
| **OpenSubtitles.com** | Text-subtitle search and download | **Yes**, requires your API application key and account |

### 1. Get the container network right

The default `server/compose.yaml` exposes StreamPort on port 8097 and includes `host.docker.internal:host-gateway` for a service running on the Docker host (Linux with compatible Docker Engine). A service's `localhost` address **inside the StreamPort container is the StreamPort container**, not the host or another container.

- If Seerr/Radarr/Sonarr runs on the **host**, use e.g. `http://host.docker.internal:5055`, `http://host.docker.internal:7878`, `http://host.docker.internal:8989`, provided each service binds to a host-reachable interface and firewall permits it.
- If services are in the **same user-defined Docker network**, use their Compose service name and internal port, such as `http://seerr:5055`; attach StreamPort to that network first. The default Compose file does **not** attach to external networks automatically.
- If they run on **another machine**, use its reachable private DNS name or VPN hostname and port.
- Test reachability from the StreamPort container when diagnosing failures. Changes to network settings may require recreating the container.

You should not expose Seerr, *Arr or qBittorrent management ports to the public internet merely to connect local containers.

### 2. Media folder and download path consistency

Typical host folders (examples only):

```text
/srv/media/
  movies/        # Imported movies (StreamPort reads this)
  tv/            # Imported episodes (StreamPort reads this)
  downloads/     # Work-in-progress downloads (StreamPort does not need this)
```

The StreamPort Compose file maps the host `MOVIES_PATH` and `TV_PATH` to `/media/movies` and `/media/tv` **read-only**. Radarr/Sonarr must import completed files into those **actual host folders**. qBittorrent itself usually writes into a separate downloads directory. For atomic moves/hardlinks, *Arr and qBittorrent need a consistent filesystem view; the [Servarr Docker guide](https://wiki.servarr.com/docker-guide) explains why inconsistent mounts cause problems.

If Radarr reports its imported file as `/movies/Film/movie.mkv` while StreamPort sees it as `/media/movies/Film/movie.mkv`, configure in **StreamPort → Settings → Radarr → Media path mapping**:

```text
Path in Radarr:          /movies
Path inside StreamPort: /media/movies
```

For Sonarr, similarly `/tv` → `/media/tv`. These are **StreamPort mappings for imported library files**, not Radarr/Sonarr's *Remote Path Mapping* for the download client; those solve different problems. The safest approach is to keep the same container paths across apps when you can.

### 3. qBittorrent → Radarr/Sonarr

1. Install and configure qBittorrent Web UI on your trusted network. Set your own **strong username and password**. Do not reuse the example credentials from tutorials; do not disable authentication for public interfaces.
2. In **Radarr → Settings → Download Clients → + → qBittorrent**, enter the qBittorrent hostname, Web UI port (often 8080 but configurable), authentication and a unique category (e.g. `radarr`). Test and save.
3. Repeat in **Sonarr**, preferably with a separate category (e.g. `sonarr`). Configure completed download handling according to your intended import/seeding workflow.
4. Check that the *Arr container can read the completed download location and that its root folders point to the imported media library. Download paths are **not** StreamPort media paths until the import completes.
5. Provide your own authorized indexers/sources in *Arr or a separate indexer manager. StreamPort neither supplies nor manages them.

For official configuration notes see [Radarr settings](https://wiki.servarr.com/radarr/settings) and [Sonarr settings](https://wiki.servarr.com/sonarr/settings). The qBittorrent Web UI hostname/credentials **do not belong in StreamPort settings**.

### 4. Seerr → Radarr/Sonarr

In **Seerr → Settings → Services**, configure movie/TV service connections using the corresponding *Arr API key (usually **Settings → General → Security**) and choose the default root folder and quality profile. Some installs also need a URL base. Verify an approved test request moves to Radarr/Sonarr before configuring StreamPort.

In **StreamPort → Settings → Seerr · Requests**:

```text
Seerr server URL: http://host.docker.internal:5055
Seerr API key:    [paste your own key in the web form]
```

Find the Seerr key in **Seerr → Settings → General**. Supply its **base URL** without `/api/v1`; StreamPort adds `/api/v1` internally. Save and click **Test saved connection**. Keep the key out of URL query parameters and source files. **Requests on viewer accounts remain pending locally until an admin approves them.** Admin requests are forwarded immediately; Seerr's account configuration still determines its handling.

Seerr requests do **not** cause immediate playback: Seerr must forward, *Arr must monitor/import, and StreamPort must subsequently scan/import metadata. Seerr's status and StreamPort's local availability are distinct. Roku does not expose Seerr discovery in this source snapshot.

Official Seerr documentation: [General/API key](https://docs.seerr.dev/using-seerr/settings/general/) and [Services](https://docs.seerr.dev/using-seerr/settings/services/).

### 5. Optional direct *Arr connections from StreamPort

For **Radarr** and **Sonarr** separately, enter the URL and the application's own API key in **StreamPort → Settings**. Use **Test** for connectivity, **Sync** for matching imported paths/metadata and **Queue** for queue status. The server calls `api/v3` on those applications. StreamPort does not save *Arr's database or modify *Arr quality profiles. Missing library files often indicate mount/path mapping mismatches rather than bad API keys.

### 6. Metadata/subtitles

- **TMDb:** Your own API read-access token or v3 API key (Settings → Metadata providers); required for automated library title matching. Refresh metadata manually from the dashboard. Matches may need review.
- **OMDb/Fanart.tv:** Optional keys for additional ratings/posters/logos.
- **OpenSubtitles.com:** Your own application key + your own user login, configured separately in the StreamPort Settings page. The application key may be passed by `OPENSUBTITLES_API_KEY` (server `.env`) if you prefer. Search/download quotas and availability are controlled by the provider. Only downloads you initiate are stored locally in `server/data/subtitles/`.

### 7. End-to-end verification

- Health check: `curl http://127.0.0.1:8097/api/health` on the server.
- Radarr/Sonarr connectivity: Settings → Test; check service bind addresses and keys when failing.
- Seerr connectivity: Settings → Seerr → Test; use a URL reachable from the StreamPort container.
- qBittorrent: Test its connection **inside Radarr/Sonarr**. Check web UI credentials, category and completed download handling.
- Playback: verify the imported file appears under the configured host folder; trigger a StreamPort library scan; test Direct Play before Compatible playback.
- Permission denied: check `PUID`/`PGID`, host mount permissions, and the `data/` ownership. Avoid fixing permissions by giving everyone write access.
- API keys: if a credential is accidentally published, **rotate it with the upstream service** and remove it from Git history, not just the latest commit.
