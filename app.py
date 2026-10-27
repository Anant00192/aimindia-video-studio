import os
import sys
import json
import shutil
import time
import subprocess
import tempfile
from pathlib import Path
import gradio as gr

# Support Hugging Face ZeroGPU if available
try:
    import spaces
    zero_gpu_decorator = spaces.GPU
except ImportError:
    def zero_gpu_decorator(func):
        return func

# Force IPv4
try:
    import socket
    import urllib3.util.connection as urllib_conn
    def _force_ipv4():
        return socket.AF_INET
    urllib_conn.allowed_gai_family = _force_ipv4
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DEFAULT_LOGO_PATH = STATIC_DIR / "default_logo.png"
NOTEBOOK_DIR = BASE_DIR / "notebook"
MASTER_NOTEBOOK_PATH = NOTEBOOK_DIR / "aimindia-video-notebook.ipynb"

DEFAULT_KAGGLE_USERNAME = "rathinnew"
DEFAULT_KAGGLE_KEY = "KGAT_a499e6bc646fe872f73e80d6481b4778"

def get_video_dims(video_path):
    cmd = f"ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x '{video_path}'"
    out = subprocess.check_output(cmd, shell=True).decode('utf-8').strip()
    w, h = out.split('x')
    return int(w), int(h)

def build_filter(w, h, zoom_pct, logo_in, logo_width, x_offset, y_offset):
    crop_w = int(w * (1 - zoom_pct / 100))
    crop_h = int(h * (1 - zoom_pct / 100))
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2

    has_logo = bool(logo_in and os.path.exists(str(logo_in)))
    if has_logo:
        return (
            f"[0:v]crop={crop_w}:{crop_h}:0:0,scale={w}:{h}:flags=lanczos,"
            f"unsharp=5:5:0.6:5:5:0.0[base];"
            f"[1:v]format=rgba,scale={logo_width}:-1[logo];"
            f"[base][logo]overlay=W-w-{x_offset}:H-h-{y_offset}:format=auto"
        )
    else:
        return f"crop={crop_w}:{crop_h}:0:0,scale={w}:{h}:flags=lanczos,unsharp=5:5:0.6:5:5:0.0"

@zero_gpu_decorator
def preview_position(video_in, logo_in, zoom_pct, logo_width, x_offset, y_offset):
    if not video_in:
        return None, "❌ Please upload a video first."

    active_logo = logo_in if (logo_in and os.path.exists(str(logo_in))) else (str(DEFAULT_LOGO_PATH) if DEFAULT_LOGO_PATH.exists() else None)

    try:
        w, h = get_video_dims(video_in)
        temp_dir = tempfile.mkdtemp()
        preview_path = os.path.join(temp_dir, "preview.png")

        filter_str = build_filter(w, h, zoom_pct, active_logo, logo_width, x_offset, y_offset)
        if active_logo and os.path.exists(active_logo):
            cmd = f"ffmpeg -ss 1 -i '{video_in}' -i '{active_logo}' -frames:v 1 -filter_complex '{filter_str}' '{preview_path}' -y"
        else:
            cmd = f"ffmpeg -ss 1 -i '{video_in}' -frames:v 1 -vf '{filter_str}' '{preview_path}' -y"

        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return preview_path, "✅ Fast Preview Generated! Inspect watermark cropping and logo placement below."
    except Exception as e:
        return None, f"❌ Preview error: {str(e)}"

