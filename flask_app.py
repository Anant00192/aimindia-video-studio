import os
import sys
import json
import shutil
import glob
import re
import threading
import time
import subprocess
import tempfile
from pathlib import Path

# Force IPv4 to prevent hanging on misconfigured IPv6 routes for Google APIs
try:
    import socket
    import urllib3.util.connection as urllib_conn
    def _force_ipv4():
        return socket.AF_INET
    urllib_conn.allowed_gai_family = _force_ipv4
except Exception:
    pass

# Ensure user site-packages are accessible
user_site = os.path.expanduser('~/.local/lib/python3.13/site-packages')
if os.path.exists(user_site) and user_site not in sys.path:
    sys.path.insert(0, user_site)

from flask import Flask, render_template, request, jsonify, send_file, make_response
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 * 1024  # 50GB max
app.secret_key = 'aimindia-video-studio-secret-key'

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
VIDEOS_DIR = UPLOADS_DIR / "videos"
LOGOS_DIR = UPLOADS_DIR / "logos"
STAGING_DIR = BASE_DIR / "staging"
OUTPUT_DIR = BASE_DIR / "output"
NOTEBOOK_DIR = BASE_DIR / "notebook"
STATIC_DIR = BASE_DIR / "static"
DEFAULT_LOGO_PATH = STATIC_DIR / "default_logo.png"

for p in [VIDEOS_DIR, LOGOS_DIR, STAGING_DIR / "dataset", STAGING_DIR / "kernel", OUTPUT_DIR]:
    p.mkdir(parents=True, exist_ok=True)

app_state = {
    "status": "idle",       # idle, syncing, pushing, running, complete, error
    "message": "Ready to upload video and process on Kaggle GPU.",
    "progress": 0,
    "last_kernel_status": None,
    "logs": [],
    "output_file": None,
}

# Auto-detect existing output
for cand in ["FINAL_VIDEO_CLEAN.mp4", "all_final_videos.zip"]:
    cand_path = OUTPUT_DIR / cand
    if cand_path.exists():
        app_state["status"] = "complete"
        app_state["progress"] = 100
        app_state["message"] = f"Processed video ready: {cand}"
        app_state["output_file"] = cand
        sz = cand_path.stat().st_size / (1024 * 1024)
        app_state["logs"].append(f"[{time.strftime('%H:%M:%S')}] Output archive ready: {cand} ({sz:.2f} MB)")
        break

def log(msg):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {msg}"
    print(entry)
    app_state["logs"].append(entry)
    if len(app_state["logs"]) > 200:
        app_state["logs"].pop(0)

DEFAULT_KAGGLE_USERNAME = "rathinnew"
DEFAULT_KAGGLE_KEY = "KGAT_10cab40726cd143c3e7d52696187fb7a"

def load_stored_credentials():
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_json = kaggle_dir / "kaggle.json"
    u = None
    k = None
    if kaggle_json.exists():
        try:
            with open(kaggle_json) as f:
                data = json.load(f)
            u = data.get("username", "").strip()
            k = data.get("key", "").strip()
        except Exception:
            pass

    if not u or not k:
        u = DEFAULT_KAGGLE_USERNAME
        k = DEFAULT_KAGGLE_KEY
        try:
            kaggle_dir.mkdir(parents=True, exist_ok=True)
            with open(kaggle_json, "w") as f:
                json.dump({"username": u, "key": k}, f)
            os.chmod(kaggle_json, 0o600)
        except Exception:
            pass

    os.environ["KAGGLE_USERNAME"] = u
    os.environ["KAGGLE_KEY"] = k
    if k and (str(k).startswith("KGAT_") or len(str(k)) > 32):
        os.environ["KAGGLE_API_TOKEN"] = str(k)
    else:
        os.environ.pop("KAGGLE_API_TOKEN", None)
    return {"configured": True, "username": u, "key": k, "is_default": (u == DEFAULT_KAGGLE_USERNAME)}

