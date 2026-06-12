"""Expand visual context from a user reference image using Grok Imagine."""
from __future__ import annotations

from typing import Any

from grok_image import edit_image, resolve_grok_config

ISO_LABEL = "generated_isometric"

# Shared constraint block — Grok often invents extra holes / wrong silhouettes without this.
GEOMETRY_LOCK = (
    " CRITICAL: This is one physical object — only the camera moves. "
    "Do NOT add, remove, relocate, or resize holes, posts, tabs, slots, or base features. "
    "Do NOT change the silhouette, part count, or overall proportions. "
    "Photorealistic product render, white background, no text or labels."
)

# label, human title, Grok edit prompt (isometric uses user photo; others chain from isometric)
BOOTSTRAP_VIEWS: list[tuple[str, str, str]] = [
    (
        ISO_LABEL,
        "Isometric",
        "Create an isometric 3/4 view of the exact object in the reference photo. "
        "Match every visible hole, post, tab, and base feature."
        + GEOMETRY_LOCK,
    ),
    (
        "generated_rear",
        "Rear",
        "Show a true rear orthographic view of this exact same object."
        + GEOMETRY_LOCK,
    ),
    (
        "generated_top",
        "Top",
        "Show a true top-down orthographic view of this exact same object."
        + GEOMETRY_LOCK,
    ),
    (
        "generated_right",
        "Right",
        "Show a true right-side orthographic view of this exact same object."
        + GEOMETRY_LOCK,
    ),
]

GLOBAL_CONTEXT_HINT = (
    "Describe the object explicitly — e.g. T-shaped bracket, centered vertical post with one hole, "
    "two mounting holes in base, blue plastic, ~80 mm wide. Grok views are approximate; "
    "uncheck any bad preview before build."
)

ON_DEMAND_PROMPT = (
    "Same object as the reference image. {detail} "
    "Keep all holes, posts, and silhouette identical to the reference."
    + GEOMETRY_LOCK
)


def bootstrap_view_defaults() -> list[dict[str, Any]]:
    return [
        {"label": label, "title": title, "prompt": prompt, "enabled": True}
        for label, title, prompt in BOOTSTRAP_VIEWS
    ]


def compose_grok_prompt(prompt: str, global_context: str | None = None) -> str:
    base = (prompt or "").strip()
    extra = (global_context or "").strip()
    if not extra:
        return base
    return f"{base} User context: {extra}"


def _resolve_view_specs(
    view_specs: list[dict[str, Any]] | None,
    *,
    only_label: str | None = None,
) -> list[tuple[str, str]]:
    """Return (label, prompt) pairs to generate."""
    specs = view_specs if view_specs else bootstrap_view_defaults()
    out: list[tuple[str, str]] = []
    for spec in specs:
        if not spec.get("enabled", True):
            continue
        label = str(spec.get("label") or "").strip()
        prompt = str(spec.get("prompt") or "").strip()
        if not label or not prompt:
            continue
        if only_label and label != only_label:
            continue
        out.append((label, prompt))
    return out