def process_on_kaggle(video_in, logo_in, trim_sec, zoom_pct, logo_width, x_offset, y_offset, kaggle_user, kaggle_key, progress=gr.Progress()):
    if not video_in:
        yield None, None, "❌ Please upload a video first."
        return

    username = (kaggle_user or "").strip() or DEFAULT_KAGGLE_USERNAME
    key = (kaggle_key or "").strip() or DEFAULT_KAGGLE_KEY

    yield None, None, f"⏳ [1/5] Authenticating Kaggle account @{username}..."
    progress(0.1, desc="Authenticating Kaggle API...")

    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key
    if key and (str(key).startswith("KGAT_") or len(str(key)) > 32):
        os.environ["KAGGLE_API_TOKEN"] = str(key)
    else:
        os.environ.pop("KAGGLE_API_TOKEN", None)

    try:
        k_dir = Path.home() / ".kaggle"
        k_dir.mkdir(parents=True, exist_ok=True)
        with open(k_dir / "kaggle.json", "w") as f:
            json.dump({"username": username, "key": key}, f)
        os.chmod(k_dir / "kaggle.json", 0o600)
    except Exception:
        pass

    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    try:
        api.authenticate()
        if hasattr(api, 'CONFIG_NAME_TOKEN') and key and (str(key).startswith("KGAT_") or len(str(key)) > 32):
            api.config_values[api.CONFIG_NAME_TOKEN] = str(key)
    except Exception as ae:
        yield None, None, f"❌ Kaggle authentication failed: {ae}"
        return

    temp_dir = tempfile.mkdtemp()
    ds_dir = Path(temp_dir) / "dataset"
    (ds_dir / "videos").mkdir(parents=True, exist_ok=True)
    (ds_dir / "logos").mkdir(parents=True, exist_ok=True)

    vid_path = Path(video_in)
    shutil.copy2(vid_path, ds_dir / "videos" / vid_path.name)

    active_logo = logo_in if (logo_in and os.path.exists(str(logo_in))) else (str(DEFAULT_LOGO_PATH) if DEFAULT_LOGO_PATH.exists() else None)
    if active_logo and os.path.exists(active_logo):
        shutil.copy2(active_logo, ds_dir / "logos" / f"logo{Path(active_logo).suffix}")

    cfg = {
        "trim_sec": float(trim_sec),
        "zoom_pct": int(zoom_pct),
        "logo_width": int(logo_width),
        "x_offset": int(x_offset),
        "y_offset": int(y_offset)
    }
    with open(ds_dir / "config.json", "w") as f:
        json.dump(cfg, f, indent=2)

    dataset_slug = "aimindia-video-dataset"
    kernel_slug = "aimindia-video-cleaner"

    with open(ds_dir / "dataset-metadata.json", "w") as f:
        json.dump({
            "title": "AimIndia Video Processing Dataset",
            "id": f"{username}/{dataset_slug}",
            "licenses": [{"name": "CC0-1.0"}]
        }, f, indent=2)

    yield None, None, f"☁️ [2/5] Uploading dataset '{username}/{dataset_slug}' to Kaggle Cloud..."
    progress(0.25, desc="Syncing dataset to Kaggle Cloud...")

    exists = False
    cur_ver = 0
    try:
        existing = api.dataset_list(user=username, search=dataset_slug)
        for d in (existing or []):
            if getattr(d, 'ref', '') == f"{username}/{dataset_slug}":
                exists = True
                break
        if exists:
            st_info = json.loads(api.dataset_status(f"{username}/{dataset_slug}", format="json"))
            cur_ver = int(st_info.get("current_version_number", 0))
    except Exception:
        pass

    if exists:
        api.dataset_create_version(str(ds_dir), version_notes=f"Run {int(time.time())}", dir_mode="zip")
    else:
        api.dataset_create_new(str(ds_dir), public=False, dir_mode="zip")

    target_ver = cur_ver + 1 if exists else 1
    yield None, None, f"⏳ Waiting for Kaggle to index dataset (targeting v{target_ver})..."
    progress(0.4, desc="Waiting for dataset indexing...")

    for _ in range(60):
        try:
            st_data = json.loads(api.dataset_status(f"{username}/{dataset_slug}", format="json"))
            v_num = int(st_data.get("current_version_number", 0))
            st_val = str(st_data.get("status", "")).lower()
            if v_num >= target_ver and "ready" in st_val:
                break
        except Exception:
            pass
        time.sleep(3)

    yield None, None, f"🚀 [3/5] Launching GPU Kernel '{username}/{kernel_slug}' on Kaggle Cloud..."
    progress(0.55, desc="Launching Kaggle GPU kernel...")

    kernel_dir = Path(temp_dir) / "kernel"
    kernel_dir.mkdir(parents=True, exist_ok=True)

    with open(MASTER_NOTEBOOK_PATH) as f:
        nb = json.load(f)

    for cell in nb.get("cells", []):
        if cell.get("cell_type") == "code":
            src = "".join(cell.get("source", []))
            if "RUN_MODE =" in src:
                cell["source"] = [
                    "RUN_MODE = 'batch'\n",
                    "print(f'⚙️ Injected Mode: {RUN_MODE}')\n"
                ]
                break

    with open(kernel_dir / "aimindia-video-notebook.ipynb", "w") as f:
        json.dump(nb, f, indent=1)

    k_meta = {
        "id": f"{username}/{kernel_slug}",
        "title": "AimIndia Video Cleaner",
        "code_file": "aimindia-video-notebook.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": "true",
        "enable_gpu": "true",
        "enable_tpu": "false",
        "enable_internet": "true",
        "dataset_sources": [f"{username}/{dataset_slug}"],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": []
    }
    with open(kernel_dir / "kernel-metadata.json", "w") as f:
        json.dump(k_meta, f, indent=2)

    # Cancel or wait if a previous kernel run is still active
    try:
        prev_st = api.kernels_status(f"{username}/{kernel_slug}")
        prev_val = str(prev_st.get("status", "")).lower() if isinstance(prev_st, dict) else str(getattr(prev_st, "status", "")).lower()
        if "running" in prev_val or "queued" in prev_val:
            yield None, None, f"⏳ A previous run is {prev_val.upper()} on Kaggle GPU. Canceling old run..."
            try:
                api.kernels_cancel(f"{username}/{kernel_slug}")
                time.sleep(5)
            except Exception:
                pass
    except Exception:
        pass

    try:
        api.kernels_push(str(kernel_dir))
    except Exception as pe:
        detail = ""
        if hasattr(pe, "response") and hasattr(pe.response, "text"):
            detail = f" (Details: {pe.response.text})"
        yield None, None, f"❌ Failed to submit kernel to Kaggle: {pe}{detail}"
        return

    yield None, None, "⚡ [4/5] Kernel submitted! Kaggle Tesla T4 GPU is processing your video with NVENC hardware acceleration..."
    progress(0.7, desc="Processing on Kaggle GPU...")

    poll_count = 0
    out_dir = Path(temp_dir) / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    while True:
        time.sleep(8)
        poll_count += 1
        st = api.kernels_status(f"{username}/{kernel_slug}")
        if isinstance(st, dict):
            curr_st = str(st.get("status", "")).lower()
            fail_msg = st.get("failureMessage", "")
        else:
            curr_st = str(getattr(st, "status", "")).lower()
            fail_msg = getattr(st, "failure_message", getattr(st, "failureMessage", ""))

        yield None, None, f"⚡ [4/5] Kaggle GPU Status: {curr_st.upper()} (check #{poll_count})"

        if "complete" in curr_st:
            yield None, None, "📥 [5/5] Processing complete! Downloading clean video output..."
            progress(0.9, desc="Downloading clean video...")
            api.kernels_output(f"{username}/{kernel_slug}", path=str(out_dir))

            cand_files = list(out_dir.glob("FINAL_VIDEO_CLEAN.mp4")) + list(out_dir.glob("*.mp4")) + list(out_dir.glob("*.zip"))
            if cand_files:
                final_out = cand_files[0]
                yield str(final_out), str(final_out), f"🎉 SUCCESS! Processed cleanly on Kaggle GPU: {final_out.name}"
                progress(1.0, desc="Done!")
                return
            else:
                yield None, None, "⚠️ Kernel completed but no video file was returned."
                return
        elif "error" in curr_st or "failed" in curr_st or "cancel" in curr_st:
            log_detail = ""
            try:
                logs = api.kernels_logs(f"{username}/{kernel_slug}")
                if logs:
                    lines = [l.strip() for l in logs.split('\n') if l.strip()]
                    log_detail = " | Last log: " + " ".join(lines[-3:])
            except Exception:
                pass
            yield None, None, f"❌ Kaggle run failed ({curr_st}): {fail_msg or ''}{log_detail}"
            return

