# Max CLI ⚡

> **The Local, Fast, & Lazy Terminal Assistant.**

**Max** is built for developers and power users who want to get things done **fast** without remembering complex flags or writing throwaway scripts. It is a modular, high-performance tool running locally on your machine.

We added **AI** not to replace the terminal, but to make it "lazier." Instead of remembering `ffmpeg -i input.mp4 -vcodec libx265 -crf 28 output.mp4`, you can just tell Max: *"Make this video smaller."*

---

## 🚀 Philosophy

1. **Local First:** Your files stay on your machine. Core logic (compression, renaming) runs 100% offline.
2. **Be Lazy, Be Fast:** Why type 5 commands when 1 will do? Max automates the mundane.
3. **AI as a Copilot:** The AI translates your natural language into precise, safe shell commands.

## 📦 Installation

```bash
# Clone the repository
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli

# Install globally (Editable mode recommended for devs)
pip install -e .
```

## 🛠 Features Available Now

### 🖼 Fast Image Tools

Bulk compress, resize, and convert images instantly using optimized algorithms.

```bash
# Compress entire folder to JPEGs with 80% quality
max images compress ./VacationPhotos --quality 80 --jpeg

# Resize a specific file for web
max img compress banner.png --scale 50
```

### 📂 File Organization

Stop manually renaming files. Max brings order to chaos.

```bash
# Renames files to 1_doc.pdf, 2_doc.pdf... (Safe Mode)
max files order ./Downloads --dry-run
```

### 📄 PDF Manipulation

Merge reports or shrink scanned documents without uploading them to shady websites.

```bash
max pdf merge ./Invoices -o 2024_Invoices.pdf
```

### 🤖 AI Command Runner

Don't know the command? Just ask.

```bash
max ai ask "Compress all PDFs in this folder and then merge them"
```

---

## 🔮 The Roadmap (Future Features)

We are actively building Max into the ultimate media engine. Here is what's coming:

### 🎥 The Media Engine (FFmpeg)

Integration with **FFmpeg** to handle heavy media locally.

- **Video:** `max video compress input.mp4` (Auto-converts to H.265/AV1).
- **Audio:** `max audio extract video.mp4` (Extracts MP3/AAC).
- **Transcode:** Convert MKV to MP4 seamlessly.

### 🧠 Interactive AI Mode & Memory

Typing `max` without arguments will launch a **Conversational Session**.

- **Context Awareness:** The AI will remember previous commands in the session.
- **Smart History:** "Run that last command again but on the folder above."

### 👁 Multimodal AI (Vision)

Allow Max to "see" your files.

- **Usage:** `max ai analyze ./chart.png`
- **Result:** The AI reads the image and outputs the data as JSON or text.

### 🎨 Generative AI

Create assets directly from the terminal.

- **Command:** `max create image "A cyberpunk city in pixel art style"`
- **Backend:** Integration with DALL-E 3 or Gemini-Flash-Image.

### 🛡 Trusted Sandboxing

Security is paramount.

- **Scoped Permissions:** By default, AI only has read/write access to the current folder.
- **Permission Requests:** If the AI wants to access a system folder, Max will prompt: *"AI requests access to /System. Allow? (y/n)"*

---

## ⚙️ Configuration

Create a `.env` file in the project root to unlock AI features:

```env
# Required for AI features
OPENAI_API_KEY=sk-...
# Optional: Default settings
DEFAULT_QUALITY=85
AI_MODEL=gpt-5-nano
```

## 🤝 Contributing

Max is Open Source. We want to make the terminal fun again.

1. Fork the repo.
2. Install dev dependencies: `pip install -e .[dev]`
3. Submit a Pull Request!

## 📄 License

MIT
