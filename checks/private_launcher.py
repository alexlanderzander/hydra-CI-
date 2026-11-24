"""Project-specific Hydra CI launcher. Never emits private source or build logs."""
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

BROKER = "https://hydra-ci-broker.evinsta9.workers.dev"
AUDIENCE = "hydra-project-ci-v1"
ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ci" / "job.json"

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Unexpected redirect")

HTTP = urllib.request.build_opener(NoRedirect)

def fetch(req, limit, timeout=30):
    with HTTP.open(req, timeout=timeout) as res:
        data = res.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("Bounded response exceeded")
        return data

def token():
    address = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    parsed = urllib.parse.urlsplit(address)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise RuntimeError("Invalid OIDC endpoint")
    url = address + ("&" if parsed.query else "?") + urllib.parse.urlencode({"audience": AUDIENCE})
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    value = json.loads(fetch(req, 24000))["value"]
    if not isinstance(value, str) or len(value) > 16000:
        raise RuntimeError("Invalid OIDC assertion")
    return value

def broker(config, path, auth=None, payload=None, maximum=500000):
    headers = {"X-Hydra-CI-Job": config["job"], "Accept": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + auth
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload, separators=(",", ":")).encode()
    return fetch(urllib.request.Request(BROKER + path, data=data, headers=headers), maximum, 45)

def require_http(config, path, expected, auth=None):
    try:
        broker(config, path, auth)
    except urllib.error.HTTPError as exc:
        if exc.code == expected:
            return
    raise RuntimeError("Authorization boundary assertion failed")

def git_hash(kind, content):
    return hashlib.sha1(kind.encode() + b" " + str(len(content)).encode() + b"\0" + content).hexdigest()

def tree_digest(entries):
    tree = {}
    for path, mode, sha in entries:
        parts = PurePosixPath(path).parts
        node = tree
        for part in parts[:-1]:
            child = node.setdefault(part, {})
            if not isinstance(child, dict):
                raise RuntimeError("Conflicting path")
            node = child
        if parts[-1] in node:
            raise RuntimeError("Duplicate tree entry")
        node[parts[-1]] = (mode, sha)
    def digest(node):
        items = []
        for name, value in node.items():
            if isinstance(value, dict):
                mode, sha, isdir = "40000", digest(value), True
            else:
                mode, sha = value
                isdir = False
            label = name.encode("utf-8")
            items.append((label + (b"/" if isdir else b""), mode.encode() + b" " + label + b"\0" + bytes.fromhex(sha)))
        return git_hash("tree", b"".join(item[1] for item in sorted(items)))
    return digest(tree)