with gr.Blocks(title="AimIndia Video Studio") as app:
    gr.Markdown("# 🎬 AimIndia Video Studio")
    gr.Markdown("**Kaggle GPU Cloud Orchestrator for Watermark Removal, Outro Trimming & Logo Overlay**")

    with gr.Accordion("⚙️ Kaggle Account Credentials", open=False):
        gr.Markdown("All processing runs on Kaggle's free Tesla T4 GPU.")
        with gr.Row():
            k_user = gr.Textbox(label="Kaggle Username", value=DEFAULT_KAGGLE_USERNAME, placeholder="e.g. rathinnew")
            k_key = gr.Textbox(label="Kaggle API Key (KGAT_...)", value=DEFAULT_KAGGLE_KEY, type="password", placeholder="Paste API Token")

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. Upload Video & Logo")
            v_in = gr.Video(label="📹 Raw NotebookLM / Source Video")
            logo_in = gr.Image(
                value=str(DEFAULT_LOGO_PATH) if DEFAULT_LOGO_PATH.exists() else None,
                type="filepath",
                image_mode="RGBA",
                label="🖼️ Brand Logo (Preloaded with AimIndia Transparent Logo)"
            )

            gr.Markdown("### 2. Fine-Tuning Controls")
            trim_slider = gr.Slider(minimum=0.0, maximum=10.0, value=3.0, step=0.1, label="✂️ Trim Outro Seconds (Cuts Gemini Ending)")
            zoom_slider = gr.Slider(minimum=0, maximum=20, value=6, step=1, label="🔍 Zoom to Crop Watermark Corner (%)")
            width_slider = gr.Slider(minimum=50, maximum=800, value=180, step=10, label="📐 Logo Width (Pixels)")
            x_offset_slider = gr.Slider(minimum=-100, maximum=600, value=20, step=5, label="➡️ Logo X Offset (from Right)")
            y_offset_slider = gr.Slider(minimum=-100, maximum=600, value=20, step=5, label="⬆️ Logo Y Offset (from Bottom)")

            with gr.Row():
                preview_btn = gr.Button("👁️ Fast 1-Frame Preview", variant="secondary")
                btn = gr.Button("🚀 Process on Kaggle GPU", variant="primary")

        with gr.Column(scale=1):
            gr.Markdown("### 3. Preview & Output")
            preview_img = gr.Image(label="📍 Fast Position Preview")
            v_out = gr.Video(label="🎬 Final Clean Video")
            f_out = gr.File(label="📥 Download Processed Video File")
            status = gr.Textbox(label="Status & Cloud Log", lines=3)

    preview_btn.click(
        preview_position,
        inputs=[v_in, logo_in, zoom_slider, width_slider, x_offset_slider, y_offset_slider],
        outputs=[preview_img, status],
        api_name=False
    )

    btn.click(
        process_on_kaggle,
        inputs=[v_in, logo_in, trim_slider, zoom_slider, width_slider, x_offset_slider, y_offset_slider, k_user, k_key],
        outputs=[v_out, f_out, status],
        api_name=False
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
