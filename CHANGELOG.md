# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-10-26

### Added
- Pure-Python reimplementation of [freesound-mcp-server](https://github.com/johnkimdw/freesound-mcp-server) with **zero runtime dependencies** (standard library only).
- `search_sounds` tool, compatible with the original, now with optional `filter`, `sort` and `page`.
- New tools: `get_sound`, `find_similar_sounds`, `get_sound_analysis`, `get_sound_comments`, `get_user`, `get_user_sounds`, `get_user_packs`, `get_pack`, `get_pack_sounds`, `get_attribution`, `download_preview`, `get_api_usage`.
- stdio transport and Streamable HTTP transport protected by a bearer token, with optional TLS, Origin checks and sessions.
- Tkinter configuration GUI: API key test, token generator, client snippets, one-click Claude Desktop setup, built-in HTTP server runner.
- On Windows, configuration variables missing from the process environment (e.g. `FREESOUND_API_KEY` when a client starts the server with a reduced environment) are read from the user/system environment stored in the registry.
- `mcp-freesound` CLI with `serve`, `gui`, `token`, `config` and `check` commands, plus a `mcp-freesound.py` launcher that runs without installation.

### Changed
- Uses the unified Freesound `/apiv2/search/` endpoint (the old text search endpoint is deprecated).
- The API key is sent in the `Authorization` header instead of the URL query string.
- Tool failures are reported as MCP tool errors (`isError: true`) instead of `{"error": ...}` payloads.

[1.0.0]: https://github.com/jumpnotequal/mcp-freesound/releases/tag/v1.0.0
