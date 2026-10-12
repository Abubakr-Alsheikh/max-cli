# Start Here: Max for Beginners

This guide takes you from nothing to your first finished job in about ten minutes. You don't need to know Python or programming. You'll copy a few lines into a window, press Enter, and Max does the rest.

!!! tip "What you need"
    - A computer with Windows 10 or 11, macOS, or Linux
    - An internet connection
    - About 500 MB of free space

## Words you'll see

| Word | What it means |
|------|---------------|
| **Terminal** | A window where you type commands instead of clicking. Max lives there. |
| **Command** | One line you type, such as `max --version`. Press **Enter** to run it. |
| **Path** | Where a file is on your computer, such as `C:\Users\Sara\Videos\trip.mp4`. |
| **Folder** | The same thing your file manager shows. Max often works on a whole folder at once. |

You can paste into the terminal with **Ctrl+V** on Windows and Linux (some Linux terminals use **Ctrl+Shift+V**), or **Cmd+V** on a Mac.

## Step 1: Open a terminal

=== "Windows"

    Press the **Windows key**, type **Terminal**, and press **Enter**. On Windows 10, type **PowerShell** instead if Terminal doesn't appear.

=== "macOS"

    Press **Cmd+Space**, type **Terminal**, and press **Enter**.

=== "Linux"

    Press **Ctrl+Alt+T**, or open **Terminal** from your apps.

A window opens with a blinking cursor. That's where you type.

## Step 2: Install uv

uv is a small, free installer for Python programs. It brings its own copy of Python, so you don't have to install Python yourself, and it keeps Max separate from anything else on your computer.

Copy the line for your system, paste it into the terminal, and press **Enter**:

=== "Windows"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "macOS and Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

When it says it's done, **close the terminal and open a new one**. The new window knows where uv is; the old one doesn't.

!!! note "Prefer a package manager?"
    `winget install --id=astral-sh.uv -e` on Windows or `brew install uv` on a Mac installs the same thing.

## Step 3: Install Max

In the new terminal, run:

```bash
uv tool install max-cli
```

uv downloads Max and everything it needs. It takes a minute or two the first time.

Close the terminal again and open a new one, then check that Max answers:

```bash
max --version
```

You should see a line such as `max 1.1.0`. Max is installed.

## Step 4: Open the dashboard

Type `max` on its own and press **Enter**:

```bash
max
```

The dashboard opens inside the terminal. It has a page for each kind of job: Download, Video, Audio, Images, PDF, Files and AI.

- Press a **number key** (1 to 9) to jump to a page, or click it in the sidebar.
- Press **?** to see every key.
- Press **q** to quit.

Your mouse works too: click buttons, fields and checkboxes like in any app.

## Step 5: Do your first job

Pick one to try.

**Download a video or song.** Press **2** for the Download page. Paste a YouTube link into the LINK box. Max shows the title, the length and the sizes. Pick **Video** or **Audio (MP3)**, pick a quality, and press **Download**. The file goes into your `Max Downloads` folder; **Open download folder** in the TOOLS card opens it.

**Make a video smaller.** Press **3** for the Video page, pick your video with **Browse**, choose **compress**, and press **Run**. Max saves `trip_compressed.mp4` next to the original and never changes the original.

**Merge PDFs.** Press **6** for the PDF page, pick a folder of PDFs, choose **merge**, and press **Run**.

The first time you use a video or audio job, Max offers to download **FFmpeg**, the free video tool it uses behind the scenes. Say yes. It happens once.

## Step 6 (optional): Turn on the AI helper

Max can do jobs you describe in your own words, such as "make every photo in my Pictures folder smaller", and write transcripts of recordings. For that it needs an AI key. Google Gemini gives you one for free:

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey) and sign in with a Google account.
2. Press **Create API key** and copy the key. Keep it private, like a password.
3. In the dashboard, press **,** (comma) to open **Settings**. Under the main AI, pick **Google Gemini**, paste the key, and pick a model such as `gemini-flash-latest`. Press **Test** to try the key, then **Save changes**.

Now press **8** for the AI page and type what you want. Max shows its plan and asks before it changes or deletes anything.

## Typing commands instead

Everything in the dashboard is also a short command. You don't have to learn them, but they're quick once you know a few:

```bash
max video compress "C:\Users\Sara\Videos\trip.mp4"
max grab download "https://youtube.com/watch?v=..." -a
max pdf merge "C:\Users\Sara\Documents\Scans"
max "convert every m4a in my Music folder to mp3"
```

!!! tip "Two tricks that save typing"
    - **Drag a file or folder onto the terminal window** and its path appears where you're typing.
    - **Put quotes around a path with spaces**, such as `"My Videos\trip.mp4"`. Without them, Max sees two separate words.

## Keep Max up to date

New versions add features and fix problems. To update, run:

```bash
uv tool upgrade max-cli
```

To remove Max completely:

```bash
uv tool uninstall max-cli
```

Your settings stay in a `.max_config.env` file in your home folder, and Max's own data in a `.max_cli` folder there. Delete both if you want no trace left.

## If something goes wrong

**"uv" or "max" is not recognized, or "command not found".**
Close the terminal and open a new one; a window opened before the install doesn't know about it. If that doesn't help, run `uv tool update-shell`, then open a new terminal once more.

**"Running scripts is disabled on this system" (Windows).**
You typed only part of the uv line. Copy the whole line from Step 2, starting with `powershell -ExecutionPolicy ByPass`.

**The dashboard looks broken or its letters overlap.**
Use **Windows Terminal** on Windows (it comes with Windows 11; get it from the Microsoft Store on Windows 10) and make the window bigger. For page icons, run `max config setup-font` once.

**A YouTube download fails with "HTTP 403".**
YouTube blocked the request. On the Download page, press **Install fix** in the TOOLS card, or run `max grab pot-setup`.

**FFmpeg didn't download.**
Run `max config setup-ffmpeg` and try again.

**Still stuck?**
Run `max config validate`, copy what it says, and [open an issue](https://github.com/Abubakr-Alsheikh/max-cli/issues). Never paste your AI key into an issue.

## Already have Python?

If you use Python already, any of these works too: `pipx install max-cli`, or `pip install max-cli` inside a virtual environment. See [Installation](installation.md) for the details, the optional extras and the AI providers.
