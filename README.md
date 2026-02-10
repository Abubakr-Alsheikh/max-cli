# Max CLI ⚡

> **The Local, Fast, & Lazy Terminal Assistant.**

**Max** is a high-performance, modular CLI framework designed for developers and power users who value speed and efficiency. It transforms complex terminal tasks—media encoding, PDF manipulation, and file organization—into simple, human-readable commands.

Equipped with **Context-Aware AI**, Max doesn't just run commands; it understands your environment, "sees" your files through vision, and generates assets on demand.

---

## 🚀 Philosophy

1. **Local First:** Your files stay on your machine. Core logic (compression, renaming) runs 100% offline.
2. **Be Lazy, Be Fast:** Why type 5 commands when 1 will do? Max automates the mundane.
3. **AI as a Copilot:** The AI translates your natural language into precise, safe shell commands.

## 🌟 Key Features

* **Local-First Media Engine:** Robust wrappers for FFmpeg and Pillow.
* **Professional PDF Suite:** Merge, split, compress, and secure documents locally.
* **Context-Aware AI:** Max scans your current directory to resolve filenames automatically.
* **Universal Downloader:** Grab video/audio from 1000+ sites with smart quality presets.
* **Multimodal Vision:** Analyze screenshots, extract data from receipts, or troubleshoot errors.
* **Image Generation:** Native integration with Gemini "Nano Banana" for creating and editing images.
* **System Tools:** ASCII QR codes for local sharing and clipboard-to-disk workflows.

---

## 📦 Installation

### 1. Prerequisites

1. **FFmpeg:** Max relies on **FFmpeg** for high-speed media processing.
    * **macOS:** `brew install ffmpeg`
    * **Linux:** `sudo apt install ffmpeg`
    * **Windows:** `winget install Gyan.FFmpeg`

2. **JS Runtime (Pick one):**
    * **Node.js:** `brew install node` (Recommended)
    * **Deno:** `brew install deno`

### 2. Install Max

```bash
# Clone the repository
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli

# Install in editable mode
pip install -e .
```

---

## ⚙️ Configuration

Max uses a `.env` file for centralized configuration. It is optimized for **Google Gemini** (using the OpenAI compatibility layer) but works with any OpenAI-compatible provider.

```ini
# .env

# --- Provider Setup ---
OPENAI_API_KEY=your_google_ai_studio_key
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/

# --- Model Selection ---
# For Text reasoning, Vision analysis, and Context-aware commands
AI_MODEL=gemini-1.5-flash

# Dedicated model for Image Generation and Editing (Nano Banana)
AI_IMAGE_MODEL=gemini-2.5-flash-image

# --- Defaults ---
DEFAULT_QUALITY=80
```

---

## 🛠 Command Reference

### 🎥 Video & Audio (`max video`)

High-level control over FFmpeg without the syntax headaches.

* **`compress`**: Shrink videos using H.264 (Presets: `high`, `balanced`, `max`).
* **`cut`**: Frame-perfect trimming using `--start`, `--end`, or `--duration`.
* **`gif`**: High-quality GIF generation with custom palette rendering.
* **`louder`**: Boost quiet audio tracks by decibels (e.g., `--db 10`).
* **`snap`**: Capture a high-res JPG from any timestamp.
* **`mute`**: Instantly remove audio tracks without re-encoding video.

### 📄 Document Suite (`max pdf`)

Professional PDF management powered by PyMuPDF.

* **`bundle`**: The ultimate pipeline—merges a folder, compresses the result, and cleans up.
* **`split`**: Extract specific pages (e.g., `-p 1-5, 8, 10-12`).
* **`stamp`**: Overlay watermarks (e.g., "CONFIDENTIAL") on all pages.
* **`lock`**: Secure documents with AES-256 password encryption.
* **`rip`**: Extract all embedded images from a PDF into a folder.

### 📥 Universal Downloader (`max grab`)

Smart downloading with **Quality Presets**:

* **`s` (Small)**: 480p Video / 64k Audio (Data saver).
* **`m` (Medium)**: 720p Video / 128k Audio (Standard).
* **`h` (High)**: 1080p Video / 192k Audio (HD Default).
* **`x` (Xtreme)**: 4K Video / 320k Audio (Best quality).

```bash
max grab "URL" -a -q s        # Download tiny podcast-ready MP3
max grab "URL" -q x           # Download 4K archival video
```

#### **Advanced Grab Controls**

```bash
max grab "URL" -i 1              # Download only the 1st video in a playlist
max grab "URL" -i "1-5"          # Download first 5 videos
max grab "URL" --no-playlist     # Force download single video from a playlist URL
max grab "URL" -a --no-meta      # Download audio without ID3 tags or thumbnails
```

### 📂 File Management (`max files`)

* **`order`**: Sequential renaming (e.g., `1_doc.pdf`, `2_doc.pdf`).
* **`smart-sort`**: AI-powered semantic organization. Max reads filenames and moves them into logical categories (e.g., `Invoices/`, `Legal/`, `Screenshots/`).

### 🖼 Image Suite (Pillow Wrapper)

High-speed bulk image processing with automatic EXIF orientation correction. All commands default to the **current directory (`.`)** if no path is provided.

