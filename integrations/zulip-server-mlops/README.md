# Zulip server fork: compose “Tone suggestions” (MLOps product integration)

Upstream reference: **[zulip/zulip](https://github.com/zulip/zulip)** tag **`11.6`** (match the major.minor of your [docker-zulip](https://github.com/zulip/docker-zulip) server image). This folder ships **drop-in files** and **`git apply` patches** so you can build a custom `zulip-server` image with:

- **`POST /json/messages/tone_suggestions`** — session-authenticated proxy to **`zulip-bridge`** `POST /generate` (same payload shape as the bridge uses for the generator).
- **Compose Web UI** — a **Tone suggestions** button under the compose textarea calling that JSON route (no cluster URLs in the browser).

AGPL-3.0 applies to a modified Zulip server; comply before you distribute images or offer a hosted fork.

## 1. Fork and checkout

```bash
git clone https://github.com/<you>/zulip.git
cd zulip
git fetch origin tag 11.6 --depth 1
git checkout 11.6
```

## 2. Copy server and web modules

From this MLOps repo (paths relative to repo root):

```bash
cp path/to/Multi-Tone-Communication-Assistant-for-Zulip---MLOps/integrations/zulip-server-mlops/zerver/views/tone_mlops.py zerver/views/
cp path/to/Multi-Tone-Communication-Assistant-for-Zulip---MLOps/integrations/zulip-server-mlops/web/src/tone_mlops.ts web/src/
```

## 3. Apply patches (Zulip 11.6 only)

```bash
git apply /path/to/integrations/zulip-server-mlops/patches/0001-zproject-urls-11.6.patch
git apply /path/to/integrations/zulip-server-mlops/patches/0002-web-compose_setup-11.6.patch
```

**Windows:** patch files must use **LF** newlines (Zulip sources are LF). This repo sets `patches/.gitattributes` so `git pull` keeps that. If `git apply` still fails, regenerate from the MLOps repo:

```bash
python integrations/zulip-server-mlops/scripts/write_patches_lf.py
```

If `git apply` reports offset/fuzz, re-diff against your exact tree and refresh the patches (line numbers move across releases).

## 4. Configure the bridge URL (Django)

Set **`TONE_MLOPS_BRIDGE_URL`** in the settings block your deployment uses. For **docker-zulip** on the same Kubernetes cluster as `ml-serving`, extend **`ZULIP_CUSTOM_SETTINGS`** in Helm (see commented example in [`k8s/zulip/values-chameleon.yaml`](../../k8s/zulip/values-chameleon.yaml)):

```python
TONE_MLOPS_BRIDGE_URL = "http://zulip-bridge.ml-serving.svc.cluster.local:8090/generate"
```

Requirements:

- The **Zulip application pod** must resolve and reach **`zulip-bridge`** (same cluster DNS, or replace with an internal Ingress URL).
- If the URL is unset, the API returns a clear error and the compose button still loads.

## 5. Build and publish the server image

Follow Zulip’s documentation for producing a **`zulip-server`**-compatible image for docker-zulip (release tooling changes over time; start from the upstream guide for your tag). Push to GHCR (or your registry), then set Helm **`image.repository`** / **`image.tag`** on the chart (see [`k8s/zulip/README.md`](../../k8s/zulip/README.md)).

## 6. Smoke test

1. Log in to the web app, open compose, type a sentence, click **Tone suggestions**.
2. Expect one **editable** draft per tone and a **Use** button; edit if you like, then **Use** copies that text into the main compose box (you can edit again before send).
3. The API returns **`mlops_tone_response`** echoing the generator payload (`variants`, `classifier_result`, etc.).
4. **`curl`** (with session cookie / API key) is optional; the web client uses the same **`/json/...`** session as other compose calls.

## Files in this folder

| Path | Role |
|------|------|
| `zerver/views/tone_mlops.py` | Django `typed_endpoint` proxy |
| `web/src/tone_mlops.ts` | Compose UI: `channel.post`, per-tone editable drafts + **Use** → compose |
| `patches/0001-zproject-urls-11.6.patch` | Register route in `zproject/urls.py` |
| `patches/0002-web-compose_setup-11.6.patch` | Wire UI in `web/src/compose_setup.js` |
