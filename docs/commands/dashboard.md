# TUI Dashboard

Type `max` on its own to open the interactive terminal dashboard. You can download media, run tools, watch the task queue, browse files, edit settings and chat with the AI from one screen.

## Usage

```bash
max              # opens the dashboard
max dashboard    # the same, by name
```

A bare `max` opens the dashboard only when you run it in a terminal. In a script, a pipe or CI it prints the help text, so nothing waits for key presses.

The dashboard comes with the base install. Older instructions say `pip install max-cli[tui]`; that command still works.

## Sections

The sidebar on the left lists eleven sections in three groups, each with its name. Press the `«` button at the top (or `Ctrl+B`) to fold it to a strip of icons; hover an icon to see its name, and press `»` to open it again. Press a section's key to jump to it (a number, or `,` for Settings), click it, or move with the arrow keys and press `Enter`. The dashboard opens on the section you used last.

| Key | Section | What it does |
|-----|---------|--------------|
| | **Do** | |
| `1` | **Home** | Command center: live CPU, memory and disk, your download and action counts, activity over the last 14 days, a breakdown by type, quick launch and recent activity |
| `2` | **Download** | Download form with progress and recent downloads |
| `3` | **Video** | Pick a video or audio file, see its length, size and codecs, and run any `max video` action on it |
| `4` | **Audio** | Pick a song or a folder of music, see its tags, length and bitrate (or how many tracks lack tags), edit tags, sort music into folders, compress or clean it |
| `5` | **Images** | Pick an image or a folder, see its size in pixels, format, date and camera (or how many images a folder holds), and run any `max images` action on it |
| `6` | **PDF** | Pick a PDF, see its pages, paper size and whether it's locked or scanned, and run any `max pdf` action on it |
| `7` | **Files** | Pick a folder or a file, see what it holds, and sort, clean, back up or undo with any `max files` action |
| `8` | **Chat** | AI chat with command suggestions |
| | **Track** | |
| `9` | **Activity** | Three tabs: Queue (running, waiting and finished tasks), History (every action, with filters) and Undo (put back what Max moved, renamed or deleted) |
| | **More** | |
| `0` | **Extras** | Show a QR code for a link, save a screenshot from the clipboard, copy a text file to the clipboard |
| `,` | **Settings** | Your defaults (AI, downloads, images, safety) and upkeep: FFmpeg status, data size, cache and undo cleanup |

Badges next to a section show what needs a look: a green `2` on Download means two downloads are running. On Activity, a red `!1` means one action failed since you last opened Activity; otherwise a yellow `3` means three tasks are waiting or running.

The dashboard remembers whether you left the sidebar open or folded. In a window narrower than 100 columns it always shows icons only.

The Activity page's Queue tab reads the same task store as `max queue` and `max grab`. See [Queue](queue.md).

## Download page

Paste a link and press `Enter`, or wait a moment: the page checks the link. While it checks, the Check button reads "Checking" and the preview shows a spinner with the seconds so far. Then it shows its title, channel, length, chapters, views, likes, upload date, the best video and audio streams, the subtitle languages and the site. Each quality button shows the size you'll get, and the Audio (MP3) buttons show the size at each bitrate.

- **Options**, under the preview, holds the other `max grab download` options: an exact resolution, the YouTube player client, and checkboxes for subtitles, metadata and playlist handling.
- **Transfers** has two tabs. Downloads shows one row per download with its progress; "Clear finished" removes the done, failed and cancelled rows. History shows 8 past downloads at a time: type in the filter box to search titles and sites, and use "< Prev" and "Next >" to page. Press `Enter` on a row, or "Download again", to put its link back in the box. "Copy link" copies it.
- **Tools** sums up your downloads (count, done, failed, total size, sites) and shows whether the YouTube fix is installed. If YouTube downloads fail with HTTP 403, press "Install fix": it does what `max grab pot-setup` does, after one confirmation. It needs Deno. The other buttons open the download folder, the Activity page's Queue and the settings.

## Video page

The Video page (`3`) works on one file at a time. Paste a path or press Browse: the FILE card shows the file's length, picture size, frame rate, codecs, size and bitrate (it needs FFmpeg; without it you see only the size).

Pick an action from its group: **Shrink & convert** (compress, convert, gif), **Cut & join** (cut, concat, snap), **Sound** (to-audio, audio-convert, louder, mute, normalize, denoise) or **Picture** (brightness, color, stabilize). Its form opens with your file filled in and the same options as the `max video` command. Run it, or add compress and denoise to the queue.

