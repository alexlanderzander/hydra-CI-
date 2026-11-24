"""Public Hydra access-boundary smoke test. No authentication or private source."""
import http.client
import ssl
from urllib.parse import urljoin, urlsplit

HOST = "hydra.asset-node.com"
ACCESS_HOST = "terrabid.cloudflareaccess.com"
# Read-only probes; POST compare is a search, not a rental or mutation.
PROBES = (
    ("GET", "/", None),
    ("GET", "/app.js", None),
    ("GET", "/index.html", None),
    ("GET", "/styles.css", None),
    ("GET", "/health", None),
    ("GET", "/v1/marketplace/suppliers", None),
    ("GET", "/v1/marketplace/lium", None),
    ("GET", "/v1/marketplace/providers", None),
    ("GET", "/v1/openapi.json", None),
    ("GET", "/swagger-client.js", None),
    ("GET", "/vendor/swagger-ui/swagger-ui-bundle.js", None),
    ("GET", "/vendor/swagger-ui/swagger-ui.css", None),
    ("POST", "/v1/marketplace/compare", b"{}"),
    ("GET", "/customer-templates.js", None),
    ("GET", "/v1/templates", None),
    ("GET", "/v1/runpod/serverless", None),
    ("GET", "/v1/runpod/pods", None),
    ("GET", "/v1/runpod/pods/nonexistent-ci-probe", None),
    ("GET", "/v1/runpod/serverless/nonexistent-ci-probe", None),
    ("GET", "/v1/runpod/gpu-pools", None),
    ("GET", "/v1/runpod/billing/serverless", None),
    ("GET", "/serverless-workspace.js", None),
    ("GET", "/v1/owner/session", None),
    ("GET", "/v1/lium/managed/status", None),
)

def access_blocked(status, location):
    if status in (401, 403):
        return True
    if status not in (302, 303, 307, 308) or not location:
        return False
    try:
        target = urlsplit(urljoin("https://" + HOST + "/", location))
        return (
            target.scheme == "https"
            and target.hostname in (HOST, ACCESS_HOST)
            and target.port in (None, 443)
            and target.username is None
            and target.password is None
            and target.path.startswith("/cdn-cgi/access/login")
            and (target.path == "/cdn-cgi/access/login" or target.path.startswith("/cdn-cgi/access/login/"))
        )
    except (ValueError, UnicodeError):
        return False

def probe(method, path, body):
    conn = http.client.HTTPSConnection(HOST, timeout=12, context=ssl.create_default_context())
    try:
        headers = {"Accept": "application/json", "User-Agent": "Hydra-public-CI/1.0"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=body, headers=headers)
        res = conn.getresponse()
        # Never follow or print redirect URLs, cookies, response headers or bodies.
        if not access_blocked(res.status, res.getheader("Location")):
            raise RuntimeError(f"Access boundary failed: {method} {path} returned HTTP {res.status}")
        print(f"PASS {method} {path} — HTTP {res.status}, access blocked")
    finally:
        conn.close()

def main():
    for method, path, body in PROBES:
        try:
            probe(method, path, body)
        except RuntimeError as exc:
            print(str(exc))
            return 1
        except (OSError, http.client.HTTPException, ValueError):
            print(f"FAIL {method} {path} — transport or TLS failure")
            return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