def _order_for_chain(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Isometric first so orthographic views can chain from one consistent render."""
    iso = next((p for p in pairs if p[0] == ISO_LABEL), None)
    rest = [p for p in pairs if p[0] != ISO_LABEL]
    if iso:
        return [iso, *rest]
    return pairs


def _edit_one(
    *,
    source_b64: str,
    prompt: str,
    cfg: dict[str, str] | None,
    mime: str,
    label: str,
    global_context: str,
) -> dict[str, Any]:
    full_prompt = compose_grok_prompt(prompt, global_context)
    try:
        images = edit_image(
            source_b64=source_b64,
            prompt=full_prompt,
            cfg=cfg,
            mime=mime,
        )
        if images:
            return {
                "label": label,
                "base64": images[0],
                "source": "generated_hypothesis",
                "prompt": full_prompt,
            }
        return {
            "label": label,
            "base64": "",
            "prompt": full_prompt,
            "error": "Grok returned no image",
        }
    except Exception as exc:
        return {
            "label": label,
            "base64": "",
            "prompt": full_prompt,
            "error": str(exc),
        }


def _generate_views(
    source_b64: str,
    cfg: dict[str, str] | None,
    *,
    mime: str = "image/png",
    pairs: list[tuple[str, str]],
    global_context: str = "",
    chain_anchor_b64: str | None = None,
    chain_anchor_mime: str | None = None,
    include_errors: bool = True,
) -> list[dict[str, Any]]:
    """
    Generate views. Isometric is rendered from the user photo; other views chain from
    the isometric (or chain_anchor) so angles stay consistent.
    """
    if not pairs:
        return []

    ordered = _order_for_chain(pairs)
    results: list[dict[str, Any]] = []
    anchor_b64 = source_b64
    anchor_mime = mime
    chain_ready = False

    for label, prompt in ordered:
        if label == ISO_LABEL:
            edit_source = source_b64
            edit_mime = mime
        elif chain_anchor_b64 and label != ISO_LABEL and len(ordered) == 1:
            edit_source = chain_anchor_b64
            edit_mime = chain_anchor_mime or mime
        elif chain_ready:
            edit_source = anchor_b64
            edit_mime = anchor_mime
        else:
            edit_source = source_b64
            edit_mime = mime

        entry = _edit_one(
            source_b64=edit_source,
            prompt=prompt,
            cfg=cfg,
            mime=edit_mime,
            label=label,
            global_context=global_context,
        )
        results.append(entry)

        if entry.get("base64"):
            if label == ISO_LABEL or not chain_ready:
                anchor_b64 = str(entry["base64"])
                anchor_mime = mime
                chain_ready = True

    if include_errors:
        return results
    return [r for r in results if r.get("base64")]


def bootstrap_context_images(
    source_b64: str,
    cfg: dict[str, str] | None = None,
    *,
    mime: str = "image/png",
    max_views: int = 4,
    view_specs: list[dict[str, Any]] | None = None,
    global_context: str = "",
    only_label: str | None = None,
) -> list[dict[str, str]]:
    """Generate supplemental views from one user image. Returns labeled context entries."""
    grok = resolve_grok_config(cfg)
    if not grok["configured"] or not grok["enabled"]:
        return []

    pairs = _resolve_view_specs(view_specs, only_label=only_label)
    if not only_label:
        pairs = pairs[: max(0, min(max_views, 4))]

    return _generate_views(
        source_b64,
        cfg,
        mime=mime,
        pairs=pairs,
        global_context=global_context,
        include_errors=False,
    )  # type: ignore[return-value]


def generate_context_previews(
    source_b64: str,
    cfg: dict[str, str] | None = None,
    *,
    mime: str = "image/png",
    view_specs: list[dict[str, Any]] | None = None,
    global_context: str = "",
    only_label: str | None = None,
    chain_anchor_b64: str | None = None,
    chain_anchor_mime: str | None = None,
) -> list[dict[str, Any]]:
    """Like bootstrap_context_images but returns every view attempt (including errors)."""
    grok = resolve_grok_config(cfg)
    if not grok["configured"]:
        return [{"label": "error", "base64": "", "error": "Grok API key not configured"}]
    if not grok["enabled"]:
        return [{"label": "error", "base64": "", "error": "Grok image expansion disabled in Settings"}]

    pairs = _resolve_view_specs(view_specs, only_label=only_label)
    if not only_label:
        pairs = pairs[:4]

    return _generate_views(
        source_b64,
        cfg,
        mime=mime,
        pairs=pairs,
        global_context=global_context,
        chain_anchor_b64=chain_anchor_b64,
        chain_anchor_mime=chain_anchor_mime,
        include_errors=True,
    )


def context_pool_from_entries(
    primary_b64: str | None,
    entries: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """Build image list + labels for vision LLM calls from pre-generated entries."""
    images: list[str] = []
    labels: list[str] = []
    kept: list[dict[str, Any]] = []
    if primary_b64:
        images.append(primary_b64)
        labels.append("User reference (original upload)")
    for entry in entries:
        b64 = entry.get("base64")
        if not b64:
            continue
        images.append(b64)
        labels.append(
            f"Generated context — {entry.get('label', 'view')} (approximate, not measured)"
        )
        kept.append(entry)
    return images, labels, kept


def expand_from_critique(
    source_b64: str,
    critique: dict[str, Any],
    cfg: dict[str, str] | None = None,
    *,
    mime: str = "image/png",
    existing_labels: set[str] | None = None,
) -> list[dict[str, str]]:
    """Agent-triggered: one extra image when reference match is weak or features are ambiguous."""
    grok = resolve_grok_config(cfg)
    if not grok["configured"] or not grok["enabled"]:
        return []

    ref = critique.get("reference_match") or {}
    ref_score = int(ref.get("score", 100))
    missing = [
        a for a in (critique.get("feature_audit") or [])
        if isinstance(a, dict) and a.get("status") in ("wrong", "missing")
    ]
    if ref_score >= 70 and len(missing) < 2:
        return []

    detail_parts: list[str] = []
    if ref.get("notes"):
        detail_parts.append(str(ref["notes"]))
    for item in missing[:2]:
        detail_parts.append(
            f"Clarify {item.get('feature')}: expected {item.get('expected')}, observed {item.get('observed')}"
        )
    if not detail_parts:
        detail_parts.append("Show an additional angle that clarifies overall shape and key features")

    label = "generated_clarify"
    if existing_labels and label in existing_labels:
        label = "generated_clarify_2"

    prompt = ON_DEMAND_PROMPT.format(detail=" ".join(detail_parts))
    try:
        images = edit_image(source_b64=source_b64, prompt=prompt, cfg=cfg, mime=mime)
        if not images:
            return []
        return [
            {
                "label": label,
                "base64": images[0],
                "source": "generated_hypothesis",
                "prompt": prompt,
            }
        ]
    except Exception as exc:
        return [{"label": label, "base64": "", "source": "generated_hypothesis", "error": str(exc)}]


def context_pool_for_vision(
    primary_b64: str | None,
    generated: list[dict[str, str]],
) -> tuple[list[str], list[str]]:
    """Build image list + human labels for vision LLM calls."""
    images: list[str] = []
    labels: list[str] = []
    if primary_b64:
        images.append(primary_b64)
        labels.append("User reference (original upload)")
    for entry in generated:
        b64 = entry.get("base64")
        if not b64:
            continue
        images.append(b64)
        labels.append(f"Generated context — {entry.get('label', 'view')} (approximate, not measured)")
    return images, labels
