# Dashboard: a page per command group

**Status:** in progress. Video (2026-09-30) and PDF (2026-10-01) pages built.
**Decided by:** the maintainer, 2026-09-30 ("lets build on top of this plan").

## Goal

You start from a file ("I have a PDF"), not from a command name. Each big command group gets a page that shows what the picked file holds and offers that group's actions. Small tools move to an Extras page, and every action is also a search away in `Ctrl+P`.

## Pages

| Group | Actions | Page |
|-------|---------|------|
| video | 15 on the dashboard (record, stream and preview stay CLI-only) | **Video** (done) |
| pdf | 13 | **PDF** (done) |
| files | 10 | Files, rebuilt on the same layout |
| audio | 7 (needs its catalog port) | Audio, with a tag table |
| images | 4 | Images |
| ai | 7 (not ported) | AI, today's Chat, later the agent |
| tools | 4 (share, qr, paste, copy; not ported) | Extras |

Target sidebar: DO 1 Home, 2 Download, 3 Video, 4 Audio, 5 Images, 6 PDF, 7 Files, 8 AI, 9 Extras; TRACK 0 Activity (Queue and History as two tabs); SETUP Settings (`,`). With 11 pages the sidebar needs 2-row items or scrolling in a 30-row terminal.

## Design

- One widget, `widgets/tool_page.py`, set up by a `ToolPageSpec` per page in `interface/tui/tool_pages.py`: group, header, action sections, and a `describe(path) -> Content` that runs in a thread.
- Layout: FILE card (path, Browse, facts), then ACTIONS (buttons in sections) beside the chosen action's `ActionForm` with the file filled in.
- Each group's core module gets a `describe` operation that reads a file without side effects (`video.describe` uses ffprobe and never downloads FFmpeg).
- `FilesPanel.OpenAction` opens the group's page when it has one.

## Steps

- [x] Settings page (PR #37).
- [x] Shared `ToolPage` and the Video page.
- [x] PDF page (`pdf.describe`: pages, paper size, title and author, form fields, locked, scanned). The Files page's Compress on a PDF opens it.
- [ ] Images page (`images.describe`: size in pixels, format, colour mode; a folder shows its image count).
- [ ] Files page on the same layout (a folder instead of a file: counts by type, size).
- [ ] Audio: port the `audio` group to the catalog, then its page with a tag table.
- [ ] `Ctrl+P` finds every action and opens its page.
- [ ] Activity: Queue and History as two tabs of one page.
- [ ] AI page with the agent (roadmap step 4); Extras after the `tools` port. Tools goes when every group has a page.
- [ ] Results: a list of finished runs on each page, with Open.

## Decisions

- Pages come from specs, not classes: a new group costs a spec and a `describe`.
- The form's own file field stays visible; the FILE card fills it. You can still type another path there.
- Page numbers in user text come from `SECTION_KEYS`; adding a page moves the keys.
