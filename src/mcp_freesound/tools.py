"""MCP tool definitions for Freesound.

Each tool is a plain function ``handler(ctx, args) -> dict`` registered together with
its JSON Schema. The protocol layer turns the returned dict into MCP content.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mcp_freesound.config import Config
from mcp_freesound.freesound import FreesoundClient, FreesoundError, safe_filename


class ToolInputError(ValueError):
    """Raised when tool arguments are missing or invalid."""


@dataclass
class ToolContext:
    client: FreesoundClient
    config: Config


@dataclass
class Tool:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[ToolContext, dict[str, Any]], dict[str, Any]]
    annotations: dict[str, Any] = field(default_factory=dict)

    def to_mcp(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {"title": self.title, **self.annotations},
        }


TOOLS: dict[str, Tool] = {}

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}

SEARCH_FIELDS = "id,name,tags,license,duration,previews,url,username,type,description"
LIST_FIELDS = "id,name,tags,license,duration,previews,url,username,type"
DETAIL_FIELDS = (
    "id,url,name,tags,description,category,created,license,type,channels,filesize,bitrate,"
    "bitdepth,duration,samplerate,username,pack,geotag,num_downloads,avg_rating,num_ratings,"
    "num_comments,previews,images,is_explicit"
)
SORT_OPTIONS = [
    "score",
    "duration_desc",
    "duration_asc",
    "created_desc",
    "created_asc",
    "downloads_desc",
    "downloads_asc",
    "rating_desc",
    "rating_asc",
]


def tool(name: str, title: str, description: str, properties: dict, required=(), annotations=None):
    """Decorator registering a tool handler."""

    def decorator(func):
        TOOLS[name] = Tool(
            name=name,
            title=title,
            description=description,
            input_schema={
                "type": "object",
                "properties": properties,
                "required": list(required),
                "additionalProperties": False,
            },
            handler=func,
            annotations=dict(READ_ONLY if annotations is None else annotations),
        )
        return func

    return decorator


# --------------------------------------------------------------------- argument helpers
def _int(args: dict, name: str, default: int | None = None, lo: int | None = None, hi: int | None = None) -> int:
    value = args.get(name, default)
    if value is None:
        raise ToolInputError(f"Missing required argument '{name}'.")
    if isinstance(value, bool):
        raise ToolInputError(f"Argument '{name}' must be an integer.")
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ToolInputError(f"Argument '{name}' must be an integer.") from None
    # Clamp rather than fail, like the original server did for max_results.
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def _str(args: dict, name: str, default: str | None = None, required: bool = False) -> str | None:
    value = args.get(name, default)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ToolInputError(f"Missing required argument '{name}'.")
        return default
    if not isinstance(value, str):
        raise ToolInputError(f"Argument '{name}' must be a string.")
    return value.strip()


def _choice(args: dict, name: str, options: list[str], default: str) -> str:
    value = _str(args, name, default) or default
    if value not in options:
        raise ToolInputError(f"Argument '{name}' must be one of: {', '.join(options)}.")
    return value


SOUND_ID = {"type": "integer", "minimum": 1, "description": "Freesound sound ID."}
MAX_RESULTS = {
    "type": "integer",
    "minimum": 1,
    "maximum": 30,
    "default": 10,
    "description": "Number of results to return (1-30, default 10).",
}
PAGE = {"type": "integer", "minimum": 1, "default": 1, "description": "Result page (1-based)."}


# --------------------------------------------------------------------- formatting
def _truncate(text: str | None, limit: int = 200) -> str:
    text = text or ""
    return text[:limit] + "..." if len(text) > limit else text


def license_info(url: str | None) -> dict[str, Any]:
    """Describe a Creative Commons license URL returned by Freesound."""
    url = url or ""
    lowered = url.lower()
    if "publicdomain/zero" in lowered or lowered.endswith("/cc0"):
        name, attribution, commercial = "Creative Commons 0 (Public Domain)", False, True
    elif "sampling+" in lowered or "sampling%2b" in lowered:
        name, attribution, commercial = "Sampling+", True, True
    elif "/by-nc" in lowered:
        name, attribution, commercial = "Attribution NonCommercial (CC BY-NC)", True, False
    elif "/by/" in lowered or lowered.rstrip("/").endswith("/by"):
        name, attribution, commercial = "Attribution (CC BY)", True, True
    else:
        name, attribution, commercial = "Unknown license (check the sound page)", True, False
    return {
        "name": name,
        "url": url,
        "requires_attribution": attribution,
        "commercial_use_allowed": commercial,
    }


def format_sound(sound: dict, truncate_description: bool = True) -> dict:
    description = sound.get("description", "")
    formatted = {
        "id": sound.get("id"),
        "name": sound.get("name"),
        "duration_seconds": sound.get("duration"),
        "description": _truncate(description) if truncate_description else description,
        "tags": sound.get("tags", []),
        "license": sound.get("license"),
        "file_type": sound.get("type"),
        "uploader": sound.get("username"),
        "freesound_page": sound.get("url"),
        "preview_urls": sound.get("previews", {}),
        "download_info": "Visit the Freesound page to download the full quality file",
    }
    if "description" not in sound:
        formatted.pop("description")
    return formatted


def format_sound_list(data: dict, page: int, max_results: int, label: str) -> dict:
    sounds = [format_sound(s) for s in data.get("results", [])]
    result: dict[str, Any] = {
        "total_found": data.get("count", 0),
        "page": page,
        "results_returned": len(sounds),
        "sounds": sounds,
    }
    if data.get("next"):
        result["note"] = (
            f"Showing {len(sounds)} results (page {page}, {max_results} per page) "
            f"out of {data.get('count', 0)}. Request page {page + 1} for more."
        )
    if not sounds:
        result["message"] = f"No sounds found for {label}."
    return result


# --------------------------------------------------------------------- tools
@tool(
    "search_sounds",
    "Search sounds",
    "Search Freesound for audio files (sound effects, ambiences, music loops...) by text. "
    "Supports Freesound filter syntax (e.g. 'duration:[0 TO 30] license:\"Creative Commons 0\"' "
    "or 'tag:rain type:wav') and sorting. Returns metadata, license and preview URLs.",
    {
        "query": {"type": "string", "description": "Search terms, e.g. 'thunderstorm', 'piano loop'."},
        "max_results": MAX_RESULTS,
        "filter": {
            "type": "string",
            "description": "Optional Freesound/Solr filter, e.g. 'duration:[1 TO 10] tag:dog'.",
        },
        "sort": {"type": "string", "enum": SORT_OPTIONS, "default": "score", "description": "Result ordering."},
        "page": PAGE,
    },
    required=["query"],
)
def search_sounds(ctx: ToolContext, args: dict) -> dict:
    query = _str(args, "query", required=True)
    max_results = _int(args, "max_results", 10, 1, 30)
    page = _int(args, "page", 1, 1)
    data = ctx.client.search(
        query=query,
        filter=_str(args, "filter"),
        sort=_choice(args, "sort", SORT_OPTIONS, "score"),
        page=page,
        page_size=max_results,
        fields=SEARCH_FIELDS,
    )
    result = {"query": query, **format_sound_list(data, page, max_results, f"'{query}'")}
    if not result["sounds"]:
        result["message"] = f"No sounds found for '{query}'. Try different search terms or check spelling."
    return result


@tool(
    "get_sound",
    "Get sound details",
    "Get full details of a single Freesound sound: technical properties (sample rate, bit depth, "
    "channels, size), license, pack, geotag, ratings, downloads, previews and waveform images.",
    {"sound_id": SOUND_ID},
    required=["sound_id"],
)
def get_sound(ctx: ToolContext, args: dict) -> dict:
    sound = ctx.client.sound(_int(args, "sound_id", lo=1), fields=DETAIL_FIELDS)
    sound["license_details"] = license_info(sound.get("license"))
    return sound


@tool(
    "find_similar_sounds",
    "Find similar sounds",
    "Find sounds that are acoustically similar to a given Freesound sound.",
    {
        "sound_id": SOUND_ID,
        "max_results": MAX_RESULTS,
        "page": PAGE,
        "similarity_space": {
            "type": "string",
            "enum": ["laion_clap", "freesound_classic"],
            "description": "Optional similarity space (default chosen by Freesound).",
        },
    },
    required=["sound_id"],
)
def find_similar_sounds(ctx: ToolContext, args: dict) -> dict:
    sound_id = _int(args, "sound_id", lo=1)
    max_results = _int(args, "max_results", 10, 1, 30)
    page = _int(args, "page", 1, 1)
    space = args.get("similarity_space")
    if space is not None:
        space = _choice(args, "similarity_space", ["laion_clap", "freesound_classic"], "laion_clap")
    data = ctx.client.similar(sound_id, page=page, page_size=max_results, fields=LIST_FIELDS, similarity_space=space)
    return {"sound_id": sound_id, **format_sound_list(data, page, max_results, f"sound {sound_id}")}


@tool(
    "get_sound_analysis",
    "Get sound analysis",
    "Get audio descriptors computed by Freesound for a sound (e.g. bpm, key, loudness, "
    "brightness, pitch). Optionally restrict to specific descriptor names.",
    {
        "sound_id": SOUND_ID,
        "descriptors": {
            "type": "string",
            "description": "Optional comma-separated descriptor names, e.g. 'bpm,tonality,loudness'.",
        },
    },
    required=["sound_id"],
)
def get_sound_analysis(ctx: ToolContext, args: dict) -> dict:
    sound_id = _int(args, "sound_id", lo=1)
    analysis = ctx.client.analysis(sound_id, fields=_str(args, "descriptors"))
    return {"sound_id": sound_id, "analysis": analysis}


@tool(
    "get_sound_comments",
    "Get sound comments",
    "Get user comments posted on a Freesound sound (newest first).",
    {"sound_id": SOUND_ID, "max_results": MAX_RESULTS, "page": PAGE},
    required=["sound_id"],
)
def get_sound_comments(ctx: ToolContext, args: dict) -> dict:
    sound_id = _int(args, "sound_id", lo=1)
    page = _int(args, "page", 1, 1)
    data = ctx.client.comments(sound_id, page=page, page_size=_int(args, "max_results", 10, 1, 30))
    comments = [
        {"username": c.get("username"), "comment": c.get("comment"), "created": c.get("created")}
        for c in data.get("results", [])
    ]
    return {"sound_id": sound_id, "total": data.get("count", 0), "page": page, "comments": comments}


@tool(
    "get_user",
    "Get user profile",
    "Get the public profile of a Freesound user (number of sounds, packs, about text, home page).",
    {"username": {"type": "string", "description": "Freesound username."}},
    required=["username"],
)
def get_user(ctx: ToolContext, args: dict) -> dict:
    return ctx.client.user(_str(args, "username", required=True))


@tool(
    "get_user_sounds",
    "List user sounds",
    "List the sounds uploaded by a Freesound user.",
    {"username": {"type": "string", "description": "Freesound username."}, "max_results": MAX_RESULTS, "page": PAGE},
    required=["username"],
)
def get_user_sounds(ctx: ToolContext, args: dict) -> dict:
    username = _str(args, "username", required=True)
    max_results = _int(args, "max_results", 10, 1, 30)
    page = _int(args, "page", 1, 1)
    data = ctx.client.user_sounds(username, page=page, page_size=max_results, fields=LIST_FIELDS)
    return {"username": username, **format_sound_list(data, page, max_results, f"user '{username}'")}


@tool(
    "get_user_packs",
    "List user packs",
    "List the packs (collections of sounds) created by a Freesound user.",
    {"username": {"type": "string", "description": "Freesound username."}, "max_results": MAX_RESULTS, "page": PAGE},
    required=["username"],
)
def get_user_packs(ctx: ToolContext, args: dict) -> dict:
    username = _str(args, "username", required=True)
    page = _int(args, "page", 1, 1)
    data = ctx.client.user_packs(username, page=page, page_size=_int(args, "max_results", 10, 1, 30))
    packs = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "num_sounds": p.get("num_sounds"),
            "created": p.get("created"),
            "url": p.get("url"),
        }
        for p in data.get("results", [])
    ]
    return {"username": username, "total": data.get("count", 0), "page": page, "packs": packs}


@tool(
    "get_pack",
    "Get pack details",
    "Get details of a Freesound pack (name, description, author, number of sounds).",
    {"pack_id": {"type": "integer", "minimum": 1, "description": "Freesound pack ID."}},
    required=["pack_id"],
)
def get_pack(ctx: ToolContext, args: dict) -> dict:
    return ctx.client.pack(_int(args, "pack_id", lo=1))


@tool(
    "get_pack_sounds",
    "List pack sounds",
    "List the sounds contained in a Freesound pack.",
    {
        "pack_id": {"type": "integer", "minimum": 1, "description": "Freesound pack ID."},
        "max_results": MAX_RESULTS,
        "page": PAGE,
    },
    required=["pack_id"],
)
def get_pack_sounds(ctx: ToolContext, args: dict) -> dict:
    pack_id = _int(args, "pack_id", lo=1)
    max_results = _int(args, "max_results", 10, 1, 30)
    page = _int(args, "page", 1, 1)
    data = ctx.client.pack_sounds(pack_id, page=page, page_size=max_results, fields=LIST_FIELDS)
    return {"pack_id": pack_id, **format_sound_list(data, page, max_results, f"pack {pack_id}")}


@tool(
    "get_attribution",
    "Build attribution",
    "Build ready-to-paste attribution/credits text for one or more Freesound sounds, with "
    "license details (whether attribution is required and whether commercial use is allowed).",
    {
        "sound_ids": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "minItems": 1,
            "maxItems": 50,
            "description": "List of Freesound sound IDs.",
        }
    },
    required=["sound_ids"],
)
def get_attribution(ctx: ToolContext, args: dict) -> dict:
    ids = args.get("sound_ids")
    if not isinstance(ids, list) or not ids:
        raise ToolInputError("Argument 'sound_ids' must be a non-empty list of integers.")
    if len(ids) > 50:
        raise ToolInputError("At most 50 sound IDs are allowed.")
    entries, errors = [], []
    for raw in ids:
        sound_id = _int({"id": raw}, "id", lo=1)
        try:
            sound = ctx.client.sound(sound_id, fields="id,name,username,license,url")
        except FreesoundError as exc:
            errors.append({"sound_id": sound_id, "error": str(exc)})
            continue
        lic = license_info(sound.get("license"))
        entries.append(
            {
                "sound_id": sound_id,
                "attribution": f'"{sound.get("name")}" by {sound.get("username")} '
                f"({sound.get('url')}) licensed under {lic['name']} ({lic['url']})",
                "license": lic,
            }
        )
    result: dict[str, Any] = {
        "credits": entries,
        "credits_text": "\n".join(c["attribution"] for c in entries),
        "commercial_use_allowed_for_all": all(c["license"]["commercial_use_allowed"] for c in entries),
    }
    if errors:
        result["errors"] = errors
    return result


@tool(
    "download_preview",
    "Download preview",
    "Download the preview audio file (MP3 or OGG) of a Freesound sound to the configured "
    "download folder on the server machine. Full-quality originals require OAuth2 and are "
    "not supported; previews are free to fetch.",
    {
        "sound_id": SOUND_ID,
        "quality": {"type": "string", "enum": ["hq", "lq"], "default": "hq", "description": "Preview quality."},
        "format": {"type": "string", "enum": ["mp3", "ogg"], "default": "mp3", "description": "Audio format."},
    },
    required=["sound_id"],
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
def download_preview(ctx: ToolContext, args: dict) -> dict:
    if not ctx.config.allow_downloads:
        raise ToolInputError("Preview downloads are disabled in the server configuration.")
    sound_id = _int(args, "sound_id", lo=1)
    quality = _choice(args, "quality", ["hq", "lq"], "hq")
    fmt = _choice(args, "format", ["mp3", "ogg"], "mp3")
    sound = ctx.client.sound(sound_id, fields="id,name,username,license,url,previews")
    url = (sound.get("previews") or {}).get(f"preview-{quality}-{fmt}")
    if not url:
        raise FreesoundError(f"Sound {sound_id} has no {quality} {fmt} preview.")
    folder = Path(ctx.config.download_dir).expanduser()
    target = folder / f"{sound_id}_{safe_filename(sound.get('name') or 'sound')}.{fmt}"
    size = ctx.client.download(url, target)
    return {
        "sound_id": sound_id,
        "saved_to": str(target.resolve()),
        "size_bytes": size,
        "license": license_info(sound.get("license")),
        "freesound_page": sound.get("url"),
    }


@tool(
    "get_api_usage",
    "Get API usage",
    "Show how many Freesound API requests the configured key has made recently, useful to monitor rate limits.",
    {"num_days": {"type": "integer", "minimum": 1, "maximum": 60, "default": 7, "description": "Days of history."}},
)
def get_api_usage(ctx: ToolContext, args: dict) -> dict:
    return ctx.client.usage(_int(args, "num_days", 7, 1, 60))
