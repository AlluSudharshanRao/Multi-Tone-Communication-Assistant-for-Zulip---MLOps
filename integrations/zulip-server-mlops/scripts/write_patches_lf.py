"""Regenerate patch files with LF-only line endings (Windows-safe for git apply)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "patches"

def _w(name: str, lines: list[str]) -> None:
    (PATCH_DIR / name).write_bytes("\n".join(lines).encode("ascii") + b"\n")


def main() -> None:
    _w(
        "0001-zproject-urls-11.6.patch",
        [
            "diff --git a/zproject/urls.py b/zproject/urls.py",
            "--- a/zproject/urls.py",
            "+++ b/zproject/urls.py",
            "@@ -91,7 +91,8 @@",
            " )",
            " from zerver.views.message_report import report_message_backend",
            " from zerver.views.message_send import render_message_backend, send_message_backend, zcommand_backend",
            "+from zerver.views.tone_mlops import tone_suggestions_backend",
            " from zerver.views.message_summary import get_messages_summary",
            " from zerver.views.muted_users import mute_user, unmute_user",
            " from zerver.views.navigation_views import (",
            "     add_navigation_view,",
            "@@ -424,6 +425,7 @@",
            "         ),",
            "     ),",
            '     rest_path("messages/render", POST=render_message_backend),',
            '+    rest_path("messages/tone_suggestions", POST=tone_suggestions_backend),',
            '     rest_path("messages/flags", POST=update_message_flags),',
            '     rest_path("messages/flags/narrow", POST=update_message_flags_for_narrow),',
            '     rest_path("messages/<int:message_id>/history", GET=get_message_edit_history),',
        ],
    )
    _w(
        "0002-web-compose_setup-11.6.patch",
        [
            "diff --git a/web/src/compose_setup.js b/web/src/compose_setup.js",
            "--- a/web/src/compose_setup.js",
            "+++ b/web/src/compose_setup.js",
            "@@ -33,9 +33,10 @@ import * as stream_data from \"./stream_data.ts\";",
            ' import * as stream_settings_components from "./stream_settings_components.ts";',
            ' import * as sub_store from "./sub_store.ts";',
            ' import * as subscriber_api from "./subscriber_api.ts";',
            ' import {get_timestamp_for_flatpickr} from "./timerender.ts";',
            '+import * as tone_mlops from "./tone_mlops.ts";',
            ' import * as ui_report from "./ui_report.ts";',
            ' import * as upload from "./upload.ts";',
            ' import * as user_topics from "./user_topics.ts";',
            ' import * as widget_modal from "./widget_modal.ts";',
            " ",
            "@@ -63,7 +64,9 @@",
            '     $(".compose-control-buttons-container .audio_link").toggle(',
            "         compose_call.compute_show_audio_chat_button(),",
            "     );",
            " ",
            "+    tone_mlops.initialize();",
            "+",
            '     $("textarea#compose-textarea").on("keydown", (event) => {',
            '         compose_ui.handle_keydown(event, $("textarea#compose-textarea").expectOne());',
            "     });",
        ],
    )
    for name in ("0001-zproject-urls-11.6.patch", "0002-web-compose_setup-11.6.patch"):
        data = (PATCH_DIR / name).read_bytes()
        assert b"\r" not in data, name
    print("OK: patches are LF-only")


if __name__ == "__main__":
    main()
