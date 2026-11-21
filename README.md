# Hydra CI (public, source-free)

This repository holds **only public black-box health checks** for Hydra. The product source, dependency files, unit tests and builds remain in the **private** `alexlanderzander/hydra` repository.

## Security boundary

- **Never** check out, download, decrypt, compile, or build the private Hydra source here.
- **Never** configure a private GitHub repository access token, Cloudflare R2 secret, payment provider secret, production API key or customer data here.
- No public artifacts, Actions caches, uploads, screenshots or debug logs of private code.
- Public workflows use **no secret credentials** and have `contents: read` only.
- Public checks target only an intentionally public, unauthenticated `/health` endpoint.
- Do not use Actions to evade GitHub's billing terms for private source builds. Private CI stays in the private repository.
- HTTPS is required for an external staging endpoint. For private staging, use Cloudflare Access and keep CI in the private repository instead.

## Setup

After deploying a staging API with an intentionally public `/health` endpoint:

1. Open **Settings → Secrets and variables → Actions → Variables** in this repository.
2. Add `HYDRA_PUBLIC_HEALTH_URL` pointing to your public HTTPS health endpoint, such as `https://staging.example.com/health`.
3. Run **Actions → Public health contract → Run workflow**, or let the scheduled check run.

The check runs without repository checkout, private source, external tokens or credentials. It confirms JSON output with `status: ok` and `service: hydra`. Without a configured URL, the remote job is skipped.

**No source code, build result, or secret is transferred between repositories — including via Cloudflare.**
