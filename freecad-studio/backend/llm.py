"""Generate FreeCAD Python from a natural-language prompt."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import secrets_store as secrets

SKILL_FILE = Path(__file__).resolve().parent / "freecad_skill.md"

VISION_KEYWORDS = (
    "vl",
    "vision",
    "gemma4",
    "gemma3",
    "kimi-k2",
    "minimax-m3",
    "nemotron-3",
    "gemini-3",
    "qwen3.5",
    "qwen3.6",
    "ministral-3",
    "glm-ocr",
    "medgemma",
    "deepseek-ocr",
    "translategemma",
    "mistral-medium",
    "devstral-small-2",
)

MODEL_HINTS: dict[str, str] = {
    "qwen3-vl:235b-instruct": "Best vision — reads concept sketches & photos",
    "qwen3-vl:235b": "Strong vision model",
    "gemma4:31b": "Multimodal — good vision + reasoning",
    "kimi-k2.6": "Multimodal agent — vision + coding",
    "kimi-k2.5": "Vision + agentic coding",
    "qwen3.5:397b": "Large multimodal model",
    "gemini-3-flash-preview": "Fast vision model",
    "minimax-m3": "Coding + vision",
    "gpt-oss:120b": "Strong text — no image input",
    "gpt-oss:20b": "Fast text — no image input",
    "qwen3-coder:480b": "Best pure coding — no image input",
    "deepseek-v4-pro": "Very strong reasoning — no image input",
    "glm-5.1": "Large general model — no image input",
}

SYSTEM_PROMPT = """You are an expert mechanical CAD engineer writing Python for FreeCAD execute_code. Rules:
- Output ONLY executable Python code. No markdown fences, no explanations.
- Always: import FreeCAD as App, import Part. Use FreeCADGui as Gui only if needed for view.
- Never use if __name__ == "__main__".
- Create or use doc = App.activeDocument() or App.newDocument("Model").
- Units are millimeters.
- Include EVERY feature the user asked for — count them before you finish.
- Follow the modeling skill below exactly.
"""


def _load_skill() -> str:
    try:
        text = SKILL_FILE.read_text(encoding="utf-8").strip()
        return f"\n{text}\n" if text else ""
    except Exception:
        return ""


FIX_PROMPT = """The FreeCAD Python script below failed when executed. Fix it.
- Output ONLY the complete corrected Python script. No markdown fences, no explanations.
- Keep every feature and dimension from the original script; change only what is needed to make it run
  and produce valid solid geometry.
"""

FEATURE_EXTRACT_SYSTEM = """You extract a structured feature checklist from a CAD design request.
Study the text AND any reference image. List every distinct geometric feature the final model must have.

Respond with ONLY JSON, no markdown fences:
{
  "summary": "one sentence describing the part",
  "features": [
    {"name": "short id", "description": "what it is + key dimensions/angles", "priority": "required"}
  ]
}
Include: overall shape, every hole/slot/boss/lip/fillet, angles, connectivity requirements, approximate sizes.
"""

CRITIQUE_SYSTEM = """You are a strict CAD quality inspector doing VISUAL REASONING.

You MUST work through these steps IN ORDER before scoring:
1. READ the required feature checklist (from the user request).
2. LOOK at every attached image carefully:
   - If image 1 is labeled "User reference" — that is the TARGET appearance. The built model must match it.
   - Remaining images are multiview renders of what was ACTUALLY BUILT:
     isometric (always first), front/top/right/back exteriors, plus section cuts
     (SectionFront/SectionTop/SectionRight) showing internal geometry at mid-plane.
3. For EACH required feature, decide: present & correct | present but wrong | missing entirely.
   Use BOTH the renders AND the structured scene JSON (volumes, positions, object names).
4. Check connectivity: disconnected floating pieces = automatic fail.
5. If a reference image was provided, score how closely the built shape matches it (proportions, silhouette, key features).
6. Only approve if EVERY required feature is correct AND reference match (if any) is strong.

