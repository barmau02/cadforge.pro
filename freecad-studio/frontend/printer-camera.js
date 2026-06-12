(() => {
  const box = document.getElementById("cameraBox");
  const snapshotEl = document.getElementById("printerSnapshot");
  const placeholderEl = document.getElementById("cameraPlaceholder");
  const statusEl = document.getElementById("cameraStatus");
  const reconnectBtn = document.getElementById("cameraReconnectBtn");
  const openBtn = document.getElementById("cameraOpenBtn");

  if (!box || !statusEl) return;

  let iframe = null;
  let snapshotTimer = null;
  let activeIp = null;
  let mode = "idle";

  function setStatus(text, state) {
    statusEl.textContent = text;
    statusEl.dataset.state = state || "";
  }

  function stopSnapshot() {
    if (snapshotTimer) {
      clearInterval(snapshotTimer);
      snapshotTimer = null;
    }
  }

  function removeIframe() {
    if (iframe) {
      iframe.remove();
      iframe = null;
    }
  }

  function stop() {
    removeIframe();
    stopSnapshot();
    if (snapshotEl) snapshotEl.hidden = true;
    mode = "idle";
    activeIp = null;
    if (placeholderEl) {
      placeholderEl.hidden = false;
      placeholderEl.textContent = "Connect printer on WiFi to view live feed";
    }
    setStatus("Offline", "off");
  }

  function startSnapshotFallback() {
    removeIframe();
    stopSnapshot();
    mode = "snapshot";
    if (placeholderEl) placeholderEl.hidden = true;
    if (snapshotEl) snapshotEl.hidden = false;
    setStatus("Snapshot only", "warn");

    const tick = () => {
      snapshotEl.src = `/api/printer/camera/snapshot?t=${Date.now()}`;
    };
    tick();
    snapshotTimer = setInterval(tick, 2500);
  }

  function startLiveFeed(ip) {
    stopSnapshot();
    if (placeholderEl) placeholderEl.hidden = true;
    if (snapshotEl) snapshotEl.hidden = true;
    removeIframe();

    iframe = document.createElement("iframe");
    iframe.className = "camera-iframe";
    iframe.title = "Printer live camera";
    iframe.allow = "autoplay; fullscreen";
    iframe.src = `/static/camera-viewer.html?ip=${encodeURIComponent(ip)}&t=${Date.now()}`;
    box.appendChild(iframe);

    mode = "live";
    activeIp = ip;
    setStatus("Connecting…", "busy");
  }

  window.addEventListener("message", (event) => {
    if (!event.data || typeof event.data !== "object") return;
    if (event.data.type === "camera-live") {
      setStatus("Live", "live");
    } else if (event.data.type === "camera-failed") {
      setStatus("Fallback", "warn");
      if (activeIp) startSnapshotFallback();
    }
  });

  function sync(status) {
    const ip = status?.printer_ip;
    const online = status?.printer_online;

    if (!online || !ip) {
      stop();
      return;
    }

    if (activeIp === ip && (mode === "live" || (mode === "snapshot" && snapshotTimer))) {
      return;
    }

    startLiveFeed(ip);
  }

  if (reconnectBtn) {
    reconnectBtn.addEventListener("click", () => {
      if (!activeIp) return;
      startLiveFeed(activeIp);
    });
  }

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      if (!activeIp) return;
      window.open(`http://${activeIp}:8000/?action=stream`, "_blank", "noopener");
    });
  }

  window.printerCamera = { sync, stop, reconnect: () => activeIp && startLiveFeed(activeIp) };
})();
