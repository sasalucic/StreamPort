# Security and privacy guidance

StreamPort is designed first for **a trusted home network or private VPN**. It is not hardened as a public internet edge server. Keep the latest software dependencies installed, use strong unique passwords and restrict management service ports.

## Never publish

- `server/.env`, `server/data/`, SQLite databases and their WAL/SHM files.
- `server/data/secret.key`: this encrypts/decrypts stored integration credentials. Keep it together with encrypted database state **only in private encrypted backups**.
- Seerr/Radarr/Sonarr/TMDb/OMDb/Fanart/OpenSubtitles API keys; passwords, session cookies, tokens, encryption keys, private hostnames/addresses, personal media metadata and application logs.
- Android `.jks`/`.keystore` signing keys, `signing/` directories, keystore password files, exported release APKs or older private release bundles.

The `.gitignore` excludes common generated/secrets paths, but **ignoring a file does not remove a secret previously committed to Git history**. Review staged files before pushing and use secret scanning. Rotate any previously exposed service credentials.

## Deployment

- Keep `/media/movies` and `/media/tv` **read-only** (the default). Never run `enable-deletion.sh` just to make playback or scans work.
- Run Docker as a non-root UID/GID with the least access needed and control who can use the Docker socket. Docker Compose drops capabilities, enables `no-new-privileges` and uses a read-only root filesystem where practical; evaluate these settings for your host.
- Serve only on your trusted LAN or private VPN. For public DNS endpoints, terminate TLS at a trusted reverse proxy, set `COOKIE_SECURE=true`, bind the backend to loopback/firewall it, and do not expose qBittorrent, Radarr, Sonarr or Seerr admin dashboards publicly.
- `COOKIE_SECURE=true` is appropriate when the user-facing app runs under HTTPS. The application is not a multi-tenant service; viewer accounts can access the configured media library. There are **no per-library access policies or parental controls**.
- In administrative Settings, only point integration URLs to upstream services you trust. Test requests access those URLs from the server environment.
- No default admin credentials are shipped; the first user provisions an admin account at first launch. User passwords are salted and hashed, and sessions are cookie-based. Provider secrets are encrypted at rest using a generated local Fernet key; compromise of the server/data directory can expose both ciphertext and its key.

## Upgrades / backup

Stop the container briefly for a consistent snapshot. Store both `server/.env` and **all** of `server/data/` offline in a location with strict access control. Do not back them up inside a public Git working tree. Verify that restores preserve permissions/UID and the encryption key. Before enabling media deletion, separately back up irreplaceable media and understand that deletion is destructive.

## Vulnerability reports

Do not post a reproducible exploit together with secrets or exposed URLs in a public GitHub issue. Use a repository security advisory/private report if one is enabled, or contact the repository maintainer privately. No guaranteed response times or security bounty are offered.
