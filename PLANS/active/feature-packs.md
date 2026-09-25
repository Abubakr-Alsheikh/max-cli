# Plan: Choose Your Features (Feature Packs)

**Status:** Draft (idea captured; plan it later)
**Priority:** P2
**Updated:** 2026-09-26

## Goal

Each user turns on only the features they want, like image tools or media downloads, so Max doesn't show noise they don't need. The same choice controls which dashboard pages appear.

## The idea (maintainer, 2026-09-26)

- Let users control which features they have. If they want image tools, they add them. If they want media downloads, they add that. By default, a feature isn't there, so it doesn't add noise.
- In the dashboard, users can hide and show pages the same way.

## What we know today

- Command groups already load lazily (hardening D5). `core/cli/registry.py` has one entry per group, so turning a group on or off is a small change.
- `plugin_commands_migration.md` plans to move heavy groups (`ai`, `video`, `grab`, `pdf`) into optional installs, so users don't download yt-dlp or PyMuPDF unless they need them. The maintainer put plugins on hold on 2026-09-25, and three plugin bugs stay deferred.
- The dashboard sidebar comes from a fixed `SECTIONS` list in `widgets/sidebar.py`.

## Ideas to plan later

- [ ] **Two levels to decide between:**
  - (a) Visibility only: every feature is installed, and users hide what they don't use. Small and safe.
  - (b) Install on demand: a feature's heavy dependencies install when you turn it on (the plugin plan). Smaller installs, more moving parts.
- [ ] A `features` setting (for example in `~/.max_cli/features.json`) read by the registry and the dashboard sidebar.
- [ ] A `max features` command and a dashboard settings page to turn features on and off. It shows what each one needs, such as FFmpeg or an API key.
- [ ] Decide the default for new users: a small core set (files, images?) or everything on.
- [ ] Hidden features stay reachable: `max <group> ...` could say "feature X is off; turn it on with `max features enable X`".

## Related

- `plugin_commands_migration.md` (install-on-demand path), `dashboard-ui-redesign.md` (settings page), `dashboard-first-ai-agent.md` (the agent should only offer enabled features).