def get_request_credentials(req=None):
    if req is None:
        from flask import request as req

    if req and req.is_json:
        data = req.get_json(silent=True) or {}
        u = data.get("kaggle_username") or data.get("username")
        k = data.get("kaggle_key") or data.get("key")
        if u and k:
            return str(u).strip(), str(k).strip()

    if req and req.headers:
        u = req.headers.get("X-Kaggle-Username")
        k = req.headers.get("X-Kaggle-Key")
        if u and k:
            return str(u).strip(), str(k).strip()

    if req and req.cookies:
        u = req.cookies.get("kaggle_username")
        k = req.cookies.get("kaggle_key")
        if u and k:
            return str(u).strip(), str(k).strip()

    return None, None

def get_kaggle_api(username=None, key=None):
    from kaggle.api.kaggle_api_extended import KaggleApi
    if not username or not key:
        username, key = get_request_credentials()

    if not username or not key:
        stored = load_stored_credentials()
        username = stored.get("username", DEFAULT_KAGGLE_USERNAME)
        key = stored.get("key", DEFAULT_KAGGLE_KEY)

    os.environ["KAGGLE_USERNAME"] = username
    os.environ["KAGGLE_KEY"] = key
    if key and (str(key).startswith("KGAT_") or len(str(key)) > 32):
        os.environ["KAGGLE_API_TOKEN"] = str(key)
    else:
        os.environ.pop("KAGGLE_API_TOKEN", None)

    api = KaggleApi()
    api.authenticate()
    if key and (str(key).startswith("KGAT_") or len(str(key)) > 32):
        api.config_values[api.CONFIG_NAME_TOKEN] = str(key)
    return api

# ==========================================
# Routes: Web & Credentials
# ==========================================

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/credentials", methods=["GET", "POST"])
def credentials():
    if request.method == "GET":
        u, k = get_request_credentials()
        if not u or not k:
            stored = load_stored_credentials()
            u = stored.get("username")
            k = stored.get("key")

        if u and k:
            preview = f"••••••••{k[-4:]}" if len(k) >= 8 else "••••••••"
            return jsonify({
                "configured": True,
                "username": u,
                "key_preview": preview,
                "is_default": (u == DEFAULT_KAGGLE_USERNAME)
            })
        return jsonify({"configured": False, "username": None, "key_preview": None, "is_default": False})

    data = request.get_json() or {}
    username = data.get("username", "").strip()
    key = data.get("key", "").strip()

    if not username or not key:
        return jsonify({"success": False, "error": "Both Username and API Key are required."}), 400

    try:
        api = get_kaggle_api(username, key)
        auth_method = str(api.get_config_value(api.CONFIG_NAME_AUTH_METHOD) or "")
        if auth_method == "ANONYMOUS":
            raise RuntimeError("Invalid credentials — Kaggle rejected the API token.")

        log(f"Verified & authenticated Kaggle account: @{username}")
        resp = make_response(jsonify({"success": True, "username": username, "key": key}))
        resp.set_cookie("kaggle_username", username, max_age=31536000, samesite="Lax", path="/")
        resp.set_cookie("kaggle_key", key, max_age=31536000, samesite="Lax", path="/")
        return resp
    except Exception as e:
        log(f"Kaggle authentication failed for @{username}: {e}")
        return jsonify({"success": False, "error": f"Authentication failed: {str(e)}"}), 400

