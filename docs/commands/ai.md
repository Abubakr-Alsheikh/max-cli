# AI Commands

The `max ai` commands need an AI provider. Run `max config setup` to pick Google Gemini, OpenAI, Ollama (local, no API key) or a custom endpoint.

## ask

Say what you want done in plain words, and Max's AI agent does it. It picks Max's own actions (compress, merge, organize ...), runs them, shows each step, and tells you what it did and where the results are.

```bash
max ai ask PROMPT [--dry-run]
max PROMPT
```

You can leave out `ai ask`: when the first word after `max` isn't a command, Max hands the whole line to the agent.

While it works, Max prints each action as it starts (`⚙ files order`) with its arguments under it, then the result (`✓ File ordering complete!`, with the time it took and the files it made). The answer comes last, rendered as Markdown in a panel that counts the actions and tokens:

```text
  ⚙ files preview
      target  notes.txt
      lines   20
      ✓ notes.txt
┌─ Max ──────────────────────────────────────────────┐
│  • Buy milk.                                        │
│  • Call Sam.                                        │
└────────────────────────────── 1 action · 5,194 tokens ┘
```

**Options:**

- `--dry-run` - Show the steps the agent would run, and change nothing

**Examples:**

```bash
max ai ask "Compress all PDFs in my Documents folder"
max "shrink every video in this folder"
max "merge the PDFs in Downloads into one file" --dry-run
```

**How it decides:** before it acts or advises, the agent can look without changing anything:

- **List a folder:** its subfolders, each file's kind and size, counts by kind.
- **Inspect a file or folder:** a song's artist, album and length, a video's length and codecs, a photo's size, date and camera, a PDF's pages, or a summary of a music or photo folder (its artists and albums, its formats).
- **Find files** in a folder and its subfolders by kind, name, size and age: "videos over 1 GB in Downloads", "photos from this year", "what's taking space here".
- **Check a link** before downloading it: title, length, qualities with their sizes, a playlist's items.
- **Read the recent activity:** what Max did lately and which file changes undo can reverse, so "undo that" and "what did I compress yesterday?" work.

Ask "how would you organize this folder?" and it answers from what's there. Every request and every action the agent runs, here or in the dashboard, goes into the activity log (`max` dashboard, Activity > History).

**What the agent may do:**

- It runs only Max's actions. It never runs other programs or shell commands.
- It works in the folder you started in, plus folders you name in your request: a path such as `D:\Photos`, or a usual folder by name ("my Downloads", "Music"). It also may save to your download folder. It refuses any other path and asks you to name the folder.
- Before an action moves, overwrites or deletes files, it asks you, even when `CONFIRM_DESTRUCTIVE` is off. Answer no and it skips that step. A dry run (`smart-sort --dry-run`, `organize --dry-run`) changes nothing, so it doesn't ask.
- Looking at files never asks and never changes anything, but stays inside the same folders.
- One request stops after 12 steps or 60,000 tokens. Ask it to go on if there's more.
- File changes go into the undo log, so `max files undo` puts them back.

The agent needs a model that can call tools: most OpenAI, Gemini, Claude and Llama 3.1+ models can. If yours can't, Max says so. The old `--explain` flag still works and does nothing.

## chat

Talk with the agent: each request runs Max's actions, and it remembers the conversation. A new session starts from the last 20 messages of the saved conversation.

```bash
max ai chat [--clear] [--export FILE] [--import FILE]
```

**Options:**

- `--clear` - Delete the saved conversation
- `--export`, `-e` - Save the conversation to a JSON file
- `--import`, `-i` - Load a conversation from a JSON file

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

- `--output`, `-o` - Save path
- `--model` - Image model override (default: `gemini-2.5-flash-image`)

**Example:**

```bash
max ai create "A cat on a bike" -o cat.png
```

## edit

Change an existing image with a text instruction.

```bash
max ai edit TARGET PROMPT [-o PATH] [--model MODEL]
```

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
- `--ext` - Comma-separated extensions (default: `txt,md,py,json,yaml`)

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
- `-o` - Save the JSON to a file

**Example:**

```bash
max ai extract receipt.jpg -s "total:Total amount" -s "date:Date" -o receipt.json
```
