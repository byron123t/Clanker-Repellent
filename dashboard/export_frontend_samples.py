"""Freeze the synthetic template API for the independent frontend design handoff."""
import base64
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "dashboard-template"))
from serve import FixtureApp


def main():
    responses, lookup = [], {}

    def record(app, path, **query):
        query_string = urlencode(sorted(query.items()))
        meta = {}
        def start(status, headers):
            meta.update(status=status, headers=dict(headers))
        raw = b"".join(app({"REQUEST_METHOD": "GET", "PATH_INFO": path,
            "QUERY_STRING": query_string, "HTTP_AUTHORIZATION": "Bearer sample-export"}, start))
        item = {"status": meta["status"], "content_type": meta["headers"]["Content-Type"]}
        if item["content_type"].startswith("application/json"):
            item.update(encoding="json", body=json.loads(raw))
        else:
            item.update(encoding="base64", body=base64.b64encode(raw).decode())
        if "Content-Disposition" in meta["headers"]:
            item["content_disposition"] = meta["headers"]["Content-Disposition"]
        key = json.dumps(item, sort_keys=True)
        if key not in lookup:
            lookup[key] = len(responses)
            responses.append(item)
        return path + ("?" + query_string if query_string else ""), lookup[key]

    app = FixtureApp("sample-export")
    populated = dict(record(app, path) for path in ("/api/summary", "/api/responses"))
    for detail in app.journal["deployments"].values():
        route = f'/api/deployments/{detail["id"]}'
        populated.update([record(app, route)])
        for row in detail["files"]:
            versions = ["before", "after"] + (["insertion"] if row["edits"] else [])
            for version in versions:
                for action in ("preview", "download"):
                    # Both forms occur in UI clients; query order is immaterial.
                    for query in ({"file": row["number"], "version": version},
                                  {"file": row["number"], "step": 0, "version": version}):
                        populated.update([record(app, route + "/" + action, **query)])
    for response in app.journal["responses"]:
        for version in ("before", "after"):
            for action in ("preview", "download"):
                populated.update([record(app, f'/api/responses/{response["id"]}/{action}', version=version)])
    assert all(item["status"] == "200 OK" for item in responses)
    scenarios = {"populated": populated}
    for name in ("empty", "error"):
        sample = FixtureApp("sample-export", name)
        scenarios[name] = dict(record(sample, path) for path in ("/api/summary", "/api/responses"))
    output = {"format": 1, "description": "Fixed synthetic responses for frontend design",
              "scenarios": scenarios, "responses": responses}
    target = ROOT / "frontend-handoff" / "fixtures" / "responses.json"
    target.write_text(json.dumps(output, indent=2) + "\n")
    print(f"Saved {len(responses)} fixed responses across {len(scenarios)} scenarios.")


if __name__ == "__main__":
    main()
