"""
Save Nature Certificate Generator API
======================================
Flask app designed for Vercel (serverless) + local development.
Certificate for saving nature. Only name + current date + a good message.
NO SCORE.

Endpoints
---------
GET  /                                  -> Landing page with live form
GET  /health                            -> {"status": "ok"}
GET  /certificate?name=Aarav            -> PNG certificate image
GET  /certificate/<name>                -> PNG certificate image (path param)
POST /certificate                       -> JSON {"name": "..."} -> PNG
GET  /api/certificate?...               -> alias of /certificate

Optional query params
---------------------
download=true   -> force file download instead of inline preview
format=jpg|png|json -> image format (default jpg for this 4K photo template; png is ~18MB)
date=26 November 2026 -> override date of issue (defaults to today, Asia/Kolkata)
message=...     -> override the good message (optional)

Template: assets/certificate_template.jpg (sunlit forest, 3840x2560)
Fonts:    assets/fonts/*.ttf (Cinzel, Great Vibes, Poppins, Montserrat)
"""

import base64
import io
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from flask import Flask, Response, jsonify, request, send_file
from PIL import Image, ImageDraw, ImageFont

THIS_DIR = Path(__file__).resolve().parent
BASE_DIR = THIS_DIR.parent
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

TEMPLATE_CANDIDATES = [
    ASSETS_DIR / "certificate_template.jpg",
    ASSETS_DIR / "certificate_template.png",
    THIS_DIR / "certificate_template.jpg",
    THIS_DIR / "certificate_template.png",
    Path.cwd() / "assets" / "certificate_template.jpg",
    Path("/home/user/nature-certificate-api/assets/certificate_template.jpg"),
]

FONT_FILES = {
    "cinzel": FONTS_DIR / "Cinzel-Bold.ttf",
    "script": FONTS_DIR / "GreatVibes-Regular.ttf",
    "poppins": FONTS_DIR / "Poppins-Regular.ttf",
    "poppins_bold": FONTS_DIR / "Poppins-Bold.ttf",
    "poppins_semi": FONTS_DIR / "Poppins-SemiBold.ttf",
    "montserrat": FONTS_DIR / "Montserrat-Regular.ttf",
}

FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
]

DEFAULT_MESSAGE = "For your dedication to saving nature and protecting our planet for future generations. Thank you for making the Earth greener!"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024


def find_template() -> Path:
    for p in TEMPLATE_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("certificate_template.jpg not found in assets/")


def get_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_FILES.get(kind)
    if path and path.exists():
        try:
            return ImageFont.truetype(str(path), size)
        except Exception:
            pass
    for fb in FALLBACK_FONTS:
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size)
            except Exception:
                continue
    return ImageFont.load_default()


def fit_font(kind: str, text: str, max_width: int, start_size: int, min_size: int = 28):
    size = start_size
    while size > min_size:
        font = get_font(kind, size)
        try:
            w = font.getlength(text)
        except Exception:
            w = size * len(text) * 0.6
        if w <= max_width:
            return font, size
        size -= 4
    return get_font(kind, min_size), min_size