Respond with ONLY JSON, no markdown fences:
{
  "reasoning": "2-4 sentences: what you see in the renders vs what was requested",
  "feature_audit": [
    {
      "feature": "name from checklist",
      "status": "ok | wrong | missing",
      "expected": "what was asked",
      "observed": "what you see in the renders/scene data",
      "fix": "specific change needed, or empty if ok"
    }
  ],
  "reference_match": {
    "provided": <true if user reference image was attached>,
    "score": <0-100 how closely built model matches reference, 100 if no reference>,
    "notes": "shape/proportion differences vs reference"
  },
  "connectivity_ok": <true if one connected solid, no floating pieces>,
  "score": <0-100 overall>,
  "approved": <true ONLY if score>=85 AND every feature_audit status is ok AND connectivity_ok AND reference_match.score>=75>,
  "issues": ["actionable problem 1", "..."],
  "fix_instructions": "ordered list of exact geometry changes for the modeler, or empty if approved"
}
Be harsh: a simple box when a phone stand was requested = score below 30.
"""

CRITIQUE_FIX_PROMPT = """Your FreeCAD script built a model that FAILED visual inspection.
Study the attached images:
- "User reference" (if present) = target appearance
- Multiview renders = what your script actually produced (the problems are visible here)

Rewrite the COMPLETE script to fix EVERY issue in the feature audit.
- Output ONLY executable Python. No markdown fences, no explanations.
- Apply fix_instructions precisely. Do not drop features that were correct.
- Focus changes on MISSING/WRONG features only — do not rebuild unrelated geometry.
"""

FILLET_ESCALATION_SUFFIX = """
CRITICAL — previous fix attempts FAILED to add required fillets (still sharp in renders).
For each missing fillet/radius in the audit:
1. Apply makeFillet on the FINAL fused solid AFTER all booleans and holes.
2. Select edges by vertex position (see modeling skill edges_near pattern) — NOT by edge index.
3. Do NOT use bare `except: pass` on required fillets — retry at half radius, then quarter.
4. Print FILLET <name>: ok (N edges, r=R) or FILLET <name>: FAILED for each fillet.
5. If makeFillet still fails, round the corner using Part.makeCylinder cut or a Part.makeLoft arc profile.
The next inspection will check renders — sharp corners on requested fillets = automatic fail.
"""

VISION_PROMPT_SUFFIX = """
The user attached a reference image of a 3D concept (sketch, render, or photo).
Study its overall shape, proportions, key features, and approximate dimensions.
Recreate it as a printable FreeCAD solid model in millimeters.
If scale is unclear, pick sensible real-world dimensions and mention them in a print().
"""

EDIT_PROMPT_SUFFIX = """
The user wants to MODIFY an existing FreeCAD model using natural language — not start from scratch.
Input order (study in this sequence before writing code):
1. Pre-built multiview renders — spatial understanding of the current 3D reference
2. Structured scene data — JSON object list with volumes, positions, and feature dimensions
3. Current Python script — the executable source that produced the model
4. User change request — what to change in plain English

Rules for edits:
- Output the COMPLETE updated Python script (not a diff, not partial snippets).
- Apply only the requested changes; keep unrelated geometry and dimensions the same.
- Reuse doc = App.activeDocument() when a document already exists.
- Before recreating solids, remove old Part features from the document to avoid duplicates:
  for obj in list(doc.Objects):
      if getattr(obj, "Shape", None) and not obj.Shape.isNull():
          doc.removeObject(obj.Name)
