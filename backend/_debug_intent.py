import sys

sys.path.insert(0, ".")

from app.api.v1.endpoints.chat import _needs_retrieval  # noqa: E402

content = "滨江花园的首付比例和贷款利率是多少？"
print("INTENT:", _needs_retrieval(content))
print("KEYWORDS_HIT:", [k for k in ("首付", "贷款", "利率") if k in content])

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)
with client.stream("POST", "/api/v1/chat", json={"thread_id": "dbg", "content": content}) as r:
    events = []
    for line in r.iter_lines():
        if line.startswith("event:"):
            events.append(line.split(":", 1)[1].strip())
        if line.startswith("data:") and "references" in line:
            print("DONE:", line[:400])
    print("EVENTS:", events)
