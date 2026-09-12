"""装修三步流水线冒烟：看懂空间(VLM) → 构思布局(LLM) → 渲染效果(Kolors img2img)"""
import asyncio
import base64
import io
import struct
import zlib
import sys

sys.path.insert(0, r"d:\Real_Estate_AI_Assistant_Platform\backend")


def make_png(w: int = 320, h: int = 240) -> bytes:
    """生成纯色测试 PNG（上白墙下灰地，模拟毛坯房极简图）"""
    rows = b""
    for y in range(h):
        v = int(200 + 40 * (y / h)) if y < h // 2 else int(120 + 30 * (y / h))
        rows += b"\x00" + bytes([v]) * (w * 3)
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


async def main() -> None:
    from app.services.render import get_task, submit_render

    png = make_png()
    print(f"[1] 提交任务 photo={len(png)}B ...")
    task = await submit_render(
        "smoke-pipeline", "normal", "modern", "living_room", "2k",
        photo_b64=base64.b64encode(png).decode(), photo_size=(320, 240),
        furniture=["sofa", "coffee_table", "tv", "potted_plant", "carpet"],
        wall_color="cream", floor_style="oak_floor", strength=0.75,
    )
    print(f"[2] task_id={task.task_id} mode={task.mode}")
    seen_phases = []
    while task.status in ("queued", "running"):
        await asyncio.sleep(2)
        if task.phase not in seen_phases:
            seen_phases.append(task.phase)
            print(f"    {task.progress:3d}% {task.phase}")
    print(f"[3] status={task.status}")
    print(f"[4] phases_seen={len(seen_phases)}: {seen_phases}")
    sr, lr = task.space_result or {}, task.layout_result or {}
    print(f"[5] 空间理解 room_type={sr.get('room_type')} | walls={str(sr.get('walls'))[:40]}")
    arr = lr.get("arrangement") or []
    print(f"[6] 布局方案 {len(arr)} 项: " + "; ".join(f"{a.get('item')}→{a.get('position')}" for a in arr[:3]))
    print(f"[7] image_url={task.image_url}")
    assert task.status == "done", "任务未完成"
    assert sr.get("room_type"), "空间理解产物缺失"
    assert arr, "布局方案缺失"
    print("[PASS] 三步流水线冒烟通过")


asyncio.run(main())