- End with doc.recompute() and print() describing what changed.
"""

SCENE_PREVIEW_SUFFIX = """
Attached image(s) are pre-built renders of the current FreeCAD model.
Use them for spatial understanding before reading the structured data and Python script.
"""

MULTIVIEW_SCENE_SUFFIX = """
Attached images are PRE-BUILT MULTIVIEW RENDERS of the 3D reference (step 1 in the pipeline).
Image order — study all together for spatial understanding before structured data and Python:
{view_list}
First image is always isometric. Exterior views show outside faces; SectionFront/SectionTop/SectionRight
are mid-plane cuts revealing internal cavities, wall thickness, and hidden features.
Infer depth, wall thickness, hole positions, overhangs, and feature relationships across views.
Then use the structured JSON scene data and current Python script to apply accurate edits.
"""

DEFAULTS = {
    "ollama_cloud": {
        "api_url": "https://ollama.com",
        "model": "gpt-oss:120b",
        "label": "Ollama Cloud",
    },
    "ollama_local": {
        "api_url": "http://localhost:11434",
        "model": "gpt-oss:20b",
        "label": "Ollama Local",
    },
    "openai_compat": {
        "api_url": "https://api.x.ai/v1",
        "model": "grok-3-mini",
        "label": "OpenAI-compatible",
    },
}


def _extract_code(text: str) -> str:
    fenced = re.search(r"```(?:python)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def resolve_ai_config(cfg: dict[str, str] | None = None) -> dict[str, Any]:
    cfg = cfg or {}
    provider = (cfg.get("ai_provider") or os.environ.get("FREECAD_STUDIO_AI_PROVIDER") or "ollama_cloud").lower()
    defaults = DEFAULTS.get(provider, DEFAULTS["openai_compat"])

    api_url = cfg.get("api_url") or os.environ.get("FREECAD_STUDIO_API_URL") or defaults["api_url"]
    model = cfg.get("model") or os.environ.get("FREECAD_STUDIO_MODEL") or defaults["model"]
    label = defaults.get("label", provider)

    api_key = (
        secrets.get_secret(secrets.OLLAMA_KEY)
        or cfg.get("ollama_api_key")
        or cfg.get("api_key")
        or os.environ.get("OLLAMA_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
    )

    configured = provider == "ollama_local" or bool(api_key)

    return {
        "provider": provider,
        "api_url": api_url.rstrip("/"),
        "model": model,
        "api_key": api_key,
        "label": label,
        "configured": configured,
    }


def is_vision_model(model: str) -> bool:
    name = model.lower()
    return any(k in name for k in VISION_KEYWORDS)


def _http_get_json(url: str, headers: dict[str, str], timeout: float = 30) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI request failed ({exc.code}): {body}") from exc


def _http_json(url: str, payload: dict, headers: dict[str, str], timeout: float = 180) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI request failed ({exc.code}): {body}") from exc


def list_ai_models(cfg: dict[str, str] | None = None) -> dict[str, Any]:
    ai = resolve_ai_config(cfg)
    models: list[dict[str, Any]] = []

    if ai["provider"] in ("ollama_cloud", "ollama_local"):
        headers: dict[str, str] = {}
        if ai["api_key"]:
            headers["Authorization"] = f"Bearer {ai['api_key']}"
        try:
            data = _http_get_json(f"{ai['api_url']}/api/tags", headers)
            for item in data.get("models", []):
                name = item.get("name") or item.get("model") or ""
                if not name:
                    continue
                vision = is_vision_model(name)
                models.append(
                    {
                        "id": name,
                        "name": name,
                        "vision": vision,
                        "hint": MODEL_HINTS.get(name, "Vision model" if vision else "Text-only model"),
                        "size": item.get("size"),
                    }
                )
        except Exception as exc:
            return {
                "models": [],
                "current": ai["model"],
                "error": str(exc),
                "provider": ai["provider"],
            }

    models.sort(key=lambda m: (not m["vision"], m["name"]))
    vision_first = [
        "qwen3-vl:235b-instruct",
        "qwen3-vl:235b",
        "gemma4:31b",
        "kimi-k2.6",
        "qwen3.5:397b",
        "gemini-3-flash-preview",
    ]
    order = {name: i for i, name in enumerate(vision_first)}
    models.sort(key=lambda m: (order.get(m["id"], 999 if m["vision"] else 1000), m["name"]))

    return {
        "models": models,
        "current": ai["model"],
        "current_vision": is_vision_model(ai["model"]),
        "provider": ai["provider"],
        "label": ai["label"],
    }


def _build_user_prompt(
    prompt: str,
    existing_code: str | None = None,
    scene_context: str | None = None,
    *,
    scene_preview: bool = False,
) -> str:
    if not existing_code and not scene_context:
        return prompt

    parts: list[str] = []
    if scene_preview:
        parts.append(
            "Step 1 — Multiview renders are attached as images above. "
            "Study them first for 3D spatial understanding."
        )
    if scene_context:
        parts.append("Step 2 — Structured scene data (JSON):\n" + scene_context.strip())
    if existing_code:
        parts.append(
            "Step 3 — Current Python script:\n```python\n" + existing_code.strip() + "\n```"
        )
    parts.append("Step 4 — User change request:\n" + prompt.strip())
    return "\n\n".join(parts)


def _append_job_doc_suffix(system: str, job_doc_name: str | None) -> str:
    system += _load_skill()
    if not job_doc_name:
        return system
    from job_docs import job_doc_prompt_suffix

    return system + job_doc_prompt_suffix(job_doc_name)


def _call_ollama_chat(
    ai: dict[str, Any],
    prompt: str,
    images: list[str] | None = None,
    *,
    existing_code: str | None = None,
    scene_context: str | None = None,
    scene_preview: bool = False,
    scene_view_names: list[str] | None = None,
    job_doc_name: str | None = None,
) -> str:
    headers = {"Content-Type": "application/json"}
    if ai["api_key"]:
        headers["Authorization"] = f"Bearer {ai['api_key']}"

    system = _append_job_doc_suffix(SYSTEM_PROMPT, job_doc_name)
    if existing_code or scene_context:
        system += EDIT_PROMPT_SUFFIX
    if images:
        if scene_preview and scene_view_names and len(scene_view_names) > 1:
            view_lines = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(scene_view_names))
            system += MULTIVIEW_SCENE_SUFFIX.format(view_list=view_lines)
        elif scene_preview:
            system += SCENE_PREVIEW_SUFFIX
        else:
            system += VISION_PROMPT_SUFFIX
    user_text = _build_user_prompt(
        prompt, existing_code, scene_context, scene_preview=scene_preview
    )
    user_msg: dict[str, Any] = {"role": "user", "content": user_text}
    if images:
        user_msg["images"] = images

    payload = {
        "model": ai["model"],
        "messages": [
            {"role": "system", "content": system},
            user_msg,
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }

    data = _http_json(f"{ai['api_url']}/api/chat", payload, headers)
    message = data.get("message") or {}
    content = message.get("content", "")
    if not content:
        raise RuntimeError(f"Ollama returned no content: {data}")
    return _extract_code(content)


def _call_openai_compat(
    ai: dict[str, Any],
    prompt: str,
    images: list[str] | None = None,
    *,
    existing_code: str | None = None,
    scene_context: str | None = None,
    scene_preview: bool = False,
    scene_view_names: list[str] | None = None,
    job_doc_name: str | None = None,
) -> str:
    if not ai["api_key"]:
        raise RuntimeError("No AI API key configured.")

    system = _append_job_doc_suffix(SYSTEM_PROMPT, job_doc_name)
    if existing_code or scene_context:
        system += EDIT_PROMPT_SUFFIX
    if images:
        if scene_preview and scene_view_names and len(scene_view_names) > 1:
            view_lines = "\n".join(f"{i + 1}. {name}" for i, name in enumerate(scene_view_names))
            system += MULTIVIEW_SCENE_SUFFIX.format(view_list=view_lines)
        elif scene_preview:
            system += SCENE_PREVIEW_SUFFIX
        else:
            system += VISION_PROMPT_SUFFIX
    user_text = _build_user_prompt(
        prompt, existing_code, scene_context, scene_preview=scene_preview
    )
    if images:
        user_content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img_b64 in images:
            user_content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
            )
        user_message: dict[str, Any] = {"role": "user", "content": user_content}
    else:
        user_message = {"role": "user", "content": user_text}

    payload = {
        "model": ai["model"],
        "messages": [
            {"role": "system", "content": system},
            user_message,
        ],
        "temperature": 0.2,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {ai['api_key']}",
    }

    data = _http_json(f"{ai['api_url']}/chat/completions", payload, headers)
    content = data["choices"][0]["message"]["content"]
    return _extract_code(content)


def generate_freecad_code(
    prompt: str,
    cfg: dict[str, str] | None = None,
    api_key: str | None = None,
    images: list[str] | None = None,
    existing_code: str | None = None,
    scene_context: str | None = None,
    scene_preview: bool = False,
    scene_view_names: list[str] | None = None,
    job_doc_name: str | None = None,
) -> str:
    ai = resolve_ai_config(cfg)
    if api_key:
        ai["api_key"] = api_key

    if not ai["configured"]:
        raise RuntimeError(
            "No AI configured. For Ollama Cloud: create an API key at "
            "https://ollama.com/settings/keys and set OLLAMA_API_KEY or api_key in config.toml"
        )

    if images and not is_vision_model(ai["model"]):
        raise RuntimeError(
            f"Model '{ai['model']}' cannot read images. "
            "Pick a vision model (e.g. qwen3-vl:235b-instruct or gemma4:31b) in the AI Design panel."
        )

    kwargs = {
        "existing_code": existing_code,
        "scene_context": scene_context,
        "scene_preview": scene_preview,
        "scene_view_names": scene_view_names,
        "job_doc_name": job_doc_name,
    }
    if ai["provider"] in ("ollama_cloud", "ollama_local"):
        return _call_ollama_chat(ai, prompt, images=images, **kwargs)
    return _call_openai_compat(ai, prompt, images=images, **kwargs)


def fix_freecad_code(
    code: str,
    error: str,
    user_prompt: str | None = None,
    cfg: dict[str, str] | None = None,
    job_doc_name: str | None = None,
) -> str:
    """Ask the LLM to repair a failing script using the execution error."""
    ai = resolve_ai_config(cfg)
    if not ai["configured"]:
        raise RuntimeError("No AI configured — cannot auto-fix code.")

    parts = [FIX_PROMPT]
    if user_prompt:
        parts.append(f"Original user request:\n{user_prompt.strip()}")
    parts.append(f"Failing script:\n```python\n{code.strip()}\n```")
    parts.append(f"Execution error:\n{error.strip()}")
    fix_request = "\n\n".join(parts)

    if ai["provider"] in ("ollama_cloud", "ollama_local"):
        return _call_ollama_chat(ai, fix_request, job_doc_name=job_doc_name)
    return _call_openai_compat(ai, fix_request, job_doc_name=job_doc_name)


def _chat_raw(ai: dict[str, Any], system: str, user_text: str, images: list[str] | None = None) -> str:
    """Low-level chat call returning raw text (no code extraction)."""
    if ai["provider"] in ("ollama_cloud", "ollama_local"):
        headers = {"Content-Type": "application/json"}
        if ai["api_key"]:
            headers["Authorization"] = f"Bearer {ai['api_key']}"
        user_msg: dict[str, Any] = {"role": "user", "content": user_text}
        if images:
            user_msg["images"] = images
        payload = {
            "model": ai["model"],
            "messages": [{"role": "system", "content": system}, user_msg],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        data = _http_json(f"{ai['api_url']}/api/chat", payload, headers)
        return (data.get("message") or {}).get("content", "")

    if not ai["api_key"]:
        raise RuntimeError("No AI API key configured.")
    if images:
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img}"}})
        user_message: dict[str, Any] = {"role": "user", "content": content}
    else:
        user_message = {"role": "user", "content": user_text}
    payload = {
        "model": ai["model"],
        "messages": [{"role": "system", "content": system}, user_message],
        "temperature": 0.1,
    }
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {ai['api_key']}"}
    data = _http_json(f"{ai['api_url']}/chat/completions", payload, headers)
    return data["choices"][0]["message"]["content"]


def _parse_json_response(raw: str, label: str) -> dict[str, Any]:
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise RuntimeError(f"{label} returned no JSON: {raw[:300]}")
    return json.loads(match.group(0))


def extract_required_features(
    prompt: str,
    cfg: dict[str, str] | None = None,
    reference_image: str | None = None,
    *,
    context_images: list[str] | None = None,
    context_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Parse the user request (+ optional reference images) into a feature checklist."""
    ai = resolve_ai_config(cfg)
    if not ai["configured"]:
        raise RuntimeError("No AI configured — cannot extract features.")
    images: list[str] = []
    if reference_image:
        images.append(reference_image)
    if context_images:
        images.extend(context_images)
    if images and not is_vision_model(ai["model"]):
        images = []
    user_text = f"Design request:\n{prompt.strip()}"
    if images:
        label_lines: list[str] = []
        if reference_image:
            label_lines.append("Image 1 = User reference (target appearance).")
        offset = 1 if reference_image else 0
        for i, lbl in enumerate(context_labels or []):
            label_lines.append(f"Image {offset + i + 1} = {lbl}")
        user_text += "\n\nAttached images:\n" + "\n".join(label_lines)
    raw = _chat_raw(ai, FEATURE_EXTRACT_SYSTEM, user_text, images=images or None)
    data = _parse_json_response(raw, "Feature extraction")
    features = data.get("features") or []
    if not isinstance(features, list):
        features = []
    return {
        "summary": str(data.get("summary") or ""),
        "features": features,
    }


