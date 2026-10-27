---
title: AimIndia Video Studio
emoji: 🎬
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

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
   Visit `http://localhost:7860`

---

## ☁️ Cloud Deployment on Hugging Face Spaces (100% Free)

1. Go to [Hugging Face New Space](https://huggingface.co/new-space).
2. Select **Gradio** as Space SDK.
3. Choose **CPU basic (Free)**.
4. Connect this GitHub repository: `Anant00192/aimindia-video-studio`.