@app.route("/api/reset_credentials", methods=["POST"])
def reset_credentials():
    kaggle_dir = Path.home() / ".kaggle"
    kaggle_dir.mkdir(parents=True, exist_ok=True)
    kaggle_json = kaggle_dir / "kaggle.json"
    try:
        with open(kaggle_json, "w") as f:
            json.dump({"username": DEFAULT_KAGGLE_USERNAME, "key": DEFAULT_KAGGLE_KEY}, f)
        os.chmod(kaggle_json, 0o600)
    except Exception:
        pass
    os.environ["KAGGLE_USERNAME"] = DEFAULT_KAGGLE_USERNAME
    os.environ["KAGGLE_KEY"] = DEFAULT_KAGGLE_KEY
    os.environ["KAGGLE_API_TOKEN"] = DEFAULT_KAGGLE_KEY
    log(f"Reset Kaggle credentials to default: @{DEFAULT_KAGGLE_USERNAME}")

    resp = make_response(jsonify({"success": True, "username": DEFAULT_KAGGLE_USERNAME, "key": DEFAULT_KAGGLE_KEY}))
    resp.set_cookie("kaggle_username", DEFAULT_KAGGLE_USERNAME, max_age=31536000, samesite="Lax", path="/")
    resp.set_cookie("kaggle_key", DEFAULT_KAGGLE_KEY, max_age=31536000, samesite="Lax", path="/")
    return resp

# ==========================================
# Routes: Media & File Management
# ==========================================

ALLOWED_VIDEOS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ALLOWED_LOGOS = {".png", ".webp", ".jpg", ".jpeg"}

@app.route("/api/state", methods=["GET"])
def get_state():
    # List uploaded videos
    videos = []
    for f in sorted(VIDEOS_DIR.iterdir()):
        if f.is_file() and not f.name.endswith(".meta.json") and f.suffix.lower() in ALLOWED_VIDEOS:
            meta_file = VIDEOS_DIR / f"{f.stem}.meta.json"
            orig_name = f.name
            if meta_file.exists():
                try:
                    with open(meta_file) as mf:
                        orig_name = json.load(mf).get("original_name", f.name)
                except Exception:
                    pass
            videos.append({
                "filename": f.name,
                "original_name": orig_name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2)
            })

    # Active logo
    custom_logos = [f for f in LOGOS_DIR.iterdir() if f.is_file() and not f.name.endswith(".meta.json") and f.suffix.lower() in ALLOWED_LOGOS]
    if custom_logos:
        active_logo = {
            "type": "custom",
            "filename": custom_logos[0].name,
            "url": f"/api/get_logo?v={int(time.time())}",
            "size_kb": round(custom_logos[0].stat().st_size / 1024, 1)
        }
    else:
        active_logo = {
            "type": "default",
            "filename": "AimIndia Transparent Logo (Bundled)",
            "url": "/static/default_logo.png",
            "size_kb": round(DEFAULT_LOGO_PATH.stat().st_size / 1024, 1) if DEFAULT_LOGO_PATH.exists() else 0
        }

    req_u, req_k = get_request_credentials()
    if not req_u or not req_k:
        stored = load_stored_credentials()
        req_u = stored.get("username")
        req_k = stored.get("key")

    has_creds = bool(req_u and req_k)
    k_preview = f"••••••••{req_k[-4:]}" if (has_creds and len(req_k) >= 8) else ("••••••••" if has_creds else None)

    return jsonify({
        "credentials": {
            "configured": has_creds,
            "username": req_u if has_creds else None,
            "key_preview": k_preview,
            "is_default": (req_u == DEFAULT_KAGGLE_USERNAME) if has_creds else False
        },
        "videos": videos,
        "logo": active_logo,
        "app_state": {
            "status": app_state["status"],
            "message": app_state["message"],
            "progress": app_state["progress"],
            "kernel_status": app_state["last_kernel_status"],
            "output_available": (OUTPUT_DIR / "FINAL_VIDEO_CLEAN.mp4").exists() or (OUTPUT_DIR / "all_final_videos.zip").exists(),
            "output_file": app_state["output_file"]
        }
    })