def materialize(config, job, workspace):
    entries, seen, total = [], set(), 0
    auth = token()
    for index in range(job["partCount"]):
        if index % 16 == 0:
            auth = token()
        rows = json.loads(broker(config, "/v1/source/" + str(index), auth))
        if not isinstance(rows, list):
            raise RuntimeError("Invalid source part")
        for row in rows:
            path, mode, sha = row["path"], row["mode"], row["sha"]
            p = PurePosixPath(path)
            if (not path or len(path) > 400 or p.is_absolute() or path != p.as_posix()
                or any(x in ("", ".", "..", ".git") for x in p.parts) or "\\" in path
                or path in seen or mode not in ("100644", "100755") or not re.fullmatch("[a-f0-9]{40}", sha)):
                raise RuntimeError("Unsafe source entry")
            raw = base64.b64decode(row["data"], validate=True)
            if git_hash("blob", raw) != sha:
                raise RuntimeError("Source blob integrity mismatch")
            total += len(raw)
            if total > 12_000_000 or len(seen) >= 1200:
                raise RuntimeError("Source bounds exceeded")
            target = workspace.joinpath(*p.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(raw)
            target.chmod(0o700 if mode == "100755" else 0o600)
            seen.add(path)
            entries.append((path, mode, sha))
    if not entries or tree_digest(entries) != config["tree"]:
        raise RuntimeError("Source tree integrity mismatch")

def build(config, job):
    with tempfile.TemporaryDirectory(prefix="hydra-private-", dir=os.environ["RUNNER_TEMP"]) as tmp:
        root = Path(tmp)
        source, home, temp = (root / "source", root / "home", root / "temp")
        for p in (source, home, temp):
            p.mkdir(mode=0o700)
        materialize(config, job, source)
        print("Verified immutable private revision; executing private CI gate", flush=True)
        log = root / "private.log"
        env = {"PATH": os.environ["PATH"], "HOME": str(home), "RUNNER_TEMP": str(temp),
               "TMPDIR": str(temp), "LANG": "C.UTF-8", "CI": "true", "HYDRA_VERSION": config["revision"]}
        rc = 1
        with log.open("wb") as output:
            try:
                rc = subprocess.run(["bash", "scripts/ci-broker-run.sh"], cwd=source, env=env,
                                    stdout=output, stderr=subprocess.STDOUT, timeout=2100, check=False).returncode
            except subprocess.TimeoutExpired:
                output.write(b"\nPrivate CI timed out\n")
        with log.open("rb") as f:
            f.seek(max(0, log.stat().st_size - 350000))
            tail = f.read().decode("utf-8", errors="replace")
        result = {"revision": config["revision"], "kind": "build", "status": "passed" if rc == 0 else "failed", "log": tail}
        if rc == 0:
            artifact = source / "deploy/cloudflare/dist/worker.mjs"
            if not artifact.is_file() or artifact.stat().st_size > 2_200_000:
                raise RuntimeError("Private release artifact missing or oversized")
            raw = artifact.read_bytes()
            result["artifact"] = base64.b64encode(raw).decode()
            result["artifactSha256"] = hashlib.sha256(raw).hexdigest()
        ack = json.loads(broker(config, "/v1/result", token(), result, 10000))
        if ack != {"accepted": True}:
            raise RuntimeError("Private result receipt unavailable")
        print("Private CI gate " + result["status"] + "; private receipt stored", flush=True)
        return 0 if rc == 0 else 1

def main():
    global PHASE
    PHASE = "config"
    config = json.loads(CONFIG.read_text())
    if (not re.fullmatch("[a-f0-9]{32}", config["job"])
        or not re.fullmatch("[a-f0-9]{40}", config["revision"])
        or not re.fullmatch("[a-f0-9]{40}", config["tree"])
        or config["kind"] not in ("preflight", "build")):
        raise RuntimeError("Invalid job config")
    PHASE = "anonymous-denial"
    require_http(config, "/v1/job", 401)
    PHASE = "oidc-token"
    assertion = token()
    PHASE = "oidc-claims"
    if config["kind"] == "preflight":
        segment = assertion.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))
        expected = {"iss":"https://token.actions.githubusercontent.com", "aud":AUDIENCE,
            "sub":"repo:alexlanderzander/hydra-CI-:ref:refs/heads/main", "repository":"alexlanderzander/hydra-CI-",
            "repository_id":"1466552945", "repository_owner_id":"162145428", "actor_id":"162145428",
            "ref":"refs/heads/main", "workflow_ref":"alexlanderzander/hydra-CI-/.github/workflows/hydra-build.yml@refs/heads/main",
            "runner_environment":"github-hosted", "sha":os.environ["GITHUB_SHA"], "workflow_sha":os.environ["GITHUB_SHA"]}
        print("Public identity checks:", json.dumps({k:str(claims.get(k))==v for k,v in expected.items()},sort_keys=True))
    PHASE = "broker-auth"
    job = json.loads(broker(config, "/v1/job", assertion))
    if (any(job.get(k) != config[k] for k in ("revision", "tree", "kind"))
        or type(job.get("partCount")) is not int or not 0 <= job["partCount"] <= 128):
        raise RuntimeError("Unexpected private job")
    if config["kind"] == "preflight":
        if job["partCount"] != 0:
            raise RuntimeError("Preflight must not access source")
        PHASE = "source-denial"
        require_http(config, "/v1/source/0", 404, assertion)
        receipt = {"revision": config["revision"], "kind": "preflight", "status": "passed",
                   "log": "Anonymous denied; signed exact-launcher OIDC accepted; source disabled."}
        PHASE = "receipt"
        if json.loads(broker(config, "/v1/result", token(), receipt, 10000)) != {"accepted": True}:
            raise RuntimeError("Preflight receipt unavailable")
        print("Hydra OIDC preflight passed; no private source transferred")
        return 0
    if job["partCount"] < 1:
        raise RuntimeError("Missing source parts")
    return build(config, job)

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        # Only a fixed phase and numeric HTTP status; no tracebacks, response body or tokens.
        phase = globals().get("PHASE", "initialization")
        status = exc.code if isinstance(exc, urllib.error.HTTPError) else 0
        print("Hydra private CI launcher failed: phase=" + phase + " HTTP=" + str(status))
        raise SystemExit(1)