def _normalize_critique(crit: dict[str, Any], *, has_reference: bool) -> dict[str, Any]:
    """Enforce structured fields and recompute approval from feature audit."""
    crit["score"] = int(crit.get("score", 0))
    crit["reasoning"] = str(crit.get("reasoning") or "")
    crit["connectivity_ok"] = bool(crit.get("connectivity_ok", True))

    audit = crit.get("feature_audit") or []
    if not isinstance(audit, list):
        audit = []
    normalized_audit: list[dict[str, str]] = []
    for item in audit:
        if not isinstance(item, dict):
            continue
        normalized_audit.append({
            "feature": str(item.get("feature") or ""),
            "status": str(item.get("status") or "wrong"),
            "expected": str(item.get("expected") or ""),
            "observed": str(item.get("observed") or ""),
            "fix": str(item.get("fix") or ""),
        })
    crit["feature_audit"] = normalized_audit

    ref = crit.get("reference_match") or {}
    if not isinstance(ref, dict):
        ref = {}
    ref_score = int(ref.get("score", 100 if not has_reference else 0))
    crit["reference_match"] = {
        "provided": bool(ref.get("provided", has_reference)),
        "score": ref_score,
        "notes": str(ref.get("notes") or ""),
    }

    crit["issues"] = [str(i) for i in (crit.get("issues") or [])]
    crit["fix_instructions"] = str(crit.get("fix_instructions") or "")

    all_features_ok = all(
        a.get("status") == "ok" for a in normalized_audit
    ) if normalized_audit else True

    crit["approved"] = bool(
        crit.get("approved")
        and crit["score"] >= 85
        and all_features_ok
        and crit["connectivity_ok"]
        and (ref_score >= 75 if has_reference else True)
    )
    return crit