@app.route("/api/upload_video", methods=["POST"])
def upload_video():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    orig_filename = secure_filename(file.filename)
    ext = os.path.splitext(orig_filename)[1].lower()
    if ext not in ALLOWED_VIDEOS:
        return jsonify({"success": False, "error": f"Invalid video extension '{ext}'"}), 400

    dest_filename = f"{int(time.time())}_{orig_filename}"
    dest = VIDEOS_DIR / dest_filename
    file.save(dest)

    meta_file = VIDEOS_DIR / f"{dest.stem}.meta.json"
    with open(meta_file, "w") as mf:
        json.dump({"original_name": orig_filename}, mf)

    log(f"Uploaded Video: {orig_filename} ({dest.stat().st_size / (1024*1024):.2f} MB)")
    return jsonify({
        "success": True,
        "filename": dest_filename,
        "original_name": orig_filename,
        "size_mb": round(dest.stat().st_size / (1024*1024), 2)
    })

@app.route("/api/delete_video/<filename>", methods=["DELETE"])
def delete_video(filename):
    safe_name = secure_filename(filename)
    target = VIDEOS_DIR / safe_name
    if target.exists():
        target.unlink()
        meta = VIDEOS_DIR / f"{target.stem}.meta.json"
        if meta.exists():
            meta.unlink()
        log(f"Removed Video: {safe_name}")
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "File not found"}), 404

@app.route("/api/upload_logo", methods=["POST"])
def upload_logo():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"}), 400
    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "error": "Empty filename"}), 400

    orig_filename = secure_filename(file.filename)
    ext = os.path.splitext(orig_filename)[1].lower()
    if ext not in ALLOWED_LOGOS:
        return jsonify({"success": False, "error": f"Invalid logo extension '{ext}'"}), 400

    # Clean existing custom logo
    for f in LOGOS_DIR.iterdir():
        f.unlink()

    dest = LOGOS_DIR / f"custom_logo{ext}"
    file.save(dest)

    log(f"Uploaded Custom Logo: {orig_filename} ({dest.stat().st_size / 1024:.1f} KB)")
    return jsonify({"success": True, "filename": dest.name})

@app.route("/api/delete_logo", methods=["DELETE"])
def delete_logo():
    for f in LOGOS_DIR.iterdir():
        f.unlink()
    log("Switched back to Bundled AimIndia Logo")
    return jsonify({"success": True})

@app.route("/api/get_logo", methods=["GET"])
def get_logo():
    custom_logos = [f for f in LOGOS_DIR.iterdir() if f.is_file() and not f.name.endswith(".meta.json")]
    if custom_logos:
        return send_file(custom_logos[0])
    if DEFAULT_LOGO_PATH.exists():
        return send_file(DEFAULT_LOGO_PATH)
    return "No logo found", 404

# ==========================================
# Route: Fast Position Preview
# ==========================================

def get_active_logo_path():
    custom_logos = [f for f in LOGOS_DIR.iterdir() if f.is_file() and not f.name.endswith(".meta.json")]
    if custom_logos:
        return custom_logos[0]
    if DEFAULT_LOGO_PATH.exists():
        return DEFAULT_LOGO_PATH
    return None

