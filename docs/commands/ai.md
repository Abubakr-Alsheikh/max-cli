# AI Commands

The `max ai` commands need an AI provider. Run `max config setup` (or open the dashboard's Settings page) to pick the main AI (OpenAI or a custom URL, OpenRouter, Google Gemini, or Ollama on this computer) and a fallback that takes over when the main one fails. Each has its own API key (Ollama needs none) and its own model. When the main AI returns an error, Max sends the request to the fallback and keeps using it until the command ends (in `ai chat`, until you leave the chat). The agent's answer panel names the model that answered and adds "(fallback)" when the main AI failed. See [config setup](config.md#setup).

## ask

Say what you want done in plain words, and Max's AI agent does it. It picks Max's own actions (compress, merge, organize ...), runs them, shows each step, and tells you what it did and where the results are.

```bash
max ai ask PROMPT [--dry-run]
max PROMPT
```

You can leave out `ai ask`: when the first word after `max` isn't a command, Max hands the line to the agent. The words up to the first option form the request, so `max shrink every video here --dry-run` works without quotes.

While it works, Max prints each action as it starts (`⚙ files order`) with its arguments under it, then the result (`✓ File ordering complete!`, with the time it took and the files it made). The answer comes last, rendered as Markdown in a panel that counts the actions and tokens and names the model:

```text
  ⚙ files preview
      target  notes.txt
      lines   20
      ✓ notes.txt
┌─ Max ─────────────────────────────────────────────────────────┐
│  • Buy milk.                                                   │
│  • Call Sam.                                                   │
└──────────────────────────── 1 action · 5,194 tokens · gpt-4o-mini ┘
```

**Options:**

- `--dry-run` - Show the steps the agent would run, and run nothing. The agent still looks at your files to plan, but it runs, queues and changes nothing, so it never asks you to confirm. Each planned step shows as `→ Would run ...`, and a batch lists the files it would run on, how big they are and which it would skip.

**Examples:**

```bash
max ai ask "Compress all PDFs in my Documents folder"
max "shrink every video in this folder"
max "merge the PDFs in Downloads into one file" --dry-run
max "convert every m4a under Music, subfolders too, to mp3"
max "remember that my music lives in D:/Music"
```

**How it decides:** before it acts or advises, the agent can look without changing anything:

- **List a folder:** its subfolders, each file's kind and size, counts by kind.
- **Inspect a file or folder:** a song's artist, album and length, a video's length and codecs, a photo's size, date and camera, a PDF's pages, or a summary of a music or photo folder (its artists and albums, its formats).
- **Find files** in a folder and its subfolders by kind, name, size and age: "videos over 1 GB in Downloads", "photos from this year", "what's taking space here". It can also list only the work left: asked to convert M4A files to MP3, it finds the M4A files without an MP3 beside them, skips the rest and tells you which it skipped.
- **Check a link** before downloading it: title, length, qualities with their sizes, a playlist's items.
- **Read the recent activity:** what Max did lately and which file changes undo can reverse, so "undo that" and "what did I compress yesterday?" work. "Undo that" runs `files undo`, which asks first.
- **Check the queued jobs:** which are running, with their progress, which wait, and how the latest ones ended, so "is my download done?" works.
- **Check the computer:** free space on each drive, memory, CPU, battery and uptime, and the programs using the most memory ("what's eating my memory?").
- **Look at an image:** the vision model answers a question about one picture ("is this a screenshot?", "what's in it?"). Each look is an AI call, so it uses it for a few images, not a whole album.

It can also **open** a file or folder in the allowed folders, or a web link, with its default app when you ask to see it ("open the merged PDF"). It never opens programs, scripts or shortcuts, since that would run them.

**Stopping a program:** "close Notepad" or "stop whatever is eating my memory". The agent names the program, its process id and its memory, and asks you before it stops it; unsaved work in that program is lost. It never stops system processes (svchost, explorer and the like), Max itself, or another user's programs.

**Commands (off unless you turn them on):** with **Let the agent run commands** on in Settings > AI agent (`AGENT_SHELL=true`), the agent can run a program with its arguments when no Max action fits, for example `git status` or `ffprobe clip.mp4`. It shows you the exact command and the folder, and runs it only after your yes. It runs one program with no shell, so pipes, redirects, `&&` and Windows built-ins such as `dir` don't work. The folder must be one it may use, a command stops after 60 seconds, and the agent sees the last 4,000 characters of its output. Each command goes into the activity log.

**Cost:** set **Cheaper model for summaries** (`AI_FAST_MODEL`) in Settings > AI agent to a cheaper model of your main AI; Max then uses it to summarise long chats. OpenAI and Gemini reuse the unchanging start of each request (the instructions and the tool list) by themselves, which costs less; Max keeps that part the same from one request to the next.

Every request also carries a few lines Max adds about where you are: what the folder holds (files by kind, subfolders), which queued jobs are running or waiting, and the last thing Max did. So "shrink these" works without the agent listing the folder first.

**Plans and questions:** before work with three or more steps or many files, the agent shows its plan as a numbered list and waits. Press Enter (or `y`) to let it go ahead, `n` to stop it, or type what to change ("only the live recordings") and it shows a new plan. When a request is unclear and a wrong guess would cost (move or delete? which folder?), it asks you one question, with numbered choices when there are some; type the number or your own answer. On the dashboard both come up in a dialog. With `--dry-run` it shows the plan and asks nothing. When a request turns to a second kind of change without a plan (convert, then compress), Max asks the agent to show the plan first. Approving a plan doesn't skip the question before an action moves, overwrites or deletes files.

Ask "how would you organize this folder?" and it answers from what's there. Every request and every action the agent runs, here or in the dashboard, goes into the activity log (`max` dashboard, Activity > History).

**What the agent may do:**

- It runs only Max's actions from the `video`, `grab`, `images`, `pdf`, `files`, `audio` and `tools` groups. It never runs other programs or shell commands.
- It works in the folder you started in, plus folders you name in your request: a path such as `D:\Photos` (a file's path names its folder), or a usual folder by name: Desktop, Documents, Downloads, Music, Pictures or Videos ("my Downloads"). It may also use your download folder. A drive root such as `D:\` never counts. It refuses any other path and asks you to name the folder. In `ai chat`, a folder you named stays allowed for the rest of the chat.
- Before an action moves, overwrites or deletes files, it asks you, even when `CONFIRM_DESTRUCTIVE` is off. Answer no and it skips that step and doesn't try it again. A dry run (`smart-sort --dry-run`, `organize --dry-run`) changes nothing, so it doesn't ask. Actions that only write new files (a compressed copy, a merged PDF) don't ask.
- Looking at files never asks and never changes anything, but stays inside the same folders.
- When the model asks for several actions in one step, Max runs up to 4 at the same time. Actions on the same file or folder run one after another, in order.
- When one action applies to several files (convert each M4A to MP3), the agent asks for them in one call: a list of files, a folder or a pattern, up to 500 files. It can narrow a folder: subfolders too, a name pattern (`*live*`), a size or an age ("videos over 1 GB from this year"). Max skips files whose result is already there, and the agent tells you which it skipped. You get one question for the whole batch, with the count, the size and the skipped files ("142 files, 3.2 GB (a.m4a, b.m4a ...); 18 done already, skipped"), not one per file. On the dashboard the batch gets one card that counts the files done, failed and running.
- A batch of more than 20 files of a long job (video and audio work, OCR, downloads) goes to the background queue instead of holding the conversation, when the agent can queue.
- After every action, Max checks the files it reports: each must exist and not be empty. A missing or empty result counts as a failure, and the agent tells you about it instead of saying it all worked.
- From the terminal, it can queue long jobs instead of waiting for them: most video work (compress, convert, cut, denoise and the rest that take `--queue`), `audio compress` and `audio denoise`, `pdf ocr` and downloads. After the answer, Max starts the background worker and tells you how many jobs it queued. Your terminal is free at once, `max queue status` shows the jobs, and closing the terminal doesn't stop them. See [Queue](queue.md).
- One request stops after 12 rounds with the model, 40 actions or 100,000 tokens. Ask it to go on if there's more.
- Once you say no to an action, it doesn't ask about that action again in the same request. Answer a question in words ("why not use audio batch?") and it takes that as your instruction.
- Each action it can run carries a short guide: when to use it and which action to use instead ("Not for music track numbers: audio batch"), so it picks the right one of similar actions.
- It remembers lasting facts and preferences you give it, between sessions: "remember that my music lives in D:/Music", "I like 192 kbps MP3s". Every new session starts with these notes, and it deletes a note you correct. See [memory](#memory).
- File changes go into the undo log, so `max files undo` puts them back.

**What the agent can't do:**

- Use `max ai`, `max config`, `max queue` or `max plugins` commands, or change your settings.
- Run `video record`, `video stream` or `video preview`, or `pdf lock` (it would have to see your password). Run those yourself.
- Work outside the folders above, even to look.

The agent needs a model that can call tools: most OpenAI, Gemini, Claude and Llama 3.1+ models can. If yours can't, Max says so. Gemini 3 models work through Google's OpenAI-compatible URL: Max sends back the thought signature Gemini adds to each tool call, which Gemini requires on the next turn. The old `--explain` flag still works and does nothing.

## chat

Talk with the agent: each request runs Max's actions, and it remembers the conversation. The agent follows the same rules as `ask`. Type `help` for example requests, and `exit` or `quit` to leave. Max saves the conversation after every request, so Ctrl+C or closing the window loses nothing, and a new session starts from the last 20 messages of it. When a chat grows long (about 12,000 tokens), Max turns its oldest turns into a short summary and keeps the last two requests as they were, so the chat stays within the token limit. The dashboard's AI page does the same.

```bash
max ai chat [--clear] [--export FILE] [--import FILE]
```

**Options** (each one does its job and exits without starting a chat):

- `--clear` - Delete the saved conversation
- `--export`, `-e` - Save the conversation to a JSON file
- `--import`, `-i` - Load a conversation from a JSON file

## memory

See and delete what the agent remembers between sessions. The agent saves a note when you tell it a lasting fact or preference; `ask`, `chat` and the dashboard's AI page all read the same notes from `~/.max_cli/agent_memory.json`.

```bash
max ai memory [--forget ID] [--clear] [--force]
```

- No option: list the notes with their ids and dates.
- `--forget ID` - Delete one note.
- `--clear` - Delete every note. It asks first unless you pass `--force`.

Max keeps the 50 newest notes, each up to 300 characters.

## analyze

Ask a vision model about an image.

```bash
max ai analyze TARGET [--prompt QUESTION]
```

**Options:**

- `--prompt`, `-p` - Your question (default: "Describe this image in detail.")

**Example:**

```bash
max ai analyze invoice.png -p "Extract the total amount and date"
```

## create

Generate an image from a text description.

```bash
max ai create PROMPT [--output PATH] [--model MODEL]
```

**Options:**

- `--output`, `-o` - Save path (default: `created_image.png` in the current folder)
- `--model` - Image model. Without it, Max uses the image model you picked for your main AI (`AI_IMAGE_MODEL`, `OPENROUTER_IMAGE_MODEL` or `GEMINI_IMAGE_MODEL`), and the fallback's when the main one fails

**Example:**

```bash
max ai create "A cat on a bike" -o cat.png
```

## edit

Change an existing image with a text instruction.

```bash
max ai edit TARGET PROMPT [-o PATH] [--model MODEL]
```

**Options:**

- `-o` - Save path (default: `edited_<name>` in the current folder). `edit` has no long `--output` form
- `--model` - Image model, as for `create`

**Example:**

```bash
max ai edit photo.jpg "Turn the sky purple" -o purple.jpg
```

## search

Find files by meaning instead of exact words. Max reads each matching file under the folder, including subfolders, and asks the AI whether it matches your query. Each file costs one AI request, so point it at a small folder.

```bash
max ai search QUERY [PATH] [--ext EXTENSIONS]
```

**Options:**

- `PATH` - Folder to search (default: current folder)
- `--ext` - Comma-separated extensions (default: `txt,md,py,json,yaml`). Search reads only `txt`, `md`, `py`, `json`, `yaml` and `yml` files; Max skips any other extension you list and says so

**Example:**

```bash
max ai search "notes about the Q3 budget" ./notes --ext md,txt
```

## extract

Pull structured fields out of an image, such as a receipt or invoice. Max prints the result as JSON.

```bash
max ai extract TARGET --schema FIELD:DESCRIPTION [--schema ...] [-o FILE]
```

**Options:**

- `--schema`, `-s` - `field:description` pair (required, repeatable)
- `-o` - Save the JSON to a file (no long `--output` form)

**Example:**

```bash
max ai extract receipt.jpg -s "total:Total amount" -s "date:Date" -o receipt.json
```
