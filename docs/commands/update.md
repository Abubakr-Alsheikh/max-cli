# Update and Doctor

Two commands that look after Max itself: `max update` installs the newest version, and `max doctor` checks that everything Max needs is in place.

## update

```bash
max update            # check PyPI, then ask before updating
max update --check    # only say whether a newer Max is out
max update --yes      # update without asking
```

Max updates itself the same way you installed it:

| You installed with | `max update` runs |
|--------------------|-------------------|
| uv (`uv tool install`, or the one-line installer) | `uv tool install --upgrade max-cli`, keeping extras such as `[ocr]` and packages you added with `--with` |
| pipx | `pipx upgrade max-cli` |
| pip | `python -m pip install --upgrade max-cli` with Max's own Python |
| a source folder (`pip install -e .`) | nothing: it tells you to `git pull` there |

**On Windows**, a running program's files are locked, and updating Max from inside Max would break the install halfway. So `max update` opens a small **Updating Max** window and closes itself. The window waits until Max has closed, updates it, says whether it worked, and waits for you to press Enter.

**On macOS and Linux**, the update runs in the same terminal.

### Update notices

Max asks PyPI once a day whether a newer version is out, and remembers the answer in `~/.max_cli/update_check.json`.

- **After a command:** one dim line, such as `Max 1.2.0 is out (you have 1.1.0). Run max update to get it.` It shows only in a terminal, never in scripts or pipes, and never after `max update`, `--version` or `--help`. A command never waits more than a second for the check.
- **In the dashboard:** a notice when it opens. **Settings** > **Maintenance** > **Updates** shows your version, the newest one and when Max last checked. **Check now** asks PyPI again, and **Update to 1.2.0** closes the dashboard and updates Max as above.

Turn the checks off with **Settings** > **Tell me when a new Max is out**, or `UPDATE_CHECK=false` in `~/.max_config.env`.

## doctor

```bash
max doctor              # check everything, asking PyPI for the newest Max
max doctor --offline    # the same, without the network
```

`max doctor` checks one thing per line, marks each, and gives the fix when something is missing:

| Mark | Means |
|------|-------|
| `OK` | In place |
| `--` | Optional: only one feature needs it |
| `!!` | Works, but something could be better (an update, FFmpeg, the AI) |
| `XX` | Broken: fix it first (`max doctor` exits with code 1) |

It checks:

- **Max:** your version, how you installed it, and whether a newer one is out
- **Python:** the version running Max (3.9 or newer)
- **FFmpeg:** for video and audio commands
- **AI:** the main provider and its model, and the fallback
- **Transcripts:** a Gemini key for `max audio transcribe`
- **YouTube:** the fix for HTTP 403 errors, and Deno, which it needs
- **Folders:** that Max can write to `~/.max_cli` and your download folder
- **Settings:** old settings your settings file still sets
- **OCR:** Tesseract, for `max pdf ocr`

`max doctor` changes nothing. When you ask for help in an issue, paste its output; it never shows your API keys.

## python -m max_cli

`python -m max_cli` runs Max the same as `max`, with the Python Max is installed in. It helps when the `max` command isn't on your PATH.
