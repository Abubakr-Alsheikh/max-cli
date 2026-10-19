# Is Max Safe? Antivirus Warnings

Max is open source: every line of the program and of its installers is on [GitHub](https://github.com/Abubakr-Alsheikh/max-cli), and each release on [PyPI](https://pypi.org/project/max-cli/) is built from that code by a public [GitHub workflow](https://github.com/Abubakr-Alsheikh/max-cli/actions/workflows/release.yml). This page says what Max installs, where it gets each piece, and what to do when Windows Defender or another antivirus stops something.

## What gets installed, and from where

| Piece | Comes from | Where it goes |
|-------|------------|---------------|
| **uv** (installs Python programs) | winget (Windows' package manager) when you have it, else [astral.sh](https://docs.astral.sh/uv/), the company that makes it | `%LOCALAPPDATA%\Microsoft\WinGet` or `~\.local\bin` |
| **Python** (for Max only) | uv's own copy, from the [python-build-standalone](https://github.com/astral-sh/python-build-standalone) project | uv's folder in your user profile |
| **Max** | [PyPI](https://pypi.org/project/max-cli/), the Python package index | uv's folder; the `max` command in `~\.local\bin` |
| **FFmpeg** (video and audio) | winget (Gyan's build) or Homebrew when you have them; else a download from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) or [BtbN](https://github.com/BtbN/FFmpeg-Builds) (Windows and Linux) or [Martin Riedl](https://ffmpeg.martin-riedl.de/) (macOS), which are the builds [ffmpeg.org](https://ffmpeg.org/download.html) links to | the package manager's folder, or `~\.max_cli\bin` |

Everything goes into your own user folder, so nothing needs administrator rights. You don't need to open PowerShell as administrator.

When Max downloads FFmpeg itself, it checks the file against the SHA-256 checksum its site publishes, and throws the file away if they differ.

**Read the installer before you run it.** The one-line installer is a short script: open [install.ps1](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/install.ps1) (Windows) or [install.sh](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/install.sh) (macOS, Linux) and read it first. Or skip it: the [step-by-step install](start-here.md#step-2-install-max) runs the same two commands by hand.

## Why an antivirus might complain

Antivirus programs judge unfamiliar files by how they look and behave. They sometimes stop safe files (a *false positive*), most often these:

- **`max.exe`**. uv makes a small launcher program called `max.exe` that starts Python with Max. Every launcher like it looks the same to an antivirus, and new ones have been flagged by mistake. The launcher holds no Max code.
- **`ffmpeg.exe` downloaded by Max**. A program downloaded by another program, rather than by a browser, gets extra suspicion. Installing FFmpeg with winget avoids this: `winget install Gyan.FFmpeg`.
- **The one-line installer** (`irm ... | iex`). Downloading a script and running it at once is a pattern malware uses too, so Windows can block it with "This script contains malicious content and has been blocked by your antivirus software". Use the step-by-step install instead.

## When Windows Defender blocks something

1. Open **Windows Security** > **Virus & threat protection** > **Protection history**, and open the newest entry.
2. Read which file it names (`max.exe`, `ffmpeg.exe`, a `.ps1` script) and the threat name (for example `Trojan:Win32/Wacatac.B!ml`; a name ending in `!ml` comes from a machine-learning guess, which is where false positives come from).
3. If it's one of the files above, you can choose **Actions** > **Allow on device** or **Restore**.
4. Please [report the false positive to Microsoft](https://www.microsoft.com/en-us/wdsi/filesubmission): pick "Software developer" or "Home customer", attach the file or name it, and say it's from max-cli. When Microsoft agrees, it clears the file for every user.
5. [Open an issue](https://github.com/Abubakr-Alsheikh/max-cli/issues) with the file name and the threat name, so we can follow it up.

If you'd rather not allow anything, install Max with pip and start it through Python, which needs no launcher and no installer script:

```bash
pip install max-cli          # with Python 3.9 or newer from python.org or the Microsoft Store
python -m max_cli            # Max, started by python.exe instead of max.exe
```

pip makes a `max.exe` launcher too; if your antivirus stops that one, `python -m max_cli` still works.

## Check Max yourself

```bash
max doctor        # what Max uses, where it is, and what's missing
max --version     # the version you have; compare it with PyPI
```

`max doctor` changes nothing and never shows your API keys. Your keys stay in `~/.max_config.env` on your computer; Max sends a key only to the AI service it belongs to.
