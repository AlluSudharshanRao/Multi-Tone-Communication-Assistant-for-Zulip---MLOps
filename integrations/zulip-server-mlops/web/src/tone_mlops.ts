import $ from "jquery";

import * as channel from "./channel.ts";
import {$t} from "./i18n.ts";

function summarize_variants(ml: Record<string, unknown>): string {
    const variants = ml.variants;
    if (!variants || typeof variants !== "object") {
        return JSON.stringify(ml, null, 2);
    }
    const lines: string[] = [];
    for (const [tone, body] of Object.entries(variants as Record<string, unknown>)) {
        let t = "";
        if (typeof body === "string") {
            t = body;
        } else if (body && typeof body === "object" && "text" in body) {
            t = String((body as {text?: unknown}).text ?? "");
        }
        lines.push(`${tone}: ${t}`);
    }
    const cr = ml.classifier_result;
    if (cr && typeof cr === "object") {
        const pred =
            (cr as {predicted_tone?: unknown}).predicted_tone ??
            (cr as {label?: unknown}).label;
        if (pred !== undefined) {
            lines.push(`(classifier: ${String(pred)})`);
        }
    }
    return lines.join("\n");
}

export function initialize(): void {
    if ($("#mlops-tone-suggestions-root").length > 0) {
        return;
    }

    const $root = $("<div/>", {
        id: "mlops-tone-suggestions-root",
        css: {margin: "4px 10px", fontSize: "13px"},
    });
    const $btn = $("<button>", {
        type: "button",
        class: "button small rounded",
        text: $t({defaultMessage: "Tone suggestions"}),
    });
    const $out = $("<pre/>", {
        css: {
            whiteSpace: "pre-wrap",
            maxHeight: "140px",
            overflow: "auto",
            display: "none",
            marginTop: "6px",
            fontSize: "12px",
            fontFamily: "inherit",
        },
    });
    $root.append($btn).append($out);
    $("textarea#compose-textarea").after($root);

    $btn.on("click", () => {
        const content = $("textarea#compose-textarea").val();
        if (typeof content !== "string" || !content.trim()) {
            $out.text($t({defaultMessage: "Type a message first."})).show();
            return;
        }
        $btn.prop("disabled", true);
        $out.hide().empty();
        void channel.post({
            url: "/json/messages/tone_suggestions",
            data: {content},
            success(response) {
                $btn.prop("disabled", false);
                const typed = response as {mlops_tone_response?: Record<string, unknown>};
                const tr = typed.mlops_tone_response;
                if (!tr) {
                    $out.text($t({defaultMessage: "No suggestions returned."})).show();
                    return;
                }
                $out.text(summarize_variants(tr)).show();
            },
            error(xhr) {
                $btn.prop("disabled", false);
                const msg = channel.xhr_error_message(
                    $t({defaultMessage: "Tone suggestions failed"}),
                    xhr,
                );
                $out.text(msg).show();
            },
        });
    });
}