def text_size(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered(draw, cx, y, text, font, fill, shadow=True):
    w, h = text_size(draw, text, font)
    x = cx - w / 2
    if shadow:
        draw.text((x + 3, y + 3), text, font=font, fill=(5, 20, 10, 220))
    draw.text((x, y), text, font=font, fill=fill)
    return w, h


def draw_spaced_centered(draw, cx, y, text, font, fill, spacing=8, shadow=True):
    widths, total = [], 0
    for ch in text:
        try:
            w = font.getlength(ch)
        except Exception:
            w = 20
        widths.append(w)
        total += w
    total += spacing * (len(text) - 1)
    x = cx - total / 2
    if shadow:
        sx = x
        for ch, w in zip(text, widths):
            draw.text((sx + 2, y + 2), ch, font=font, fill=(5, 20, 10, 200))
            sx += w + spacing
    sx = x
    for ch, w in zip(text, widths):
        draw.text((sx, y), ch, font=font, fill=fill)
        sx += w + spacing
    return total


def wrap_text(text, font, max_width, draw):
    """Greedy word-wrap to max_width. Returns list of lines."""
    words = text.split()
    lines, cur = [], ""
    for word in words:
        trial = f"{cur} {word}".strip()
        w, _ = text_size(draw, trial, font)
        if w <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def current_date_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        now = datetime.now()
    return now.strftime("%d %B %Y")


def generate_certificate(name: str, date_str=None, message=None) -> Image.Image:
    template_path = find_template()
    img = Image.open(template_path).convert("RGBA")
    W, H = img.size
    cx = W // 2

    # --- Dark green translucent panel for readability over bright forest ---
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    panel_x0, panel_x1 = int(W * 0.16), int(W * 0.84)
    panel_y0, panel_y1 = int(H * 0.09), int(H * 0.80)
    odraw.rounded_rectangle(
        [panel_x0, panel_y0, panel_x1, panel_y1],
        radius=48,
        fill=(8, 32, 18, 150),
        outline=(212, 175, 55, 200),
        width=4,
    )
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    GOLD = (255, 209, 102, 255)
    GOLD_LIGHT = (255, 230, 150, 255)
    WHITE = (255, 255, 255, 255)
    CREAM = (255, 248, 220, 255)
    MUTED = (220, 235, 210, 255)

    # --- Title: SAVE NATURE ---
    title_font, _ = fit_font("cinzel", "SAVE NATURE", int(W * 0.55), int(H * 0.085), 56)
    tw, th = text_size(draw, "SAVE NATURE", title_font)
    tx, ty = cx - tw / 2, H * 0.125
    draw.text((tx + 3, ty + 4), "SAVE NATURE", font=title_font, fill=(5, 20, 10, 230))
    draw.text((tx, ty), "SAVE NATURE", font=title_font, fill=GOLD)

    # --- Subtitle: CERTIFICATE OF APPRECIATION ---
    sub_font = get_font("cinzel", int(H * 0.030))
    sub_y = H * 0.235
    draw_spaced_centered(draw, cx, sub_y, "CERTIFICATE OF APPRECIATION", sub_font, WHITE, spacing=7)
    line_y = sub_y + int(H * 0.026)
    line_len = int(W * 0.10)
    gap = int(W * 0.225)
    draw.line([(cx - gap - line_len, line_y), (cx - gap, line_y)], fill=GOLD_LIGHT, width=3)
    draw.line([(cx + gap, line_y), (cx + gap + line_len, line_y)], fill=GOLD_LIGHT, width=3)
    dy = line_y + 13
    draw.polygon([(cx, dy - 7), (cx + 7, dy), (cx, dy + 7), (cx - 7, dy)], fill=GOLD)

    # --- Presented to ---
    presented_font = get_font("poppins", int(H * 0.024))
    draw_centered(draw, cx, H * 0.315, "This certificate is proudly presented to", presented_font, MUTED)

    # --- Name (script, gold) — NO underline ---
    name_font, _ = fit_font("script", name, int(W * 0.58), int(H * 0.088), 44)
    nw, nh = text_size(draw, name, name_font)
    name_y = H * 0.365
    draw.text((cx - nw / 2 + 3, name_y + 4), name, font=name_font, fill=(5, 20, 10, 220))
    draw.text((cx - nw / 2, name_y), name, font=name_font, fill=GOLD)

    # --- Good message (wrapped, centred) ---
    msg = (message or DEFAULT_MESSAGE).strip()
    msg_font = get_font("poppins", int(H * 0.026))
    lines = wrap_text(msg, msg_font, int(W * 0.60), draw)
    msg_y = H * 0.505
    line_h = int(H * 0.038)
    for i, line in enumerate(lines[:3]):
        draw_centered(draw, cx, msg_y + i * line_h, line, msg_font, CREAM)

    # --- Date of Issue (pill below panel) ---
    date_display = date_str or current_date_str()
    date_font = get_font("poppins_semi", int(H * 0.024))
    date_label = f"Date of Issue:  {date_display}"
    dw, dh = text_size(draw, date_label, date_font)
    date_y = H * 0.825
    dpad_x, dpad_y = 32, 14
    draw.rounded_rectangle(
        [cx - dw / 2 - dpad_x, date_y - dpad_y, cx + dw / 2 + dpad_x, date_y + dh + dpad_y],
        radius=26, fill=(8, 32, 18, 190), outline=(212, 175, 55, 160), width=3,
    )
    draw_centered(draw, cx, date_y, date_label, date_font, WHITE, shadow=False)

    # --- Footer ---
    foot_font = get_font("poppins", int(H * 0.016))
    draw_centered(draw, cx, H * 0.905, "~  Save Nature, Save Life  ~", foot_font, MUTED)

    return img.convert("RGB")


def certificate_response(name, date_str=None, message=None, download=False, as_json=False, fmt="jpg"):
    if not name or not str(name).strip():
        return jsonify({"error": "Missing required parameter: name"}), 400
    name = str(name).strip()[:80]
    fmt = str(fmt or "jpg").lower()
    if fmt in ("jpg", "jpeg"):
        fmt = "jpeg"
    elif fmt != "png":
        fmt = "jpeg"
    if as_json:
        fmt = "jpeg"
    try:
        img = generate_certificate(name, date_str=date_str, message=message)
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to generate certificate: {e}"}), 500

    buf = io.BytesIO()
    if fmt == "jpeg":
        img.save(buf, format="JPEG", quality=90, optimize=True)
        mime, ext = "image/jpeg", "jpg"
    else:
        img.save(buf, format="PNG", compress_level=1)
        mime, ext = "image/png", "png"
    buf.seek(0)

    if as_json:
        b64 = base64.b64encode(buf.getvalue()).decode()
        return jsonify({
            "name": name,
            "date_of_issue": date_str or current_date_str(),
            "message": message or DEFAULT_MESSAGE,
            "image_base64": b64,
            "data_uri": f"data:{mime};base64,{b64}",
        })

    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name).strip().replace(" ", "_")
    filename = f"Save_Nature_Certificate_{safe_name}.{ext}"
    resp = send_file(buf, mimetype=mime, as_attachment=download, download_name=filename)
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["X-Certificate-Name"] = name
    return resp


