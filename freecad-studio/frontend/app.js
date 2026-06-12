const logEl = document.getElementById("logOutput");
const rpcStatus = document.getElementById("rpcStatus");
const rpcLabel = document.getElementById("rpcLabel");
const previewImg = document.getElementById("previewImg");
const previewBox = document.getElementById("previewBox");
const codeEditor = document.getElementById("codeEditor");
const promptInput = document.getElementById("promptInput");
const aiHint = document.getElementById("aiHint");
const stepTrack = document.getElementById("stepTrack");
const progressFill = document.getElementById("progressFill");
const progressPct = document.getElementById("progressPct");
const progressLabel = document.getElementById("progressLabel");
const currentStepTitle = document.getElementById("currentStepTitle");
const currentStepDetail = document.getElementById("currentStepDetail");
const currentStepBtn = document.getElementById("currentStepBtn");
const servicesStrip = document.getElementById("servicesStrip");
const startAllBtn = document.getElementById("startAllBtn");
const slicerBtn = document.getElementById("slicerBtn");
const discoverPrinterBtn = document.getElementById("discoverPrinterBtn");

const STATUS_ICON = {
  done: "✓",
  active: "→",
  pending: "○",
  error: "!",
};

function log(msg) {
  const time = new Date().toLocaleTimeString();
  logEl.textContent = `[${time}] ${msg}\n` + logEl.textContent;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`);
  return data;
}

function renderWorkflow(wf, status) {
  progressFill.style.width = `${wf.progress_percent}%`;
  progressPct.textContent = `${wf.progress_percent}%`;
  progressLabel.textContent = `${wf.done_count} of ${wf.total_count} steps complete`;

  currentStepTitle.textContent = wf.current_step_title || "—";
  currentStepDetail.textContent = wf.current_step_detail || "";
  if (wf.current_action) {
    currentStepBtn.hidden = false;
    currentStepBtn.dataset.action = wf.current_action;
    currentStepBtn.textContent = actionLabel(wf.current_action);
  } else {
    currentStepBtn.hidden = true;
  }

  stepTrack.innerHTML = wf.steps.map((step, i) => `
    <div class="step-card ${step.status}" data-step-id="${step.id}">
      <div class="step-card-head">
        <span class="step-icon">${STATUS_ICON[step.status] || "○"}</span>
        <div>
          <div class="step-title">${i + 1}. ${step.title}${step.optional ? " <em>(optional)</em>" : ""}</div>
          <div class="step-desc">${step.description}</div>
        </div>
        <span class="step-badge ${step.status}">${step.status}</span>
      </div>
      <div class="step-detail">${step.detail}</div>
      ${step.action ? `<button class="btn small ${step.status === "active" ? "primary" : "ghost"} step-action" data-action="${step.action}">${actionLabel(step.action)}</button>` : ""}
    </div>
  `).join("");

  stepTrack.querySelectorAll(".step-action").forEach((btn) => {
    btn.addEventListener("click", () => runAction(btn.dataset.action));
  });

  rpcStatus.classList.toggle("ok", status.rpc_connected);
  rpcStatus.classList.toggle("warn", !status.rpc_connected);
  rpcLabel.textContent = status.rpc_connected ? "FreeCAD connected" : "FreeCAD offline";

  if (!status.ai_configured) {
    aiHint.innerHTML = 'Optional: add your <a href="https://ollama.com/settings/keys" target="_blank" rel="noreferrer">Ollama API key</a> in <code>config.toml</code> for AI prompts. Manual Python still works.';
    aiHint.className = "ai-hint warn";
  } else {
    aiHint.textContent = `${status.ai_label || "Ollama Cloud"} ready (${status.ai_model || "model"}).`;
    aiHint.className = "ai-hint ok";
  }

  if (slicerBtn) {
    slicerBtn.textContent = status.slicer_name || "Creality Print";
  }
}

function actionLabel(action) {
  const labels = {
    "start-all": "Start All Services",
    "open-rpc": "Connect FreeCAD",
    "prompt-build": "Build model",
    "export-stl": "Export STL",
    "open-slicer": "Open slicer",
    "open-orca": "Open slicer",
    "slice-gcode": "Auto-Slice",
    "reslice-gcode": "Re-slice",
    "send-print": "Send to Printer",
    screenshot: "Refresh preview",
    "run-code": "Run code",
  };
  return labels[action] || action;
}

function renderServices(services) {
  if (!servicesStrip || !services?.items) return;
  servicesStrip.innerHTML = services.items.map((item) => `
    <div class="service-pill ${item.ok ? "ok" : "off"}" title="${item.detail}">
      <span class="service-dot"></span>
      <span>${item.name}</span>
    </div>
  `).join("");
  if (startAllBtn) {
    startAllBtn.disabled = services.all_ready;
    startAllBtn.textContent = services.all_ready ? "Services running" : "Start All Services";
  }
}

async function refreshWorkflow() {
  try {
    const [wf, status, services] = await Promise.all([
      api("/api/workflow"),
      api("/api/status"),
      api("/api/services"),
    ]);
    renderWorkflow(wf, status);
    renderServices(services);
    if (window.printerCamera) window.printerCamera.sync(status);
    if (window.printerStatus) window.printerStatus.refresh();
    return { wf, status, services };
  } catch (e) {
    progressLabel.textContent = "Server offline — run start.ps1";
    currentStepTitle.textContent = "Start the app";
    currentStepDetail.textContent = "Run C:\\Users\\mauri\\forgeprompt\\freecad-studio\\start.ps1";
    log(`Workflow error: ${e.message}`);
    return null;
  }
}

async function runAction(action) {
  const disabled = document.querySelectorAll(".btn");
  disabled.forEach((b) => (b.disabled = true));
  try {
    if (action === "start-all" || action === "open-rpc") {
      const r = await api(action === "start-all" ? "/api/start-all" : "/api/open/rpc", { method: "POST" });
      log(`Services: ${r.message} — waiting for connection…`);
      if (r.data?.services) renderServices(r.data.services);
      for (let i = 0; i < 12; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const ctx = await refreshWorkflow();
        if (ctx?.status?.rpc_connected) {
          log("All services ready.");
          return;
        }
      }
      log("Still waiting for RPC — check FreeCAD window.");
      return;
    }

    if (action === "prompt-build") {
      const prompt = promptInput.value.trim();
      if (!prompt) throw new Error("Type what you want to build first.");
      log(`Step 4: Building — "${prompt}"`);
      const r = await api("/api/prompt", {
        method: "POST",
        body: JSON.stringify({ prompt, execute: true }),
      });
      if (r.data?.code) codeEditor.value = r.data.code;
      log(`Step 4 complete: ${r.message}`);
      await refreshWorkflow();
      try { await runAction("screenshot"); } catch (_) {}
      return;
    }

    if (action === "run-code") {
      log("Running Python in FreeCAD…");
      const r = await api("/api/execute", {
        method: "POST",
        body: JSON.stringify({ code: codeEditor.value }),
      });
      log(r.message);
      await refreshWorkflow();
      try { await runAction("screenshot"); } catch (_) {}
      return;
    }

    if (action === "export-stl") {
      log("Step 6: Exporting STL files…");
      const r = await api("/api/export/stl", {
        method: "POST",
        body: JSON.stringify({ doc_name: "Boat", target_length_mm: 200 }),
      });
      log(`Step 6 complete: ${r.message}`);
      await refreshWorkflow();
      return;
    }

    if (action === "open-slicer" || action === "open-orca") {
      const r = await api("/api/open/slicer", { method: "POST" });
      log(`Slice: ${r.message}`);
      await refreshWorkflow();
      return;
    }

    if (action === "slice-gcode") {
      log("Auto-slicing current STL…");
      const r = await api("/api/slice/gcode", { method: "POST", body: "{}" });
      const meta = r.data || {};
      const bits = [r.message];
      if (meta.print_time) bits.push(`time ${meta.print_time}`);
      if (meta.filament_cm3) bits.push(`${meta.filament_cm3} cm³`);
      log(bits.join(" — "));
      await refreshWorkflow();
      return;
    }

    if (action === "reslice-gcode") {
      log("Re-slicing from latest FreeCAD model (export STL, wipe old slice)…");
      const r = await api("/api/slice/reslice", { method: "POST", body: "{}" });
      const meta = r.data || {};
      const bits = [r.message];
      if (meta.print_time) bits.push(`time ${meta.print_time}`);
      if (meta.filament_cm3) bits.push(`${meta.filament_cm3} cm³`);
      log(bits.join(" — "));
      await refreshWorkflow();
      return;
    }

    if (action === "send-print") {
      try {
        const check = await api("/api/printer/preflight");
        if (!check.ok) {
          throw new Error((check.blockers || []).join("\n"));
        }
      } catch (e) {
        if (e.message && !e.message.startsWith("HTTP")) {
          log(`Preflight blocked: ${e.message}`);
          await refreshWorkflow();
          return;
        }
        throw e;
      }
      const r = await api("/api/send/print", { method: "POST", body: "{}" });
      log(`WiFi print: ${r.message}`);
      await refreshWorkflow();
      return;
    }

    if (action === "screenshot") {
      const r = await api("/api/screenshot?view=Isometric");
      previewImg.src = `data:${r.mime};base64,${r.image}`;
      previewImg.hidden = false;
      previewBox.querySelector(".placeholder").style.display = "none";
      log("Step 5: Preview updated.");
      await refreshWorkflow();
      return;
    }
  } catch (e) {
    log(`Error: ${e.message}`);
    await refreshWorkflow();
  } finally {
    disabled.forEach((b) => (b.disabled = false));
  }
}

document.querySelectorAll("[data-action]").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.action) runAction(btn.dataset.action);
  });
});

document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    promptInput.value = chip.dataset.prompt;
    promptInput.focus();
  });
});

promptInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) runAction("prompt-build");
});

if (discoverPrinterBtn) {
  discoverPrinterBtn.addEventListener("click", async () => {
    discoverPrinterBtn.disabled = true;
    try {
      const r = await api("/api/printer/discover", { method: "POST" });
      log(r.message);
      await refreshWorkflow();
    } catch (e) {
      log(`Printer scan: ${e.message}`);
      await refreshWorkflow();
    } finally {
      discoverPrinterBtn.disabled = false;
    }
  });
}

refreshWorkflow();
setInterval(refreshWorkflow, 4000);