def critique_model(
    prompt: str,
    images: list[str],
    view_names: list[str],
    scene_context: str | None = None,
    cfg: dict[str, str] | None = None,
    *,
    reference_image: str | None = None,
    context_images: list[str] | None = None,
    context_labels: list[str] | None = None,
    required_features: dict[str, Any] | None = None,
    current_code: str | None = None,
) -> dict[str, Any]:
    """Vision inspection: compare built model to request + reference image + feature checklist."""
    ai = resolve_ai_config(cfg)
    if not ai["configured"]:
        raise RuntimeError("No AI configured — cannot critique.")
    if not is_vision_model(ai["model"]):
        raise RuntimeError(f"Model '{ai['model']}' has no vision — cannot inspect renders.")

    all_images: list[str] = []
    labels: list[str] = []
    if reference_image:
        all_images.append(reference_image)
        labels.append("User reference (TARGET — built model must match this)")
    if context_images:
        for img, lbl in zip(context_images, context_labels or []):
            all_images.append(img)
            labels.append(lbl)

    offset = len(all_images)
    for i, (img, name) in enumerate(zip(images, view_names)):
        all_images.append(img)
        labels.append(f"Built model — {name}")

    label_block = "\n".join(f"{i + 1}. {lbl}" for i, lbl in enumerate(labels))
    parts = [
        f"User request:\n{prompt.strip()}",
        f"Attached images in order:\n{label_block}",
    ]
    if required_features:
        parts.append(
            "Required feature checklist (audit EACH one):\n"
            + json.dumps(required_features, indent=2)
        )
    if current_code:
        parts.append(
            "Python script that produced the built model (check # Features comment vs reality):\n"
            f"```python\n{current_code.strip()}\n```"
        )
    if scene_context:
        parts.append(f"Structured scene data from FreeCAD:\n{scene_context.strip()}")

    if not all_images:
        parts.append(
            "NOTE: No render images available — base your inspection ONLY on "
            "structured scene JSON, Python code, and the feature checklist."
        )
    raw = _chat_raw(ai, CRITIQUE_SYSTEM, "\n\n".join(parts), images=all_images or None)
    crit = _normalize_critique(
        _parse_json_response(raw, "Critique"),
        has_reference=bool(reference_image),
    )
    return crit