@app.route("/api/preview", methods=["POST"])
def preview():
    videos = [f for f in sorted(VIDEOS_DIR.iterdir()) if f.is_file() and not f.name.endswith(".meta.json") and f.suffix.lower() in ALLOWED_VIDEOS]
    if not videos:
        return jsonify({"success": False, "error": "Upload a video first before previewing."}), 400

    video_in = videos[0]
    data = request.get_json() or {}
    zoom_pct = int(data.get("zoom_pct", 6))
    logo_width = int(data.get("logo_width", 180))
    x_offset = int(data.get("x_offset", 20))
    y_offset = int(data.get("y_offset", 20))

    logo_path = get_active_logo_path()

    try:
        # Get video dimensions
        cmd_dim = f"ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x '{video_in}'"
        dim_out = subprocess.check_output(cmd_dim, shell=True).decode('utf-8').strip()
        w, h = [int(v) for v in dim_out.split('x')]

        crop_w = int(w * (1 - zoom_pct / 100))
        crop_h = int(h * (1 - zoom_pct / 100))
        crop_w -= crop_w % 2
        crop_h -= crop_h % 2

        preview_out = STATIC_DIR / "preview.png"

        if logo_path and logo_path.exists():
            filter_str = (
                f"[0:v]crop={crop_w}:{crop_h}:0:0,scale={w}:{h}:flags=lanczos,"
                f"unsharp=5:5:0.6:5:5:0.0[base];"
                f"[1:v]format=rgba,scale={logo_width}:-1[logo];"
                f"[base][logo]overlay=W-w-{x_offset}:H-h-{y_offset}:format=auto"
            )
            cmd = f"ffmpeg -ss 1 -i '{video_in}' -i '{logo_path}' -frames:v 1 -filter_complex '{filter_str}' '{preview_out}' -y"
        else:
            filter_str = f"crop={crop_w}:{crop_h}:0:0,scale={w}:{h}:flags=lanczos,unsharp=5:5:0.6:5:5:0.0"
            cmd = f"ffmpeg -ss 1 -i '{video_in}' -frames:v 1 -vf '{filter_str}' '{preview_out}' -y"

        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return jsonify({
            "success": True,
            "preview_url": f"/static/preview.png?v={int(time.time()*1000)}",
            "message": "Preview generated successfully."
        })
    except Exception as e:
        log(f"Preview generation failed: {e}")
        return jsonify({"success": False, "error": f"Preview failed: {str(e)}"}), 500

# ==========================================
# Route: Launch Kaggle Pipeline
# ==========================================

