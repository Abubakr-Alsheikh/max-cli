"""The dashboard's colour theme (PLANS/active/dashboard-design-system.md, R2).

One registered Textual theme instead of `$variable` overrides in the app
CSS. Overrides there only reached the app's own CSS; every widget's
DEFAULT_CSS and every `Content` style still saw Textual's default theme,
so the same `$accent` was violet in one place and orange in another.

The look: deep navy panels, neon cyan for what matters now, magenta for
highlights, violet for focus and selection.
"""

from textual.theme import Theme

THEME_NAME = "max-cyber"

MAX_CYBER = Theme(
    name=THEME_NAME,
    primary="#22d3ee",  # neon cyan: live values, primary actions
    secondary="#e879f9",  # magenta: peaks, today, highlights
    accent="#a78bfa",  # violet: focus, the active page
    warning="#fbbf24",
    error="#fb7185",
    success="#34d399",
    foreground="#e2e8f0",
    background="#050914",
    surface="#0f1a2e",  # cards
    panel="#0a1222",  # page background
    boost="#16233d",  # hover and selected rows
    dark=True,
    variables={
        "border": "#1e3354",
        "border-blurred": "#16233d",
        "text-muted": "#7c8db0",
        "footer-key-foreground": "#22d3ee",
        "block-cursor-background": "#a78bfa",
        "block-cursor-foreground": "#050914",
        "input-selection-background": "#a78bfa 35%",
        "scrollbar": "#1e3354",
        "scrollbar-hover": "#a78bfa",
        "scrollbar-active": "#22d3ee",
        "scrollbar-background": "#0a1222",
        "scrollbar-background-hover": "#0a1222",
        "scrollbar-corner-color": "#0a1222",
    },
)
