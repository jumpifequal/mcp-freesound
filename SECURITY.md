# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/jumpnotequal/mcp-freesound/security/advisories/new)
instead of opening a public issue. You will get an answer as soon as possible.

## Hardening notes

- Keep the **bearer token** secret and long (`mcp-freesound token` generates 256-bit tokens).
- The HTTP transport binds to `127.0.0.1` by default. If you expose it on a network, enable TLS
  (`--tls-cert` / `--tls-key`) or put it behind a TLS reverse proxy.
- Browser requests are accepted only from localhost origins unless you list others in `allowed_origins`.
- The Freesound API key and the token are stored in the per-user config file; on Linux/macOS it is
  created with `0600` permissions. Environment variables are an alternative that avoids the file.
- `download_preview` writes only into the configured download folder, only from Freesound hosts,
  and can be disabled with `allow_downloads: false`.
