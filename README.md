# 🎬 AimIndia Video Studio

Automated Headless & Interactive Video Processing Studio powered by **Kaggle GPU (Tesla T4 x2)**.

A specialized web application and Kaggle notebook workflow to automatically hide watermarks (e.g. NotebookLM watermark), trim outro endings (e.g. Gemini slides), and overlay your custom / AimIndia brand logo with hardware-accelerated NVENC encoding.

---

## ✨ Features

- **🌐 Web-Driven Kaggle Orchestration**: Manage everything from a modern web dashboard without manually editing code or uploading large files to Kaggle by hand.
- **⚡ Hardware-Accelerated NVENC Encoding**: Uses static FFmpeg builds with NVIDIA NVENC GPU support on Kaggle (with transparent CPU libx264 fallback).
- **📐 Lanczos Digital Zoom & Unsharp Edge Recovery**: Crops a clean corner margin where the watermark sits, scales back to native dimensions with Lanczos interpolation, and applies subtle unsharp filtering to preserve crisp detail.
- **✂️ Outro Trimmer**: Precision timing cutoff to eliminate unwanted platform ending slides.
- **🖼️ Transparent Logo Overlay**: Preloaded with AimIndia transparent logo or upload any custom PNG logo with dynamic size and offset controls.
- **👁️ Fast 1-Frame Position Preview**: Instantly preview watermark cropping and logo alignment in your web browser before launching the full GPU render.
- **🔄 Dual Execution Mode**:
  1. **Web Studio Mode**: Syncs assets as a private Kaggle dataset, triggers the GPU kernel headlessly, streams logs in real-time, and downloads the finished output.
  2. **Interactive Kaggle Notebook**: Run `notebook/aimindia-video-notebook.ipynb` or `aimindia-video(5).ipynb` directly inside Kaggle with Gradio UI.

---

## 🚀 Quick Start (Local Run)

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Launch the Web Studio**:
   ```bash
   ./run.sh
   # Or run directly:
   python3 app.py
   ```

3. **Open in Browser**:
   Visit `http://localhost:5000`

---

## ☁️ Cloud Deployment

Ready for 1-click deployment on:
- **Hugging Face Spaces** (Docker template, port 7860)
- **Render** (using bundled `render.yaml`)
- **Koyeb** / **Railway** (using `Dockerfile` or `Procfile`)

---

## 📁 Repository Structure

```text
├── aimindia-video(5).ipynb              # Exact original Kaggle notebook
├── notebook/
│   └── aimindia-video-notebook.ipynb    # Dual-mode production notebook (Interactive + Headless)
├── templates/
│   └── index.html                       # Modern web studio dashboard
├── static/
│   ├── style.css                        # Custom responsive dark theme
│   ├── app.js                           # Real-time UI & WebSocket-like log streaming
│   └── default_logo.png                 # Bundled transparent AimIndia logo
├── uploads/                             # Local staging for videos and logos
├── output/                              # Download destination for clean videos
├── app.py                               # Flask backend & Kaggle API orchestrator
├── requirements.txt                     # Python dependencies
├── Dockerfile                           # Container configuration for cloud deployment
├── render.yaml                          # Render cloud deployment config
├── Procfile                             # Process runner for PaaS hosting
├── run.sh                               # Quick start shell script
└── README.md                            # Documentation
```

---

## 🔒 Kaggle Credentials & Privacy

- Supports Kaggle API Token (`KGAT_...`) or standard API Key.
- Remembers credentials in secure browser cookies so you don't need to re-enter them across sessions.
- Automatically creates and manages private datasets on Kaggle.
