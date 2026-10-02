# Dashboard: a page per command group

**Status:** in progress. Video (2026-09-30), PDF, Images, Files and Audio (2026-10-01) pages built; the Tools page is gone.
**Decided by:** the maintainer, 2026-09-30 ("lets build on top of this plan").

## Goal

You start from a file ("I have a PDF"), not from a command name. Each big command group gets a page that shows what the picked file holds and offers that group's actions. Small tools move to an Extras page, and every action is also a search away in `Ctrl+P`.

## Pages

| Group | Actions | Page |
|-------|---------|------|
| video | 15 on the dashboard (record, stream and preview stay CLI-only) | **Video** (done) |
| pdf | 13 | **PDF** (done) |
| files | 10 | **Files** (done) |
| audio | 7 | **Audio** (done) |
| images | 4 | **Images** (done) |
| ai | 7 (not ported) | AI, today's Chat, later the agent |
| tools | 3 (share, paste, copy; `qr` is a hidden alias) | **Extras** (done) |

Target sidebar: DO 1 Home, 2 Download, 3 Video, 4 Audio, 5 Images, 6 PDF, 7 Files, 8 AI, 9 Extras; TRACK 0 Activity (Queue and History as two tabs); SETUP Settings (`,`). With 11 pages the sidebar needs 2-row items or scrolling in a 30-row terminal.

## Design

- One widget, `widgets/tool_page.py`, set up by a `ToolPageSpec` per page in `interface/tui/tool_pages.py`: group, header, action sections, and a `describe(path) -> Content` that runs in a thread.
- Layout: FILE card (path, Browse, facts), then ACTIONS (buttons in sections) beside the chosen action's `ActionForm` with the file filled in.
- Each group's core module gets a `describe` operation that reads a file without side effects (`video.describe` uses ffprobe and never downloads FFmpeg).
- A file picked on the wrong page gets a button that opens it on its kind's page (`ToolPageSpec.kinds`, `messages.OpenFile`).

## Steps

- [x] Settings page (PR #37).
- [x] Shared `ToolPage` and the Video page.
- [x] PDF page (`pdf.describe`: pages, paper size, title and author, form fields, locked, scanned). The Files page's Compress on a PDF opens it.
- [x] Images page (`images.describe`: pixels, format, colour mode, frames, EXIF date and camera, a GPS warning; a folder shows its image count, size and formats). Settings moved to `,`: eleven pages outgrew the number keys. The sidebar's arrow keys became priority bindings, because the overflowing page list scrolled instead.
- [x] Files page on the same layout (`files.describe`: a folder's own files by kind, size, subfolders, the biggest file). The old file browser is gone: Browse (PR #42) replaced it, and any page offers "Open on the <kind> page" for a file another page is made for.
- [x] Audio: ported the `audio` group to the catalog; its page shows a song's tags on the facts line, and `set` opens with them filled in (`ToolPageSpec.prefill`). The Tools page went with it: every catalog action now has its group's page, and 12 pages didn't fit the keys.
- [x] `Ctrl+P` finds every action and opens its page (2026-10-02): `interface/tui/commands.py` lists every page and catalog action; Enter shows the action's form with its first field focused.
- [x] Activity: Queue, History and Undo as three tabs of one page (2026-10-02). History rebuilt (paged, kind filter, Failed only, search, detail line); Undo lists the recorded file changes with their folders and steps back one at a time. Key 0 is free now.
- [x] Extras on key 0 after the `tools` port (2026-10-02): QR code on the page, clipboard image saved under a dated name in Pictures with "Open on the Images page", copy a text file. Extras and Settings share the MORE group, so every page fits a 44-row window.
- [x] The sidebar starts open with names and remembers whether you folded it (`sidebar_open`), the maintainer's choice (2026-10-02).
- [ ] AI page with the agent (roadmap step 4). (The Tools page went with the Audio page.)
- [ ] Results: a list of finished runs on each page, with Open.

## Decisions

- Pages come from specs, not classes: a new group costs a spec and a `describe`.
- The form's own file field stays visible; the FILE card fills it. You can still type another path there.
- Page numbers in user text come from `SECTION_KEYS`; adding a page moves the keys.
