"""MLOps tone suggestions: authenticated JSON proxy to zulip-bridge /generate.

Copy into a fork of https://github.com/zulip/zulip at the same release as your
docker-zulip image (e.g. 11.6), register in zproject/urls.py (see patches/), and set
TONE_MLOPS_BRIDGE_URL in ZULIP_CUSTOM_SETTINGS (Helm values-secret / production_settings).
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.utils.translation import gettext as _

from zerver.lib.exceptions import JsonableError
from zerver.lib.response import json_success
from zerver.lib.typed_endpoint import typed_endpoint
from zerver.models import UserProfile

logger = logging.getLogger(__name__)

_MAX_CHARS = 2000

# Cluster-internal bridge URL must not go through HTTP(S)_PROXY (often returns 407).
_bridge_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@typed_endpoint
def tone_suggestions_backend(
    request: HttpRequest,
    user_profile: UserProfile,
    *,
    content: str,
) -> HttpResponse:
    bridge_url = str(getattr(settings, "TONE_MLOPS_BRIDGE_URL", "") or "").strip()
    if not bridge_url:
        raise JsonableError(_("Tone suggestions are not configured on this server."))

    text = (content or "").strip()
    if not text:
        raise JsonableError(_("Message text is empty."))
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS]

    payload = json.dumps(
        {
            "message_id": f"web-{user_profile.id}",
            "text": text,
            "message_type": "stream",
        }
    ).encode()

    req = urllib.request.Request(
        bridge_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _bridge_opener.open(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        if err_body:
            logger.warning(
                "tone_mlops: bridge/generator HTTP %s url=%s body=%s",
                e.code,
                bridge_url,
                err_body,
            )
        raise JsonableError(
            _("Tone service returned an error ({code}).").format(code=e.code),
        ) from e
    except urllib.error.URLError as e:
        raise JsonableError(_("Tone service temporarily unavailable.")) from e

    try:
        gen_json: dict[str, Any] = json.loads(raw.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise JsonableError(_("Invalid response from tone service.")) from e

    return json_success(request, data={"mlops_tone_response": gen_json})
