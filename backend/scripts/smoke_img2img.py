"""img2img smoke test: empty-room photo + furniture/wall/floor -> renovated render.
Run: backend venv python, backend server must be on 127.0.0.1:8000
"""
import io
import struct
import sys
import time
import zlib

import httpx

BASE = "http://127.0.0.1:8000/api/v1"


def make_png(w: int, h: int) -> bytes:
    """Minimal empty-room test image (cement walls + floor + window) in pure stdlib."""
    rows = []
    for y in range(h):
        row = bytearray([0])  # filter type 0
        for x in range(w):
            if y > h * 0.72:  # floor
                px = (176, 168, 152)
            elif w * 0.55 < x < w * 0.92 and h * 0.18 < y < h * 0.62:  # window
                px = (214, 228, 238)
            elif w * 0.74 < x < w * 0.76 and h * 0.18 < y < h * 0.62:  # window mullion
                px = (240, 240, 240)
            else:  # cement wall with subtle noise
                n = (x * 7 + y * 13) % 11
                px = (148 + n, 146 + n, 140 + n)
            row.extend(px)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def main() -> int:
    r = httpx.post(
        f"{BASE}/auth/login",
        json={"username": "admin", "password": "123456", "mode": "local"},
        trust_env=False,
        timeout=10,
    )
    r.raise_for_status()
    tok = r.json()["data"]["token"]
    h = {"Authorization": f"Bearer {tok}"}
    print("login OK")

    png = make_png(1024, 768)
    data = {
        "house_task_id": "smoke-img2img",
        "layout_plan": "normal",
        "style": "modern",
        "scene": "living_room",
        "resolution": "2k",
        "furniture": '["corner_sofa","tv","potted_plant","carpet","fridge"]',
        "wall_color": "cream",
        "floor_style": "oak_floor",
        "strength": "0.75",
        "photo_width": "1024",
        "photo_height": "768",
    }
    files = {"photo": ("room.png", png, "image/png")}
    r = httpx.post(
        f"{BASE}/render/generate", headers=h, data=data, files=files,
        trust_env=False, timeout=30,
    )
    print("generate:", r.status_code, r.text[:220])
    if r.status_code != 200:
        return 1
    tid = r.json()["data"]["task_id"]

    for _ in range(50):
        time.sleep(3)
        s = httpx.get(f"{BASE}/render/{tid}", headers=h, trust_env=False, timeout=10).json()["data"]
        print(f"  {s['status']:>7} {s['progress']:>3}% {s['phase'][:36]}")
        if s["status"] in ("done", "failed"):
            print("mode:", s["mode"], "| img:", s["image_url"])
            if s["image_url"] and s["image_url"].startswith("/api"):
                f = httpx.get(f"http://127.0.0.1:8000{s['image_url']}", trust_env=False, timeout=15)
                print("file fetch:", f.status_code, f.headers.get("content-type"), len(f.content), "bytes")
                return 0 if s["status"] == "done" and f.status_code == 200 else 1
            return 0 if s["status"] == "done" else 1
    print("TIMEOUT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
