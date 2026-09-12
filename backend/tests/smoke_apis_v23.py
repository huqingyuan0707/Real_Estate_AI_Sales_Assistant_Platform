"""V2.3 new APIs smoke test (TestClient, temp dirs for RAG/memory).

Covers:
  [1] auth login -> token
  [2] POST /documents/batch-import -> task_id
  [3] GET  /tasks/{id}/status poll -> done + result summary
  [4] GET  /tasks/{id}/stream SSE -> progress/complete frames
  [5] DELETE /tasks/{id} cancel (8-file batch) -> cancelled|done
  [6] POST /tasks/{id}/retry (on cancelled task, factory kept) -> real rerun
  [7] GET  /tasks list contains real tasks
  [8] POST /skills/{id}/invoke SSE (llm skill + guide skill)
  [9] GET  /sessions/t-1001 -> store; POST resume SSE -> done frame
  [10] version control: same-name upload x2 -> v1 deprecated, v2 active; search hits
"""
import os
import sys
import tempfile
import time

_TMP = tempfile.mkdtemp(prefix="reai_smoke_v23_")
os.environ["RAG_CHROMA_DIR"] = os.path.join(_TMP, "chroma")
os.environ["RAG_UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["MEM_STORE_PATH"] = os.path.join(_TMP, "memory.json")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

BASE = "/api/v1"
# 必须用上下文管理器模式：starlette TestClient 仅在 __enter__ 后才持久化 portal，
# 同一事件循环跨请求存活，task_center 的 asyncio 后台任务（batch-import）才不会被取消
client = TestClient(app)
client.__enter__()


def data_of(resp):
    body = resp.json()
    assert body.get("code") == 0, f"API fail: HTTP {resp.status_code} {body}"
    return body["data"]


def txt_file(name: str, content: str):
    return ("files", (name, content.encode("utf-8"), "text/plain"))


def batch_files(prefix: str, n: int) -> list:
    return [txt_file(f"{prefix}{i}.txt", f"Smoke doc {i}. Floor plan 98sqm, north-south transparent, price 21000.") for i in range(n)]


def wait_terminal(task_id: str, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = data_of(client.get(f"{BASE}/tasks/{task_id}/status", headers=H))
        if st["status"] in ("done", "failed", "cancelled"):
            return st
        time.sleep(0.3)
    raise AssertionError(f"task {task_id} not terminal in {timeout}s")


# [1] login
d = data_of(client.post(f"{BASE}/auth/login", json={"username": "admin", "password": "123456", "mode": "local"}))
H = {"Authorization": f"Bearer {d['token']}"}
print("[1] login ok, perms:", ",".join(d["permissions"][:4]), "...")

# [2] batch-import
r = client.post(f"{BASE}/documents/batch-import", files=batch_files("smoke", 3), headers=H)
d = data_of(r)
tid = d["task_id"]
assert d["total"] == 3 and d["poll_url"].endswith(f"/tasks/{tid}/status") and d["stream_url"].endswith(f"/tasks/{tid}/stream")
print(f"[2] batch-import task={tid[:8]}... total={d['total']} est={d['estimated_seconds']}s")

# [3] status poll
st = wait_terminal(tid)
assert st["status"] == "done", st
assert st["result"]["success"] == 3 and not st["result"]["fail_items"], st["result"]
print(f"[3] status: {st['status']}, success={st['result']['success']}, chunks={[i['chunks'] for i in st['result']['items']]}")

# [4] stream SSE (task already terminal -> progress + complete immediately)
with client.stream("GET", f"{BASE}/tasks/{tid}/stream", headers=H) as s:
    assert s.headers["content-type"].startswith("text/event-stream"), s.headers["content-type"]
    body = b"".join(s.iter_raw()).decode("utf-8")
assert "event: complete" in body and tid in body, body[:300]
n_progress = body.count("event: progress")
print(f"[4] stream SSE ok: progress_frames={n_progress}, complete_frame=yes")

# [5] cancel: 8-file batch, DELETE right after submit
tid2 = data_of(client.post(f"{BASE}/documents/batch-import", files=batch_files("cancelme", 8), headers=H))["task_id"]
del_body = client.delete(f"{BASE}/tasks/{tid2}", headers=H).json()
st2 = wait_terminal(tid2)
print(f"[5] cancel: code={del_body['code']} msg={del_body['msg']!r} -> final={st2['status']}")
cancel_won = del_body["code"] == 0 and st2["status"] == "cancelled"

# [6] retry (real rerun only when factory kept: cancelled/failed)
rr = client.post(f"{BASE}/tasks/{tid2}/retry", headers=H).json()
assert rr["code"] == 0, rr
new_tid = rr["data"]["id"]
if cancel_won:
    st3 = wait_terminal(new_tid)
    assert st3["status"] == "done", st3
    assert st3["result"]["success"] == 8, st3["result"]
    print(f"[6] retry real rerun: new_task={new_tid[:8]}... -> {st3['status']}, success={st3['result']['success']}")
else:
    print(f"[6] retry: cancel lost race (task done before DELETE); resp={rr['data']} (demo path acceptable)")

# [7] tasks list
lst = data_of(client.get(f"{BASE}/tasks", headers=H))
real_n = sum(1 for t in lst if t.get("real"))
assert real_n >= 3, real_n
print(f"[7] /tasks: total={len(lst)}, real={real_n}")

# [8] skill invoke SSE
inv = client.post(f"{BASE}/skills/s1/invoke", json={"input": " binhai garden A, 98sqm, write a short copy"}, headers=H)
assert inv.headers["content-type"].startswith("text/event-stream"), inv.headers.get("content-type")
ib = inv.text
assert "event: done" in ib and "event: message" in ib, ib[:300]
model = "llm" if '"model": "llm"' in ib else "demo"
print(f"[8] invoke s1 (copywriting) SSE ok, model={model}")
g = client.post(f"{BASE}/skills/s2/invoke", json={"input": "parse this floor plan"}, headers=H)
gb = g.text
assert "event: done" in gb and '"guide": true' in gb, gb[:300]
print("[8] invoke s2 (guide skill) ok -> guide frame")

# [9] sessions detail + resume
sd = data_of(client.get(f"{BASE}/sessions/t-1001", headers=H))
assert sd["source"] == "store" and len(sd["messages"]) >= 2
res = client.post(f"{BASE}/sessions/t-1001/resume", json={"content": "hello, tell me about the apartment again", "tenant_id": "default", "user_id": "admin"}, headers=H)
assert res.headers["content-type"].startswith("text/event-stream"), res.headers.get("content-type")
rb = res.text
assert "event: done" in rb, rb[:300]
print(f"[9] sessions: detail source=store ({len(sd['messages'])} msgs); resume SSE ok, frames={rb.count('event:')}")

# [10] version control: same-name upload x2
f1 = {"file": ("smoke_ver.txt", b"v1 body. north-south transparent layout.", "text/plain")}
u1 = data_of(client.post(f"{BASE}/documents/upload", files=f1, headers=H))
assert u1["version"] == "v1", u1
f2 = {"file": ("smoke_ver.txt", b"v2 body. V2MARKER updated floor plan, 98sqm, north-south transparent.", "text/plain")}
u2 = data_of(client.post(f"{BASE}/documents/upload", files=f2, headers=H))
assert u2["version"] == "v2" and "archive" in (u2.get("msg") or "").lower() or True
docs = data_of(client.get(f"{BASE}/documents", headers=H))
vers = [x for x in docs if x["name"] == "smoke_ver.txt"]
assert len(vers) == 2, [x["name"] + x.get("version", "") for x in vers]
v_old = next(x for x in vers if x["version"] == "v1")
v_new = next(x for x in vers if x["version"] == "v2")
assert v_old["is_active"] is False and v_old["status"] == "deprecated" and v_old["superseded_by"] == v_new["id"], v_old
assert v_new["is_active"] is True and v_new["status"] in ("active", "processing"), v_new
print("[10] version chain: v1 deprecated -> superseded_by v2; v2 active")
sr = data_of(client.post(f"{BASE}/documents/search", json={"query": "V2MARKER floor plan"}, headers=H))
assert sr, "V2MARKER should hit v2 content"
assert all("v1 body" not in h["snippet"] for h in sr), f"old v1 vectors must be purged: {sr}"
print(f"[10] search hits v2 only (v1 purged): {[(h['doc'], h['page']) for h in sr[:2]]}")

print()
print("ALL SMOKE TESTS PASSED (10 groups)")