## Audio page

The Audio page (`4`) works on one song or a folder of music. Pick a song: the FILE OR FOLDER card shows its length, bitrate, sample rate, size and whether it has cover art, then its title, artist, album, year, track and genre. Pick a folder: it counts the tracks, adds up their length and size, lists their formats, and warns you how many have no title or artist.

The actions sit in three groups: **Tags** (set, get, batch, clear), **Sort** (organize) and **Sound** (compress, denoise). **set** opens with the song's current tags filled in, so you change only what's wrong; a field you've already typed in keeps your text. **organize** starts with folders by artist and album, and its **Dry run** box shows the moves before anything happens. Moves can be undone from the Files page (**undo**).

## Images page

The Images page (`5`) takes one image or a whole folder. Pick an image: the FILE OR FOLDER card shows its size in pixels and megapixels, format, colour mode (colour, greyscale, transparency), frames for an animated GIF, file size, and the date and camera from its EXIF data. It warns you when the image holds a GPS location, which **strip** removes. Pick a folder: the card shows how many images it holds, their total size and formats, and the folder the results go to (`<folder>_optimized`). Max reads the images in that folder, not in its subfolders.

The actions sit in two groups: **Shrink** (compress, resize) and **Convert & clean** (convert, strip). The picked image or folder fills the action's target.

## PDF page

The PDF page (`6`) works like the Video page. Pick a PDF: the FILE card shows its pages, paper size (A4, Letter or millimetres), size, title and author, and how many form fields it has. It tells you when the PDF is locked with a password, and when it has no text on its first pages, which means it's a scan that **ocr** can read.

The actions sit in five groups: **Shrink** (compress, optimize), **Combine & split** (merge, bundle, split, compare), **Protect & mark** (lock, stamp), **Extract** (rip, ocr) and **Forms** (form-data, form-fill, form-flatten). The picked PDF fills the action's first file field; for merge and bundle, press Browse there to add more.

## Files page

The Files page (`7`) works on a folder or one file. Pick a folder: the FILE OR FOLDER card counts the files directly in it and its subfolders, shows their total size, how many of each kind (images, videos, PDFs ...) and the biggest file. Pick a file: it shows the kind, size and date.

The actions sit in four groups: **Organize** (order, smart-sort, duplicates), **Look** (preview, history), **Backup & undo** (backup, backups, backup-cleanup, undo) and **Destroy** (shred). Picking a file and then a folder action (order, smart-sort, duplicates) fills in the file's folder. Actions that move or delete files ask first, and **undo** reverses the last change Max recorded.

### Open on another page

When you pick a video, an audio file, an image or a PDF on a page that isn't made for it, the card shows a button such as **Open on the PDF page (6)**. It opens that page with the file picked. This works on every page with a FILE card: a PDF picked on the Images page offers the PDF page too.

## Browse

Every Browse button opens the same window. It starts in the folder of the path already in the field, or where you picked from last time.

- **Places** on the left: Home, Desktop, Documents, Downloads, Pictures, Videos and Music (the ones you have), Max's download folder, your pinned folders, folders you picked from lately, and the drives.
- **The path bar:** `<` goes back, `^` goes up a folder. Type or paste a path and press `Enter` to go there; a file path picks that file.
- **The list:** folders first, then files with their size and date. Type in the filter box (`Ctrl+F`) to narrow it. `Enter` opens a folder or picks a file, `Backspace` goes up and puts you back on the folder you left, `Alt+Left` goes back.
- On the Video, Images and PDF pages the list shows only the files that page works on. Tick **All files** to see everything, and **Hidden files** to see hidden ones.
- **Pin this folder** adds the open folder to Places for next time.

Fields that take a folder list folders only and pick the open one. Fields for a file Max writes (an output) ask for a file name and save it in the open folder. Fields that take a file also have **Use this folder**, for actions that work on a whole folder.

## Activity page

The Activity page (`9`) has three tabs. Queue opens first; the Download page's Queue button opens it too.

### Queue

The Queue tab shows the work the dashboard runs, one task at a time. At the top, four counters show what's running and waiting, and how many tasks finished or failed today. The light in the corner says whether the queue is running.

- **Now running** shows the running task with its progress, speed and time left. Cancel stops it.
- **Up next** lists the waiting tasks in the order they'll run. Each one has Pause (or Resume) and Cancel. "Pause all", "Resume all" and "Clear waiting" act on the whole list; "Clear waiting" asks first and leaves the running task alone.
- **Finished** shows the last 8 tasks. Retry puts a failed or cancelled task back in line, "Run again" repeats a finished one, and "Open folder" opens where its files went. "All activity (History)" opens the History tab.