def run_kaggle_pipeline(config):
    username = config["kaggle_username"]
    key = config["kaggle_key"]
    trim_sec = float(config.get("trim_sec", 3.0))
    zoom_pct = int(config.get("zoom_pct", 6))
    logo_width = int(config.get("logo_width", 180))
    x_offset = int(config.get("x_offset", 20))
    y_offset = int(config.get("y_offset", 20))

    dataset_slug = "aimindia-video-dataset"
    kernel_slug = "aimindia-video-cleaner"

    try:
        app_state["status"] = "syncing"
        app_state["progress"] = 10
        app_state["message"] = "Preparing assets and syncing to Kaggle Cloud..."
        log("=== Starting AimIndia Video Studio Pipeline ===")
        log(f"Target Kaggle Account: @{username}")

        api = get_kaggle_api(username, key)

        # 1. Package Dataset
        ds_dir = STAGING_DIR / "dataset"
        if ds_dir.exists():
            shutil.rmtree(ds_dir)
        (ds_dir / "videos").mkdir(parents=True, exist_ok=True)
        (ds_dir / "logos").mkdir(parents=True, exist_ok=True)

        videos = [f for f in sorted(VIDEOS_DIR.iterdir()) if f.is_file() and not f.name.endswith(".meta.json") and f.suffix.lower() in ALLOWED_VIDEOS]
        if not videos:
            raise RuntimeError("No videos found! Please upload at least one video.")

        for v in videos:
            shutil.copy2(v, ds_dir / "videos" / v.name)
            log(f"Packaged Video: {v.name}")

        logo_path = get_active_logo_path()
        if logo_path and logo_path.exists():
            shutil.copy2(logo_path, ds_dir / "logos" / f"logo{logo_path.suffix}")
            log(f"Packaged Logo: {logo_path.name}")

        # Config JSON
        pipeline_cfg = {
            "trim_sec": trim_sec,
            "zoom_pct": zoom_pct,
            "logo_width": logo_width,
            "x_offset": x_offset,
            "y_offset": y_offset
        }
        with open(ds_dir / "config.json", "w") as f:
            json.dump(pipeline_cfg, f, indent=2)

        meta_path = ds_dir / "dataset-metadata.json"
        ds_metadata = {
            "title": "AimIndia Video Processing Dataset",
            "id": f"{username}/{dataset_slug}",
            "licenses": [{"name": "CC0-1.0"}]
        }
        with open(meta_path, "w") as f:
            json.dump(ds_metadata, f, indent=2)

        app_state["progress"] = 30
        app_state["message"] = "Uploading dataset to Kaggle Cloud..."
        log(f"Syncing dataset '{username}/{dataset_slug}'...")

        exists = False
        current_ver = 0
        try:
            existing = api.dataset_list(user=username, search=dataset_slug)
            for d in (existing or []):
                if getattr(d, 'ref', '') == f"{username}/{dataset_slug}":
                    exists = True
                    break
            if exists:
                try:
                    st_info = json.loads(api.dataset_status(f"{username}/{dataset_slug}", format="json"))
                    current_ver = int(st_info.get("current_version_number", 0))
                except Exception:
                    current_ver = 0
        except Exception as e:
            log(f"Dataset lookup notice: {e}")

        if exists:
            log(f"Dataset exists (Version {current_ver}). Creating new version...")
            res = api.dataset_create_version(str(ds_dir), version_notes=f"Run {time.strftime('%Y-%m-%d %H:%M')}", dir_mode="zip")
            log(f"Dataset version created: {res}")
        else:
            log(f"Creating new private dataset '{dataset_slug}'...")
            res = api.dataset_create_new(str(ds_dir), public=False, dir_mode="zip")
            log(f"Dataset created: {res}")

        target_ver = current_ver + 1 if exists else 1
        app_state["message"] = f"Waiting for Kaggle to index dataset (v{target_ver})..."

        # Wait for dataset to be READY
        for attempt in range(60):
            try:
                st_json = api.dataset_status(f"{username}/{dataset_slug}", format="json")
                st_data = json.loads(st_json) if isinstance(st_json, str) else {}
                st_val = str(st_data.get("status", "")).lower()
                v_num = int(st_data.get("current_version_number", 0))
                if v_num >= target_ver and "ready" in st_val:
                    log(f"✅ Dataset Version {v_num} is READY on Kaggle!")
                    break
            except Exception:
                pass
            time.sleep(3)

        # 2. Prepare & Push Kernel
        app_state["progress"] = 60
        app_state["status"] = "pushing"
        app_state["message"] = "Preparing & launching Kaggle GPU Kernel..."
        log("=== Preparing Kernel for Background Execution ===")

        kernel_dir = STAGING_DIR / "kernel"
        if kernel_dir.exists():
            shutil.rmtree(kernel_dir)
        kernel_dir.mkdir(parents=True, exist_ok=True)

        nb_path = NOTEBOOK_DIR / "aimindia-video-notebook.ipynb"
        with open(nb_path) as f:
            nb = json.load(f)

        # Inject batch mode
        for cell in nb.get("cells", []):
            if cell.get("cell_type") == "code":
                src = "".join(cell.get("source", []))
                if "RUN_MODE =" in src:
                    cell["source"] = [
                        "# 2. Mode Configuration Switch (Auto-set by AimIndia Video Studio)\n",
                        "RUN_MODE = 'batch'\n",
                        "print(f'⚙️ Injected Mode: {RUN_MODE}')\n"
                    ]
                    break

        target_nb = kernel_dir / "aimindia-video-notebook.ipynb"
        with open(target_nb, "w") as f:
            json.dump(nb, f, indent=1)

        k_meta = {
            "id": f"{username}/{kernel_slug}",
            "title": "AimIndia Video Watermark Remover and Logo Overlay",
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

        log(f"Pushing GPU kernel '{username}/{kernel_slug}'...")
        push_res = api.kernels_push(str(kernel_dir))
        log(f"Kernel push response: {push_res}")

        app_state["progress"] = 70
        app_state["status"] = "running"
        app_state["message"] = "Submitted! Kaggle GPU is now processing your video..."

        # 3. Monitor Kernel Status
        poll_count = 0
        while True:
            time.sleep(8)
            poll_count += 1
            try:
                st = api.kernels_status(f"{username}/{kernel_slug}")
                curr_st = str(st.get("status", "")).lower() if isinstance(st, dict) else str(getattr(st, "status", "")).lower()
                app_state["last_kernel_status"] = curr_st
                
                if poll_count % 3 == 0:
                    log(f"Kaggle GPU Kernel Status: {curr_st.upper()} (check #{poll_count})")

                if "complete" in curr_st:
                    log("🎉 Kaggle GPU processing COMPLETE! Pulling output...")
                    app_state["progress"] = 90
                    app_state["message"] = "Downloading clean video output from Kaggle..."
                    
                    # Pull output
                    api.kernels_output(f"{username}/{kernel_slug}", path=str(OUTPUT_DIR))
                    
                    out_cand = None
                    for cand in ["FINAL_VIDEO_CLEAN.mp4", "all_final_videos.zip"]:
                        if (OUTPUT_DIR / cand).exists():
                            out_cand = cand
                            break
                    if not out_cand:
                        files = list(OUTPUT_DIR.glob("*.mp4")) + list(OUTPUT_DIR.glob("*.zip"))
                        if files:
                            out_cand = files[0].name

                    if out_cand:
                        app_state["output_file"] = out_cand
                        app_state["status"] = "complete"
                        app_state["progress"] = 100
                        app_state["message"] = f"Finished! Clean video ready: {out_cand}"
                        log(f"✅ Success! Output ready for download: {out_cand}")
                    else:
                        app_state["status"] = "complete"
                        app_state["progress"] = 100
                        app_state["message"] = "Kaggle execution finished successfully."
                        log("✅ Kernel completed execution.")
                    break

                elif "error" in curr_st or "failed" in curr_st or "cancel" in curr_st:
                    raise RuntimeError(f"Kaggle kernel exited with status '{curr_st}'. Check Kaggle kernel logs.")

            except Exception as pe:
                if "error" in str(pe).lower() or "failed" in str(pe).lower():
                    raise pe
                log(f"Status check notice: {pe}")

    except Exception as e:
        app_state["status"] = "error"
        app_state["message"] = str(e)
        log(f"❌ Error during execution: {e}")

@app.route("/api/launch", methods=["POST"])
def launch():
    if app_state["status"] in ["syncing", "pushing", "running"]:
        return jsonify({"success": False, "error": f"Job already in progress (Status: {app_state['status']})"}), 400

    config = request.get_json() or {}
    req_u, req_k = get_request_credentials()
    k_user = config.get("kaggle_username") or req_u
    k_key = config.get("kaggle_key") or req_k

    if not k_user or not k_key:
        stored = load_stored_credentials()
        k_user = stored.get("username")
        k_key = stored.get("key")

    if not k_user or not k_key:
        return jsonify({"success": False, "error": "No Kaggle credentials configured."}), 401

    config["kaggle_username"] = k_user
    config["kaggle_key"] = k_key

    thread = threading.Thread(target=run_kaggle_pipeline, args=(config,), daemon=True)
    thread.start()

    return jsonify({"success": True, "message": "Pipeline launched successfully."})

@app.route("/api/logs", methods=["GET"])
def get_logs():
    return jsonify({
        "status": app_state["status"],
        "message": app_state["message"],
        "progress": app_state["progress"],
        "logs": app_state["logs"]
    })

@app.route("/api/download", methods=["GET"])
def download():
    out_file = app_state.get("output_file")
    if out_file and (OUTPUT_DIR / out_file).exists():
        return send_file(OUTPUT_DIR / out_file, as_attachment=True)
    for cand in ["FINAL_VIDEO_CLEAN.mp4", "all_final_videos.zip"]:
        if (OUTPUT_DIR / cand).exists():
            return send_file(OUTPUT_DIR / cand, as_attachment=True)
    return jsonify({"error": "No output available yet"}), 404

@app.route("/api/cancel", methods=["POST"])
def cancel():
    app_state["status"] = "idle"
    app_state["message"] = "Job cancelled by user."
    app_state["progress"] = 0
    log("Job cancelled by user.")
    return jsonify({"success": True})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