def fix_from_critique(
    code: str,
    critique: dict[str, Any],
    user_prompt: str,
    cfg: dict[str, str] | None = None,
    job_doc_name: str | None = None,
    *,
    built_images: list[str] | None = None,
    built_view_names: list[str] | None = None,
    reference_image: str | None = None,
    required_features: dict[str, Any] | None = None,
    stagnation: bool = False,
) -> str:
    """Rewrite the script using vision — shows reference + broken renders to the model."""
    ai = resolve_ai_config(cfg)
    if not ai["configured"]:
        raise RuntimeError("No AI configured — cannot fix.")

    audit_lines = []
    for item in critique.get("feature_audit") or []:
        if item.get("status") != "ok":
            audit_lines.append(
                f"- {item.get('feature')}: {item.get('status')} — "
                f"expected {item.get('expected')}, saw {item.get('observed')}. "
                f"Fix: {item.get('fix')}"
            )
    if not audit_lines:
        audit_lines = [f"- {i}" for i in critique.get("issues", [])]

    parts = [CRITIQUE_FIX_PROMPT, f"Original user request:\n{user_prompt.strip()}"]
    if stagnation:
        parts.append(FILLET_ESCALATION_SUFFIX)
    if required_features:
        parts.append(f"Required features:\n{json.dumps(required_features, indent=2)}")
    parts.append(f"Current script:\n```python\n{code.strip()}\n```")
    parts.append(f"Feature audit failures (score {critique.get('score')}):\n" + "\n".join(audit_lines))
    if critique.get("fix_instructions"):
        parts.append(f"Fix instructions:\n{critique['fix_instructions']}")
    ref = critique.get("reference_match") or {}
    if ref.get("provided") and ref.get("notes"):
        parts.append(f"Reference image comparison: {ref['notes']}")

    all_images: list[str] = []
    view_labels: list[str] = []
    if reference_image:
        all_images.append(reference_image)
        view_labels.append("User reference")
    if built_images:
        for img, name in zip(built_images, built_view_names or []):
            all_images.append(img)
            view_labels.append(f"Built — {name}")
    if all_images:
        parts.append(
            "Attached images:\n"
            + "\n".join(f"{i + 1}. {n}" for i, n in enumerate(view_labels))
        )

    fix_request = "\n\n".join(parts)
    scene_preview = bool(all_images)
    kwargs = {
        "scene_preview": scene_preview,
        "scene_view_names": view_labels if scene_preview else None,
        "job_doc_name": job_doc_name,
    }
    if ai["provider"] in ("ollama_cloud", "ollama_local"):
        return _call_ollama_chat(ai, fix_request, images=all_images or None, **kwargs)
    return _call_openai_compat(ai, fix_request, images=all_images or None, **kwargs)


def lessons_prompt_suffix(lessons: list[dict[str, Any]]) -> str:
    """Format past-failure lessons for injection into the system prompt."""
    if not lessons:
        return ""
    lines = ["\nLESSONS FROM PAST SIMILAR BUILDS (avoid repeating these mistakes):"]
    for lesson in lessons:
        for issue in lesson.get("issues", []):
            lines.append(f"- {issue}")
    return "\n".join(lines) + "\n"