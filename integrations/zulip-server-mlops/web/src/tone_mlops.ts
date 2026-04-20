import $ from "jquery";

import * as channel from "./channel.ts";
import {$t} from "./i18n.ts";

function variantBodyText(body: unknown): string {
    if (typeof body === "string") {
        return body;
    }
    if (body && typeof body === "object" && "text" in body) {
        return String((body as {text?: unknown}).text ?? "");
    }
    return "";
}

/** Renders editable fields + Use buttons; user can edit text before applying to compose. */
function renderToneResults($out: JQuery, ml: Record<string, unknown>): void {
    $out.empty();
    const variants = ml.variants;
    if (!variants || typeof variants !== "object") {
        $out.text(JSON.stringify(ml, null, 2));
        return;
    }

    $out.append(
        $("<div/>", {
            class: "mlops-tone-hint",
            text: $t({
                defaultMessage: "Edit a suggestion, then click Use to place it in your message.",
            }),
            css: {fontSize: "12px", opacity: "0.85", marginBottom: "8px"},
        }),
    );

    const $compose = $("textarea#compose-textarea");

    for (const [tone, body] of Object.entries(variants as Record<string, unknown>)) {
        const text = variantBodyText(body);
        const $row = $("<div/>", {
            class: "mlops-tone-suggestion-row",
            css: {marginBottom: "10px"},
        });

        $row.append(
            $("<label/>", {
                class: "mlops-tone-suggestion-label",
                for: `mlops-tone-draft-${tone}`,
                text: tone,
                css: {
                    display: "block",
                    fontWeight: 600,
                    textTransform: "capitalize",
                    marginBottom: "4px",
                },
            }),
        );

        const draftId = `mlops-tone-draft-${tone}`;
        const $edit = $("<textarea/>", {
            id: draftId,
            class: "mlops-tone-suggestion-draft",
            "aria-label": tone,
            rows: 3,
            spellcheck: "true",
            css: {
                width: "100%",
                maxWidth: "36rem",
                boxSizing: "border-box",
                resize: "vertical",
                fontFamily: "inherit",
                fontSize: "13px",
                lineHeight: "1.35",
                padding: "6px 8px",
            },
        });
        $edit.val(text);

        const $use = $("<button>", {
            type: "button",
            class: "button small rounded",
            text: $t({defaultMessage: "Use"}),
        });
        $use.on("click", () => {
            const v = $edit.val();
            if (typeof v === "string") {
                $compose.val(v);
                $compose.trigger("input");
            }
        });

        $row.append($edit).append(
            $("<div/>", {css: {marginTop: "4px"}}).append($use),
        );
        $out.append($row);
    }

    const cr = ml.classifier_result;
    if (cr && typeof cr === "object") {
        const pred =
            (cr as {predicted_tone?: unknown}).predicted_tone ??
            (cr as {label?: unknown}).label;
        if (pred !== undefined) {
            $out.append(
                $("<div/>", {
                    text: `(classifier: ${String(pred)})`,
                    css: {fontSize: "12px", opacity: "0.85", marginTop: "6px"},
                }),
            );
        }
    }
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
    const $out = $("<div/>", {
        class: "mlops-tone-suggestions-panel",
        css: {
            display: "none",
            marginTop: "6px",
            maxHeight: "320px",
            overflow: "auto",
            fontSize: "13px",
        },
    });
    $root.append($btn).append($out);
    $("textarea#compose-textarea").after($root);

    $btn.on("click", () => {
        const content = $("textarea#compose-textarea").val();
        if (typeof content !== "string" || !content.trim()) {
            $out.empty().text($t({defaultMessage: "Type a message first."})).show();
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
                renderToneResults($out, tr);
                $out.show();
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
