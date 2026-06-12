"""Creality K-series camera (WebRTC on port 8000)."""
from __future__ import annotations

import base64
import json

import requests

CAMERA_PORT = 8000
WEBRTC_PATH = "/call/webrtc_local"
SNAPSHOT_PATH = "/downloads/original/current_print_image.png"


def camera_urls(ip: str) -> dict[str, str]:
    base = f"http://{ip}:{CAMERA_PORT}"
    return {
        "page_url": f"{base}/",
        "webrtc_url": f"{base}{WEBRTC_PATH}",
        "snapshot_url": f"http://{ip}{SNAPSHOT_PATH}",
    }


def probe_camera(ip: str, timeout: float = 1.2) -> bool:
    try:
        response = requests.head(
            f"http://{ip}:{CAMERA_PORT}{WEBRTC_PATH}",
            timeout=timeout,
        )
        return response.status_code < 400
    except requests.RequestException:
        return False


def camera_info(ip: str) -> dict:
    available = probe_camera(ip)
    urls = camera_urls(ip) if available else {}
    return {
        "available": available,
        "type": "webrtc" if available else None,
        "port": CAMERA_PORT if available else None,
        **urls,
    }


def fix_creality_sdp(sdp: str, printer_ip: str | None = None) -> str:
    """Repair malformed duplicate-codec SDP returned by Creality K-series cameras."""
    lines = [line for line in sdp.replace("\r\n", "\n").split("\n") if line]
    out: list[str] = []
    in_video = False
    video_pt: str | None = None
    seen_rtpmap = False
    fmtp_lines: list[str] = []
    fmtp_insert_at = 0

    def flush_fmtp() -> None:
        nonlocal fmtp_lines, seen_rtpmap
        if not fmtp_lines:
            return
        preferred = next(
            (line for line in fmtp_lines if "packetization-mode" in line),
            fmtp_lines[0],
        )
        out.insert(fmtp_insert_at, preferred)
        fmtp_lines = []

    for line in lines:
        if line.startswith("m=video"):
            flush_fmtp()
            in_video = True
            seen_rtpmap = False
            fmtp_lines = []
            parts = line.split()
            payload_types = parts[3:] if len(parts) > 3 else []
            if len(payload_types) >= 2 and payload_types[0] != payload_types[1]:
                # K2 Plus: first codec entry is a decoy; keep the second.
                video_pt = payload_types[1]
            elif payload_types:
                video_pt = payload_types[0]
            else:
                video_pt = None
            if video_pt:
                parts = parts[:3] + [video_pt]
            line = " ".join(parts)
            out.append(line)
            fmtp_insert_at = len(out)
            continue

        if line.startswith("m="):
            flush_fmtp()
            in_video = False
            video_pt = None

        if in_video and video_pt:
            if line.startswith("a=rtpmap:"):
                pt = line.split(":", 1)[1].split()[0]
                if pt != video_pt or seen_rtpmap:
                    continue
                seen_rtpmap = True
            elif line.startswith("a=fmtp:"):
                if "x-google" in line:
                    continue
                pt = line.split(":", 1)[1].split()[0]
                if pt != video_pt:
                    continue
                fmtp_lines.append(line)
                continue

        if printer_ip and line.startswith("c=IN IP4 0.0.0.0"):
            line = f"c=IN IP4 {printer_ip}"

        out.append(line)

    flush_fmtp()

    text = "\r\n".join(out)
    return text if text.endswith("\r\n") else text + "\r\n"


def _decode_answer(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("Empty answer from printer")
    try:
        return json.loads(base64.b64decode(text))
    except (json.JSONDecodeError, ValueError):
        return json.loads(text)


def _encode_answer(answer: dict) -> str:
    return base64.b64encode(json.dumps(answer).encode()).decode()


def webrtc_exchange(ip: str, offer_b64: str, timeout: int = 15) -> str:
    url = f"http://{ip}:{CAMERA_PORT}{WEBRTC_PATH}"
    response = requests.post(
        url,
        data=offer_b64,
        headers={"Content-Type": "plain/text"},
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(
            f"WebRTC signaling failed ({response.status_code}): {response.text[:200]}"
        )

    try:
        answer = _decode_answer(response.text)
        if answer.get("type") == "answer" and answer.get("sdp"):
            answer["sdp"] = fix_creality_sdp(str(answer["sdp"]), ip)
            return _encode_answer(answer)
    except (ValueError, json.JSONDecodeError, KeyError):
        pass

    return response.text


def fetch_snapshot(ip: str, timeout: int = 10) -> tuple[bytes, str]:
    url = f"http://{ip}{SNAPSHOT_PATH}"
    response = requests.get(url, timeout=timeout)
    if response.status_code >= 400:
        raise RuntimeError(f"Snapshot failed ({response.status_code})")
    mime = response.headers.get("Content-Type", "image/png").split(";")[0].strip()
    return response.content, mime or "image/png"
