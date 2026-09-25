"""Catalog entries for `max grab`.

Only `download` is here so far (grab-page-redesign.md, G1). The CLI command
calls it after phase G5; until then the drift test skips this group's CLI.
"""

from max_cli.core.catalog.spec import Action, Group, Param, ParamKind, Setting

OPS = "max_cli.core.operations.grab"
QUALITY_CHOICES = ("ss", "s", "m", "h", "x")
PLAYER_CLIENTS = ("auto", "default", "web", "tv", "ios", "android")

GROUP = Group(
    name="grab",
    summary="Download video or audio from YouTube and other sites.",
    actions=(
        Action(
            group="grab",
            name="download",
            summary="Download a video, its audio, or a playlist.",
            operation=f"{OPS}:download",
            params=(
                Param("url", ParamKind.URL, "Link to a video or playlist."),
                Param(
                    "output",
                    ParamKind.FOLDER,
                    "Folder to save into.",
                    default=Setting("GRAB_DEFAULT_PATH"),
                    cli=("--output", "-o"),
                ),
                Param(
                    "media_type",
                    ParamKind.CHOICE,
                    "Video, or audio only.",
                    default=Setting("GRAB_DEFAULT_TYPE"),
                    choices=("video", "audio"),
                ),
                Param(
                    "quality",
                    ParamKind.CHOICE,
                    "ss 360p, s 480p, m 720p, h 1080p, x best (4K).",
                    default=Setting("GRAB_QUALITY"),
                    choices=QUALITY_CHOICES,
                    cli=("--quality", "-q"),
                ),
                Param(
                    "resolution",
                    ParamKind.INT,
                    "Exact height in pixels, e.g. 1440. Overrides quality.",
                    default=None,
                    cli=("--resolution", "-r"),
                    advanced=True,
                ),
                Param(
                    "playlist_items",
                    ParamKind.TEXT,
                    "Playlist items to get, e.g. 1-5,8. Empty means all.",
                    default=None,
                    cli=("--index", "-i"),
                    advanced=True,
                ),
                Param(
                    "no_playlist",
                    ParamKind.BOOL,
                    "Only the video, even if the link is part of a playlist.",
                    default=False,
                    cli=("--no-playlist",),
                    advanced=True,
                ),
                Param(
                    "subtitles",
                    ParamKind.BOOL,
                    "Download subtitles too.",
                    default=False,
                    cli=("--subtitles", "-s"),
                    advanced=True,
                ),
                Param(
                    "include_metadata",
                    ParamKind.BOOL,
                    "Embed title, artist and thumbnail.",
                    default=Setting("GRAB_INCLUDE_METADATA"),
                    advanced=True,
                ),
                Param(
                    "strip_playlist",
                    ParamKind.BOOL,
                    "Drop the playlist part of a single video's link.",
                    default=Setting("GRAB_STRIP_PLAYLIST"),
                    advanced=True,
                ),
                Param(
                    "player_client",
                    ParamKind.CHOICE,
                    "YouTube player to imitate. Try another one on HTTP 403 errors.",
                    default="auto",
                    choices=PLAYER_CLIENTS,
                    cli=("--player-client",),
                    advanced=True,
                ),
            ),
            queueable=True,
        ),
    ),
)
