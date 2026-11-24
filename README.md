# Hydra CI (public, source-free)

This repository contains independent public black-box checks for the Hydra service.
It is separate from the private Hydra product source.

## Checks

- **Hydra public Access smoke**: validates the public probe, then tests the live HTTPS
  authentication boundary for the dashboard, script, catalog, and owner-session routes.
  Unauthenticated requests must be denied or redirected only to the known Access
  login. It never follows login redirects, authenticates, rents a GPU, or prints
  response contents, cookies or tokens.
- **Public health contract**: optional public JSON health check for a future
  intentionally public staging endpoint. Disabled until configured; the live
  Access-protected Hydra domain does not need an unauthenticated health endpoint.

The Access smoke runs on pushes to its configuration, manually, and every six hours.
Pull requests test only the public probe logic. Standard public GitHub-hosted runners
are free; larger runners, usage limits and other terms still apply.

## Project-specific OIDC broker

A separately configured hosted runner job verifies its exact immutable workflow identity with the Hydra broker. The current preflight is source-free. Only separately authorized build jobs may receive ephemeral private revision data; no private file, logs, token, artifact or cache is published by this repository. Full source-bearing builds remain subject to the project and GitHub usage terms and must not be used as unrelated compute.

## Security and release boundary

- Never commit, cache, publish or log private application source. The OIDC preflight is not a build.
- No private checkout credentials, Cloudflare storage secrets, customer data,
  private logs, build artifacts, caches, or provider keys.
- Public jobs have read-only repository permissions and no secret credentials.
- Full private checks require a separate authorized CI job and a private result receipt; public smoke checks alone never certify a private build.
- Public smoke success is not a substitute for full private tests or proof that a
  paid booking, authenticated session or new revision works. A failed private
  release gate remains failed.

## Run

Use Actions → Hydra public Access smoke → Run workflow, or run the independent
public checks locally:

```sh
python3 -m unittest discover -s checks -p 'test_*.py'
python3 checks/access_probe.py
```

If a separate public health endpoint is intentionally made available, configure
`HYDRA_PUBLIC_HEALTH_URL` under Settings → Secrets and variables → Actions → Variables.

No code, private build result or credential is transferred between repositories.
