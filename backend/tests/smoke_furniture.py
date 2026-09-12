"""任务7 冒烟：家具清单库 + 渲染层改查清单库 + AI 解析降级 + 渲染链路
运行（在 backend 目录）：.venv\\Scripts\\python.exe tests/smoke_furniture.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["RENDER_PROVIDER"] = "simulate"   # 不触发真实生图/云端校验
os.environ["RENDER_SIM_SECONDS"] = "0.3"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.services import furniture as fsvc  # noqa: E402
from app.services import render as rsvc  # noqa: E402

# 数据隔离：清单库与生成历史全部落在临时目录
_tmp = Path(tempfile.mkdtemp(prefix="furn_smoke_"))
fsvc._CATALOG_PATH = _tmp / "furniture_catalog.json"
rsvc.HISTORY_PATH = _tmp / "render_history.json"

_ok = 0


def check(name: str, cond: bool):
    global _ok
    assert cond, f"FAIL: {name}"
    _ok += 1
    print(f"PASS {_ok}. {name}")


with TestClient(app) as client:
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": "123456"})
    check("login admin", r.status_code == 200 and r.json()["code"] == 0)
    H = {"Authorization": f"Bearer {r.json()['data']['token']}"}

    # 1) 清单库首启播种：5 分类 / 32 内置项
    d = client.get("/api/v1/furniture/catalog", headers=H).json()["data"]
    check("catalog seed 5 cats / 32 items",
          len(d["categories"]) == 5 and d["total"] == 32)
    ids = {i["id"] for i in d["items"]}
    check("builtin keys present",
          {"corner_sofa", "tv_cabinet", "treadmill", "office_chair"} <= ids)

    # 2) 自定义条目：增 / 重名 400 / 改 / 删
    r = client.post("/api/v1/furniture/items", headers=H, json={
        "name": "双人学习桌", "category": "study", "en": "a study desk for two",
        "aliases": ["学习桌", "双人桌"]})
    check("add custom item", r.status_code == 200 and r.json()["data"]["id"].startswith("f_"))
    cid = r.json()["data"]["id"]
    r = client.post("/api/v1/furniture/items", headers=H, json={"name": "双人学习桌", "category": "study"})
    check("duplicate name -> 400", r.status_code == 400)
    r = client.put(f"/api/v1/furniture/items/{cid}", headers=H, json={"name": "双人书桌", "en": ""})
    check("update custom item", r.status_code == 200 and r.json()["data"]["name"] == "双人书桌")
    d = client.delete(f"/api/v1/furniture/items/{cid}", headers=H)
    check("delete custom item", d.status_code == 200)

    # 3) 分类：增删 + 内置分类禁删
    r = client.post("/api/v1/furniture/categories", headers=H, json={"name": "阳台"})
    check("add category", r.status_code == 200)
    cat_id = r.json()["data"]["id"]
    r = client.delete(f"/api/v1/furniture/categories/{cat_id}", headers=H)
    check("delete category", r.status_code == 200)
    r = client.delete("/api/v1/furniture/categories/living", headers=H)
    check("builtin category delete -> 400", r.status_code == 400)

    # 4) 内置条目删除记 removed_builtin，重载不复活；删除后同名可重建
    r = client.delete("/api/v1/furniture/items/sofa", headers=H)
    check("delete builtin item", r.status_code == 200)
    d = client.get("/api/v1/furniture/catalog", headers=H).json()["data"]
    check("removed builtin not resurrected", all(i["id"] != "sofa" for i in d["items"]))
    r = client.post("/api/v1/furniture/items", headers=H, json={"name": "沙发", "category": "living"})
    check("re-add same name after builtin delete", r.status_code == 200)
    rid = r.json()["data"]["id"]
    client.delete(f"/api/v1/furniture/items/{rid}", headers=H)

    # 5) AI 解析降级切词（打补丁强制走 rules，不碰云端）
    fsvc._is_cloud_chat_available = lambda: False
    r = client.post("/api/v1/furniture/parse", headers=H,
                    data={"text": "转角沙发2张，电视柜，一张双人床 x1"})
    body = r.json()
    check("parse http 200 rules", r.status_code == 200 and body["data"]["source"] == "rules")
    items = body["data"]["items"]
    names = [i["name"] for i in items]
    check("parse split + catalog hit",
          "转角沙发" in names and "电视柜" in names and "一张双人床" in names)
    hit = {i["name"]: i for i in items}["转角沙发"]
    check("parse matched catalog id/count",
          hit["catalog_id"] == "corner_sofa" and hit["in_catalog"] and hit["count"] == "2")

    # 6) 渲染链路走清单库：非法 id 被滤除，快照/历史中文名正确
    r = client.post("/api/v1/render/generate", headers=H, data={
        "style": "modern", "scene": "living_room",
        "furniture": json.dumps(["corner_sofa", "bed", "no_such_id"])})
    task_id = r.json()["data"]["task_id"]
    snap = None
    for _ in range(40):
        snap = client.get(f"/api/v1/render/{task_id}", headers=H).json()["data"]
        if snap["status"] in ("done", "failed"):
            break
        time.sleep(0.2)
    check("render done(simulate)", snap["status"] == "done")
    check("snapshot furniture names from catalog",
          snap["furniture_names"] == ["转角沙发", "大床"])
    hist = client.get("/api/v1/render/history", headers=H).json()["data"]["items"]
    check("history furniture names from catalog",
          hist and hist[0]["furniture_names"] == ["转角沙发", "大床"])

print(f"\nALL {_ok} PASS")
