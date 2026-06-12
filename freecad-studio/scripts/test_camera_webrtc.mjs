/**
 * Headless WebRTC camera test against local backend + Creality K2.
 * Usage: node scripts/test_camera_webrtc.mjs [printer_ip]
 */
import { chromium } from "playwright";
import { spawn } from "child_process";
import http from "http";

const API = "http://127.0.0.1:8787";
const PRINTER_IP = process.argv[2] || "192.168.1.134";
const PYTHON = "C:\\Program Files\\FreeCAD 1.1\\bin\\python.exe";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND = path.join(__dirname, "..", "backend");

function waitForServer(timeoutMs = 45000) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      http
        .get(`${API}/api/status`, (res) => {
          res.resume();
          if (res.statusCode === 200) resolve();
          else retry();
        })
        .on("error", retry);
    };
    const retry = () => {
      if (Date.now() - start > timeoutMs) reject(new Error("Backend timeout"));
      else setTimeout(tick, 500);
    };
    tick();
  });
}

function startBackend() {
  return spawn(PYTHON, ["-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port=8787"], {
    cwd: BACKEND,
    windowsHide: true,
    stdio: "ignore",
  });
}

async function main() {
  let backend = null;
  try {
    await waitForServer(1500);
    console.log("Backend already running");
  } catch {
    console.log("Starting backend…");
    backend = startBackend();
    await waitForServer();
  }

  const browser = await chromium.launch({
    args: ["--disable-features=WebRtcHideLocalIpsWithMdns"],
  });
  const page = await browser.newPage();

  page.on("console", (msg) => {
    if (msg.type() === "error") console.log("PAGE ERR:", msg.text());
  });

  const url = `${API}/static/camera-viewer.html?ip=${encodeURIComponent(PRINTER_IP)}&t=${Date.now()}`;
  console.log("Opening", url);
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });

  const result = await page.waitForFunction(
    () => {
      const video = document.querySelector("video");
      const msg = document.getElementById("msg");
      if (video && !video.hidden && video.videoWidth > 0) {
        return { ok: true, mode: "live", width: video.videoWidth, height: video.videoHeight };
      }
      if (msg && /failed|timed out|error/i.test(msg.textContent || "")) {
        return { ok: false, mode: "error", text: msg.textContent };
      }
      return null;
    },
    { timeout: 25000 },
  );

  const value = await result.jsonValue();
  console.log("Result:", value);
  await browser.close();
  if (backend) backend.kill();

  if (!value?.ok) {
    process.exit(1);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