def parse_inputs():
    name = request.args.get("name")
    date_str = request.args.get("date")
    message = request.args.get("message")
    download = request.args.get("download", "").lower() in ("1", "true", "yes")
    fmt = request.args.get("format", "jpg").lower()
    as_json = fmt == "json"
    if fmt not in ("png", "jpg", "jpeg", "json"):
        fmt = "jpg"
    if request.is_json:
        data = request.get_json(silent=True) or {}
        name = name or data.get("name")
        date_str = date_str or data.get("date")
        message = message or data.get("message")
        download = download or bool(data.get("download"))
        if data.get("format"):
            fmt = str(data.get("format")).lower()
            as_json = fmt == "json"
    elif request.form:
        name = name or request.form.get("name")
        date_str = date_str or request.form.get("date")
        message = message or request.form.get("message")
    return name, date_str, message, download, as_json, fmt


@app.after_request
def add_cors(resp: Response):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.route("/", methods=["GET"])
def index():
    html = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Save Nature Certificate Generator</title>
<style>
 body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#0a2012;color:#fff;
      min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px}
 .card{max-width:640px;width:100%;background:linear-gradient(160deg,#0f2e1a,#1a4a28);border:1px solid #ffd16655;
       border-radius:20px;padding:28px;box-shadow:0 20px 60px #0009}
 h1{margin:0 0 6px;font-size:28px;color:#ffd166} p{color:#d8ecd0;line-height:1.5}
 label{display:block;margin:14px 0 6px;font-weight:600} input{width:100%;padding:12px;border-radius:10px;border:1px solid #ffffff33;background:#0a2012;color:#fff;font-size:16px;box-sizing:border-box}
 button{margin-top:18px;width:100%;padding:13px;border:0;border-radius:10px;background:#ffd166;color:#0f2e1a;font-weight:800;font-size:16px;cursor:pointer}
 button:hover{background:#ffe08a} img{max-width:100%;border-radius:12px;margin-top:18px;display:none}
 .api{background:#0a2012;border:1px solid #ffffff22;border-radius:10px;padding:12px;overflow:auto;font-size:13px}
</style></head><body><div class="card">
<h1>🌳 Save Nature Certificate Generator</h1>
<p>Enter a name to generate a Save Nature certificate with today's date and a good message. No score needed.</p>
<form id="f">
<label>Name</label><input id="name" placeholder="e.g. Aarav Sharma" required>
<button>Generate Certificate</button></form>
<img id="out" alt="Certificate preview">
<p style="margin-top:18px">API usage:</p>
<div class="api">GET /certificate?name=Aarav<br>GET /certificate/Aarav<br>POST /certificate  {"name":"Aarav"}</div>
</div><script>
document.getElementById('f').onsubmit=e=>{e.preventDefault();
 const n=encodeURIComponent(document.getElementById('name').value);
 const img=document.getElementById('out'); img.src='/certificate?name='+n+'&format=jpg'; img.style.display='block';};
</script></body></html>"""
    return Response(html, mimetype="text/html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "nature-certificate-api"})


@app.route("/certificate", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/certificate", methods=["GET", "POST", "OPTIONS"])
def certificate():
    if request.method == "OPTIONS":
        return Response(status=204)
    name, date_str, message, download, as_json, fmt = parse_inputs()
    return certificate_response(name, date_str, message, download, as_json, fmt)


@app.route("/certificate/<path:name>", methods=["GET"])
@app.route("/api/certificate/<path:name>", methods=["GET"])
def certificate_path(name):
    name = unquote(name)
    date_str = request.args.get("date")
    message = request.args.get("message")
    download = request.args.get("download", "").lower() in ("1", "true", "yes")
    fmt = request.args.get("format", "jpg").lower()
    as_json = fmt == "json"
    return certificate_response(name, date_str, message, download, as_json, fmt)


app_obj = app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