```bash
# 1. The All-in-One Optimizer (Compress)
# High-speed compression with optional resizing and format forcing.
max img compress ./Photos -q 75           # Compress with 75% quality
max img compress . --jpeg -m 1080         # Force to JPG and limit size to 1080px
max img compress logo.png --quantize      # Lossy PNG optimization (8-bit)

# 2. Precision Resizing
max img resize . --width 1920             # Set width (height scales automatically)
max img resize . --height 500              # Set height (width scales automatically)
max img resize . --scale 50                # Shrink by 50%

# 3. Format Conversion
max img convert ./Assets --to webp        # Convert all images to modern WebP
max img convert shot.bmp --to png         # Convert single file to PNG

# 4. Privacy Scrubbing (Metadata Stripping)
# Removes GPS coordinates, camera model, and timestamps.
max img strip ./SocialMedia               # Remove EXIF data from all images
```

---

## 🧠 The AI Assistant

### 1. Context-Aware Execution

Max reads your current directory. You don't need to be specific.

```bash
# In a folder with 'IMG_2024.jpg'
max ai ask "Make the photo 50% smaller"
# Max resolves context and runs: max images compress IMG_2024.jpg --scale 50
```

### 2. Vision & Analysis

```bash
max ai analyze error.png -p "Why is my build failing?"
max ai analyze receipt.jpg -p "Total price in JSON format"
```

### 3. Generative Creative Suite

```bash
max ai create "A minimalist logo for a tech company" -o logo.png
max ai edit photo.jpg "Change the sky to a sunset" -o new_photo.jpg
```

### 4. Interactive Chat

Start a persistent session where Max remembers your previous tasks.

```bash
max ai chat
> User: What's the biggest video in this folder?
> Max: 'final_render.mp4' is 1.2GB.
> User: Compress it to medium quality.
> Max: [Executes compression...]
```

### 5. Sharing & System

* **`max share [URL/Text]`**: Generates an ASCII QR code in your terminal. Perfect for mobile testing.
* **`max paste [file.png]`**: Saves the image currently in your system clipboard to a file.
* **`max copy [file.txt]`**: Copies the entire content of a text file to your clipboard.

---

## 🏗 Architectural Design

* **Modular Monolith:** Logic is separated into `core/` (Services) and `interface/` (CLI).
* **Strategy Pattern:** Media processing engines are interchangeable.
* **Type Safety:** Strict Python type-hinting throughout for maintainability.
* **Rich UI:** Every command features color-coded feedback and real-time progress bars.
This section is the "Vision" for Max. It targets high-impact utilities that turn the CLI into an intelligent agent capable of understanding audio, automating coding tasks, and managing cloud resources.

## 🔮 The Roadmap: Future Features & Improvements

We are constantly evolving **Max** to be the definitive local-first terminal assistant. Here is what we are building next:

### 🎙 AI Intelligence & Content Extraction

* **AI Transcription (`max audio transcribe`)**: Integrate OpenAI Whisper (Local or API) to extract text from any video or audio file.
  * *Use Case:* "Max, transcribe this 1-hour meeting recording into a text file."
* **AI Summarization**: Feed transcribed text or long PDFs into Gemini/GPT-4 to generate executive summaries.
* **Auto-Subtitle Generation**: Automatically generate and burn-in `.srt` subtitles for videos using AI-detected speech.

### 🧠 Semantic Knowledge Base (Local RAG)

* **Local File Indexing**: Allow Max to "index" your local Documents folder.
* **Natural Language Search**: Ask questions across your files.
  * *Query:* "Max, which PDF mentions the contract terms for the 2024 project?"

### 🎥 Advanced Media Automation

* **Smart Silence Removal**: Automatically cut silent gaps out of video/audio recordings—perfect for podcasters.
* **Auto-Face Blurring**: Use local computer vision to detect and blur faces in videos for privacy before sharing.
* **Color Grading Presets**: Apply cinematic looks to videos via simple CLI commands.

### 🛠 Developer Productivity Tools

* **AI Commit Messages**: Max reads your `git diff` and suggests a perfect, conventional commit message.
* **Local Port Tunneling**: Integrate with tools like `ngrok` or `cloudflared` via `max share --tunnel 8000`.
* **Docker Management**: Simplify complex Docker commands.
  * *Command:* `max dev cleanup` (Kills all unused containers, volumes, and dangling images).

### ☁️ Cloud & Backup Integration

* **S3/Cloud Sync**: Quick-upload assets to AWS S3, Google Cloud Storage, or R2 for hosting.
  * *Command:* `max push image.jpg --to s3-bucket`
* **Temporary File Hosting**: Upload a file to a temporary, encrypted cloud link that expires in 24 hours.

### 🛡 Security & Privacy

* **PII Scanner**: Scan images or PDFs for Personal Identifiable Information (Credit cards, SSNs, Emails) before you upload or share them.
* **Deepfake Detection**: Simple checks for image/video manipulation markers.

---

### 💡 Have an Idea?

Max is built for the community. If you have a workflow that feels "too slow" or "too complex," [open an issue](https://github.com/Abubakr-Alsheikh/max-cli/issues) and we might build a command for it!

## 🤝 Contributing

1. Fork the repository.
2. Install development dependencies: `pip install -e .[dev]`
3. Ensure code passes `ruff` linting and `mypy` type checks.
4. Submit a Pull Request.

## 📄 License

MIT