### History

Every action you ran from the dashboard, newest first, 10 at a time with Prev and Next. Pick a kind (Video, Audio, PDF, Downloads ...), tick **Failed only**, or search by name, file or message. The line under the list shows the highlighted action in full: its message or error, its output files and the options it ran with. **Clear history** asks first and leaves your files alone.

### Undo

The file changes Max recorded (organize, order, smart-sort and duplicates --delete), newest first, with the folder each one changed. **Undo** puts back the newest change that isn't undone yet, after one confirmation; press it again to step further back. Folders that a change created, such as organize's Artist/Album folders, go too when they're empty again.

## Extras page

The Extras page (`0`) holds the `max tools` actions, one card each:

- **Share as QR code:** type a link or any text and press Run. The code appears on the page; point your phone's camera at it. Use it to open a local dev server on your phone.
- **Save clipboard image:** saves the image on your clipboard, such as a screenshot. The file name starts as a new dated name in your Pictures folder (`clipboard-20261002-153012.png`), so pastes never replace each other. Tick **Overwrite** to replace a file that has the name you typed. After a save, "Open on the Images page" opens the picture there.
- **Copy text file:** puts a text file's contents on the clipboard.

## Find any action (Ctrl+P)

Press `Ctrl+P` and type part of an action's or a page's name, such as `merge` or `pdf compress`. Each result shows the page it's on and what it does. Press `Enter` to open that page with the action's form shown and the cursor in its first field. With nothing typed, the list shows every page and action. Theme commands are there too.

## Settings page

The Settings page (`,`) edits the same settings as `max config`, saved in `~/.max_config.env`. It shows only settings that change something:

- **AI:** the API key (hidden; press Show to see it), the base URL, the chat and image models, and Ollama.
- **Downloads:** the folder, format, quality, how many downloads run at once, metadata, and playlist links.
- **Images:** the default quality and how many images run at once.
- **Safety and network:** whether Max asks before it moves, overwrites or deletes files, how many more times the queue runs a task that failed, and how long a download waits for data.

"Save changes" checks the values first, writes only the settings you changed and applies them at once; "Downloads at once" applies the next time `max` starts. An empty API key removes it from the file. If a `.env` file in the folder you started `max` from sets the same settings, it wins; Maintenance says so.

**Maintenance** shows the Max, Python and system versions, whether FFmpeg is found, and how much `~/.max_cli` holds. Its buttons clear the cache, remove undo backups and undo records older than 30 days, and reset every setting. Each one asks first. If your settings file still sets something Max no longer has, such as `VERBOSE`, Maintenance names it and **Remove them** deletes those lines. The dashboard points them out when it starts, too.

## Jobs window

Press `J` to open or close the Jobs window above the footer. It shows the task running now, with its progress, speed and time left, then the tasks waiting their turn, then the last few that finished, failed or were cancelled. It opens by itself when you press "Queue for later" on the Download page or "Add to queue" on an action's form.

While the dashboard is open it runs queued tasks one after another, including any left from earlier runs. To cancel or retry a task, open Activity (`9`).

## Theme

The dashboard uses its own dark theme, `max-cyber`. Press `Ctrl+P` and search "theme" to try another one; the dashboard remembers your choice.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1` to `9`, `0` | Jump to a section |
| `,` | Settings |
| `Alt+Left` | Back to the previous section |
| `Esc` | Move to the sidebar |
| `?` | Show every shortcut |
| `J` | Show or hide the Jobs window |
| `Ctrl+P` | Find any action or page by name; themes |
| `q` | Quit |
| `r` | Refresh the sections |
| `Ctrl+B` | Collapse or expand the sidebar |
| `Tab` / `Shift+Tab` | Move between buttons and fields |
| `Enter` | Press the focused button |

Number keys and `q` type into a text field when one has focus. Press `Esc` first to leave the field.

## Troubleshooting

### "The dashboard needs the 'textual' library, which is missing"

Your install is broken or partly removed. Reinstall Max:

```bash
pip install --upgrade max-cli
```

### `max` prints help instead of opening the dashboard

`max` opens the dashboard only when both its input and its output are a terminal. Run it directly, without `|` or `>`, or run `max dashboard`.

### Dashboard not refreshing

Press `r` to refresh. The visible section also refreshes every 2 seconds.
