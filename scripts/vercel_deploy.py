"""Deploy web/ to Vercel production through the REST API.

The Vercel CLI looks up the token's user, which fails for team-scoped tokens;
the API accepts them. Needs VERCEL_TOKEN, VERCEL_ORG_ID (team id), VERCEL_PROJECT_ID.
"""
import hashlib, json, os, pathlib, sys, time, urllib.error, urllib.request

TOKEN, TEAM, PROJECT = (os.environ[k].strip() for k in ("VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID"))
ROOT = pathlib.Path(__file__).resolve().parents[1] / "web"
SKIP = {"node_modules", ".vercel", "dist", ".git"}


def call(method, url, data=None, headers=None, attempts=5):
    """One API request, retried on dropped connections and 429/5xx (one of ~400 uploads failing is routine)."""
    req = urllib.request.Request(url, data=data, method=method, headers={"Authorization": f"Bearer {TOKEN}", **(headers or {})})
    for i in range(attempts):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or i == attempts - 1:
                return e.code, e.read()
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if i == attempts - 1:
                raise
        time.sleep(2 ** i)


entries = []
for p in sorted(ROOT.rglob("*")):
    if not p.is_file() or set(p.relative_to(ROOT).parts) & SKIP:
        continue
    b = p.read_bytes()
    sha = hashlib.sha1(b).hexdigest()
    s, r = call("POST", f"https://api.vercel.com/v2/files?teamId={TEAM}", b,
                {"x-vercel-digest": sha, "Content-Type": "application/octet-stream"})
    if s not in (200, 201):
        sys.exit(f"upload failed for {p}: {s} {r[:200]!r}")
    entries.append({"file": p.relative_to(ROOT).as_posix(), "sha": sha, "size": len(b)})
print(len(entries), "files uploaded")

body = json.dumps({"name": "congress-trades", "project": PROJECT, "target": "production", "files": entries}).encode()
s, r = call("POST", f"https://api.vercel.com/v13/deployments?teamId={TEAM}&skipAutoDetectionConfirmation=1", body,
            {"Content-Type": "application/json"})
dep = json.loads(r)
if s != 200:
    sys.exit(f"deployment failed: {s} {dep.get('error')}")
for _ in range(90):
    state = json.loads(call("GET", f"https://api.vercel.com/v13/deployments/{dep['id']}?teamId={TEAM}")[1]).get("readyState")
    if state in ("READY", "ERROR", "CANCELED"):
        break
    time.sleep(10)
print("deployment", dep["id"], state)
sys.exit(0 if state == "READY" else 1)
