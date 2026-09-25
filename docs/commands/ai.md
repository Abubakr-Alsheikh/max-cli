# AI Commands

The `max ai` commands need an AI provider. Run `max config setup` to pick Google Gemini, OpenAI, Ollama (local, no API key) or a custom endpoint.

## ask

Describe a task in plain English. Max suggests a command, shows it to you and runs it only after you confirm. Max warns you when the command modifies files.

```bash
max ai ask PROMPT [--explain]
```

**Options:**

- `--explain`, `-e` - Explain what the command does

**Examples:**

```bash
max ai ask "Compress all PDFs in Documents folder"
max ai ask "Make this image smaller" --explain
```

## chat

Start an interactive chat. Max keeps the conversation between sessions.

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
