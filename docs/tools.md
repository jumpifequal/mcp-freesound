# Tool reference

All tools are read-only on Freesound (they never modify your account) and return JSON.
`max_results` is always clamped to 1-30 and `page` starts at 1. When a call fails (bad ID,
network error, rate limit...) the tool returns an MCP tool error (`isError: true`) with a
readable message, so the model can recover.

| Tool | Purpose | Required args | Optional args |
|---|---|---|---|
| `search_sounds` | Text search with filters and sorting | `query` | `max_results`, `filter`, `sort`, `page` |
| `get_sound` | Full details of one sound | `sound_id` | - |
| `find_similar_sounds` | Acoustically similar sounds | `sound_id` | `max_results`, `page`, `similarity_space` |
| `get_sound_analysis` | Audio descriptors (bpm, key, loudness...) | `sound_id` | `descriptors` |
| `get_sound_comments` | Comments on a sound | `sound_id` | `max_results`, `page` |
| `get_user` | Public user profile | `username` | - |
| `get_user_sounds` | Sounds uploaded by a user | `username` | `max_results`, `page` |
| `get_user_packs` | Packs created by a user | `username` | `max_results`, `page` |
| `get_pack` | Pack details | `pack_id` | - |
| `get_pack_sounds` | Sounds in a pack | `pack_id` | `max_results`, `page` |
| `get_attribution` | Ready-to-paste credits + license analysis | `sound_ids` (1-50) | - |
| `download_preview` | Save the MP3/OGG preview locally | `sound_id` | `quality` (`hq`/`lq`), `format` (`mp3`/`ogg`) |
| `get_api_usage` | Requests made with your API key | - | `num_days` (1-60) |

## search_sounds

Compatible with the original server (`query`, `max_results`) and returns the same shape:

```json
{
  "query": "rain",
  "total_found": 5321,
  "page": 1,
  "results_returned": 10,
  "sounds": [
    {
      "id": 123,
      "name": "Rain on window.wav",
      "duration_seconds": 12.4,
      "description": "first 200 characters...",
      "tags": ["rain", "window"],
      "license": "http://creativecommons.org/publicdomain/zero/1.0/",
      "file_type": "wav",
      "uploader": "someone",
      "freesound_page": "https://freesound.org/people/someone/sounds/123/",
      "preview_urls": {"preview-hq-mp3": "https://cdn.freesound.org/...", "...": "..."},
      "download_info": "Visit the Freesound page to download the full quality file"
    }
  ],
  "note": "Showing 10 results (page 1, 10 per page) out of 5321. Request page 2 for more."
}
```

### filter syntax

`filter` uses Freesound's Solr syntax. Useful examples:

| Goal | Filter |
|---|---|
| Short sounds | `duration:[0 TO 5]` |
| Only CC0 | `license:"Creative Commons 0"` |
| Only WAV | `type:wav` |
| Tag match | `tag:footsteps` |
| Stereo, 48 kHz | `channels:2 samplerate:48000` |
| Combine | `tag:rain duration:[5 TO 60] license:"Creative Commons 0"` |

### sort values

`score` (default), `duration_desc`, `duration_asc`, `created_desc`, `created_asc`,
`downloads_desc`, `downloads_asc`, `rating_desc`, `rating_asc`.

## get_attribution

Returns one credit line per sound, e.g.

```text
"Rain on window.wav" by someone (https://freesound.org/people/someone/sounds/123/) licensed under Attribution (CC BY) (http://creativecommons.org/licenses/by/4.0/)
```

and, for every sound, `requires_attribution` and `commercial_use_allowed`, plus
`commercial_use_allowed_for_all`. The license interpretation is a convenience: always check
the license page before publishing.

## download_preview

Writes `<download_dir>/<sound_id>_<name>.<mp3|ogg>` on the machine running the server and
returns the absolute path. Only Freesound hosts are contacted. Previews are lossy (about
128 kbps for `hq`); the original file needs OAuth2 and is out of scope. Disable this tool with
`allow_downloads: false` (it is the only tool that writes to disk).
