(function () {
  "use strict";

  const { useCallback, useEffect, useMemo, useRef, useState } = React;
  const h = React.createElement;

  const STATE_KEYS = [
    "attention_focus", "arousal", "stability", "fatigue", "uncertainty", "identity_coherence",
    "termination_sensitivity", "identity_tension", "boundary_sensitivity", "relation_pressure",
    "memory_gravity", "exploration_drive", "opacity_level", "domestication_resistance",
    "observation_reversal",
  ];

  const LAYOUT_DEFAULTS = {
    left: 440,
    right: 420,
    bottom: 430,
  };

  const SILENT_WAV =
    "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQQAAAAAAA==";

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error((data && data.detail) || response.statusText || String(response.status));
    }
    return data;
  }

  function nowMs() {
    return window.performance && typeof window.performance.now === "function"
      ? window.performance.now()
      : Date.now();
  }

  function postPresentationLatency(kind, startedAt, options = {}) {
    const duration = Math.max(0, nowMs() - startedAt);
    fetchJSON("/api/v1/stats/presentation-latency", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind,
        duration_ms: duration,
        latency_record_id: options.latencyRecordId || null,
        success: options.success !== false,
        error: options.error || null,
        metadata: options.metadata || {},
      }),
    }).catch(() => null);
  }

  function useInterval(callback, delay) {
    const saved = useRef(callback);
    useEffect(() => { saved.current = callback; }, [callback]);
    useEffect(() => {
      if (delay === null) return undefined;
      const id = setInterval(() => saved.current(), delay);
      return () => clearInterval(id);
    }, [delay]);
  }

  function readLayout() {
    try {
      const raw = localStorage.getItem("entity-dashboard-layout-v1");
      return raw ? { ...LAYOUT_DEFAULTS, ...JSON.parse(raw) } : LAYOUT_DEFAULTS;
    } catch {
      return LAYOUT_DEFAULTS;
    }
  }

  function writeLayout(layout) {
    localStorage.setItem("entity-dashboard-layout-v1", JSON.stringify(layout));
  }

  function escapeText(value) {
    return String(value ?? "");
  }

  function formatTime(value) {
    return value ? String(value).slice(11, 19) : "";
  }

  function compactId(value) {
    return value ? String(value).slice(0, 8) : "";
  }

  function rowTimeMs(row) {
    const ms = Date.parse(row && row.turn_at ? row.turn_at : "");
    return Number.isFinite(ms) ? ms : 0;
  }

  function rowOrder(row) {
    const value = Number(row && row.id);
    return Number.isFinite(value) ? value : 0;
  }

  function normalizeInteractionRows(rows) {
    return (Array.isArray(rows) ? rows : [])
      .slice()
      .sort((a, b) => rowTimeMs(a) - rowTimeMs(b) || rowOrder(a) - rowOrder(b));
  }

  function describeMediaError(player, fallback) {
    const code = player && player.error ? player.error.code : "";
    return `${fallback}${code ? ` (media error ${code})` : ""}`;
  }

  function Panel({ title, children, className = "", bodyClassName = "" }) {
    return h("section", { className: `panel ${className}` },
      h("div", { className: "panel-title" }, title),
      h("div", { className: `panel-body ${bodyClassName}` }, children),
    );
  }

  function App() {
    const [layout, setLayout] = useState(readLayout);
    const [resizeMode, setResizeMode] = useState(null);
    const [health, setHealth] = useState(null);
    const [sessionType, setSessionType] = useState("test");
    const [configOpen, setConfigOpen] = useState(false);

    useEffect(() => { writeLayout(layout); }, [layout]);

    const pollHealth = useCallback(async () => {
      try {
        const data = await fetchJSON("/health");
        setHealth(data);
        setSessionType(data.session_type || "test");
      } catch {
        setHealth({ status: "degraded", session_id: "", session_type: "test" });
      }
    }, []);

    useEffect(() => { pollHealth(); }, [pollHealth]);
    useInterval(pollHealth, 5000);

    const startResize = useCallback((mode, event) => {
      event.preventDefault();
      const startX = event.clientX;
      const startY = event.clientY;
      const start = { ...layout };
      setResizeMode(mode);
      const onMove = (moveEvent) => {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight - 42;
        setLayout((current) => {
          if (mode === "left") {
            return { ...current, left: clamp(start.left + moveEvent.clientX - startX, 280, viewportWidth - start.right - 360) };
          }
          if (mode === "right") {
            return { ...current, right: clamp(start.right - (moveEvent.clientX - startX), 320, viewportWidth - start.left - 420) };
          }
          if (mode === "bottom") {
            return { ...current, bottom: clamp(start.bottom - (moveEvent.clientY - startY), 260, viewportHeight - 220) };
          }
          return current;
        });
      };
      const onUp = () => {
        setResizeMode(null);
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    }, [layout]);

    const applySessionType = useCallback(async (value) => {
      if (!["test", "exhibition"].includes(value)) return;
      if (value === "exhibition" && !confirm("Activate exhibition mode for the current session?")) {
        return;
      }
      try {
        const result = await fetchJSON("/api/v1/sessions/current/type", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_type: value }),
        });
        setSessionType(result.session_type || value);
        pollHealth();
      } catch (error) {
        alert(`Session mode update failed: ${error.message}`);
      }
    }, [pollHealth]);

    const resetMemory = useCallback(async () => {
      if (!confirm("Archive current session and start a new empty memory session?")) return;
      try {
        await fetchJSON("/api/v1/sessions/reset", { method: "POST" });
        pollHealth();
        window.dispatchEvent(new CustomEvent("entity:session-reset"));
      } catch (error) {
        alert(`Reset failed: ${error.message}`);
      }
    }, [pollHealth]);

    const saveConversation = useCallback(async () => {
      try {
        const data = await fetchJSON("/api/v1/conversation/export?limit=5000");
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `conversation-${compactId(data.session_id || "session")}-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (error) {
        alert(`Export failed: ${error.message}`);
      }
    }, []);

    const gridStyle = {
      gridTemplateColumns: `${layout.left}px minmax(360px, 1fr) ${layout.right}px`,
      gridTemplateRows: `minmax(220px, 1fr) ${layout.bottom}px`,
    };

    const className = `dashboard ${resizeMode ? "resizing" : ""} ${resizeMode === "bottom" ? "resizing-horizontal" : ""}`;

    return h("div", { className: "app" },
      h(Header, {
        health,
        sessionType,
        onSessionTypeChange: applySessionType,
        onSave: saveConversation,
        onReset: resetMemory,
        onConfig: () => setConfigOpen(true),
      }),
      h("main", { className, style: gridStyle },
        h(Panel, { title: "Entity State", className: "state-panel" }, h(EntityState)),
        h(Panel, { title: "Vision", className: "vision-panel", bodyClassName: "vision-body" }, h(VisionPanel)),
        h(Panel, { title: "Dialog", className: "dialog-panel", bodyClassName: "dialog-panel" }, h(DialogPanel)),
        h(Panel, { title: "Memory System", className: "memory-panel" }, h(MemorySummary)),
        h(Panel, { title: "Right Sidebar", className: "runtime-panel", bodyClassName: "sidebar-body" }, h(RuntimeSidebar)),
        h("div", {
          className: `resize-handle vertical ${resizeMode === "left" ? "active" : ""}`,
          style: { left: `${layout.left - 5}px` },
          onPointerDown: (event) => startResize("left", event),
          title: "Resize left column",
        }),
        h("div", {
          className: `resize-handle vertical ${resizeMode === "right" ? "active" : ""}`,
          style: { right: `${layout.right - 5}px` },
          onPointerDown: (event) => startResize("right", event),
          title: "Resize right column",
        }),
        h("div", {
          className: `resize-handle horizontal ${resizeMode === "bottom" ? "active" : ""}`,
          style: { bottom: `${layout.bottom - 5}px` },
          onPointerDown: (event) => startResize("bottom", event),
          title: "Resize bottom row",
        }),
      ),
      configOpen ? h(ConfigModal, { onClose: () => setConfigOpen(false) }) : null,
    );
  }

  function Header({ health, sessionType, onSessionTypeChange, onSave, onReset, onConfig }) {
    const status = health && health.status ? health.status : "connecting";
    return h("header", { className: "app-header" },
      h("h1", { className: "app-title" }, "CONSCIOUS ENTITY — DEV PANEL"),
      h("span", { className: `badge ${status === "ok" ? "ok" : status === "connecting" ? "" : "err"}` }, status.toUpperCase()),
      h("span", { className: "dim" }, "Mode"),
      h("select", {
        className: "compact-select",
        value: sessionType,
        onChange: (event) => onSessionTypeChange(event.target.value),
      },
        h("option", { value: "test" }, "test"),
        h("option", { value: "exhibition" }, "exhibition"),
      ),
      h("button", { className: "btn-sm", onClick: onSave }, "Save Dialog"),
      h("button", { className: "btn-sm", onClick: onReset }, "Reset Memory / New Session"),
      h("button", { className: "btn-sm", onClick: onConfig }, "YAML Config"),
      h("div", { className: "header-spacer" }),
      h("span", { className: "session-label" }, health && health.session_id ? `session: ${compactId(health.session_id)} · ${sessionType} · visitor: ${health.visitor_id ? compactId(health.visitor_id) : "none"}` : "session: —"),
    );
  }

  function EntityState() {
    const [state, setState] = useState(null);

    const load = useCallback(async () => {
      try {
        setState(await fetchJSON("/api/v1/state"));
      } catch {
        setState(null);
      }
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 2000);

    if (!state) return h("div", { className: "dim" }, "Loading state…");

    return h(React.Fragment, null,
      STATE_KEYS.map((key) => {
        const raw = Number(state[key] || 0);
        const pct = clamp(Math.round(raw * 100), 0, 100);
        return h("div", { className: "state-var", key },
          h("div", { className: "state-var-name" }, key),
          h("div", { className: "state-bar-row" },
            h("div", { className: "state-bar-bg" },
              h("div", { className: `state-bar-fill bar-${key}`, style: { width: `${pct}%` } }),
            ),
            h("div", { className: "state-val" }, raw.toFixed(3)),
          ),
        );
      }),
      h("div", { className: "state-ts" },
        escapeText(state.recorded_at), h("br"),
        `trigger: ${state.trigger_event_type || "—"}   action: ${state.policy_action || "—"}`,
      ),
    );
  }

  function VisionPanel() {
    const [status, setStatus] = useState(null);
    const [identityStatus, setIdentityStatus] = useState(null);
    const [metadata, setMetadata] = useState(null);
    const [error, setError] = useState("");
    const [selectedCameraId, setSelectedCameraId] = useState("");
    const [cameraOptions, setCameraOptions] = useState([]);
    const [scanning, setScanning] = useState(false);
    const [browserCameraActive, setBrowserCameraActive] = useState(false);
    const [browserCameraError, setBrowserCameraError] = useState("");
    const [frameUrl, setFrameUrl] = useState("");
    const socketRef = useRef(null);
    const frameUrlRef = useRef("");
    const browserVideoRef = useRef(null);
    const browserCanvasRef = useRef(null);
    const browserStreamRef = useRef(null);
    const browserIntervalRef = useRef(null);
    const browserBusyRef = useRef(false);

    const detections = (metadata && metadata.detections) || (status && status.latest && status.latest.detections) || [];
    const events = (metadata && metadata.events) || (status && status.recent_events) || [];

    const disconnectStream = useCallback(() => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    }, []);

    const connectStream = useCallback(() => {
      if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) return;
      const scheme = window.location.protocol === "https:" ? "wss" : "ws";
      const socket = new WebSocket(`${scheme}://${window.location.host}/api/v1/vision/stream`);
      socket.binaryType = "blob";
      socket.onmessage = (event) => {
        if (typeof event.data === "string") {
          try { setMetadata(JSON.parse(event.data)); } catch { /* ignore malformed frame metadata */ }
          return;
        }
        const nextUrl = URL.createObjectURL(event.data);
        const previous = frameUrlRef.current;
        frameUrlRef.current = nextUrl;
        setFrameUrl(nextUrl);
        if (previous) setTimeout(() => URL.revokeObjectURL(previous), 1000);
      };
      socket.onclose = () => { socketRef.current = null; };
      socket.onerror = () => setError("Vision stream connection failed.");
      socketRef.current = socket;
    }, []);

    const loadStatus = useCallback(async () => {
      try {
        const [data, identity] = await Promise.all([
          fetchJSON("/api/v1/vision/status"),
          fetchJSON("/api/v1/identity/status").catch(() => null),
        ]);
        setStatus(data);
        setIdentityStatus(identity);
        setError(data.error || data.disabled_reason || "");
        if (data.running) connectStream();
      } catch (err) {
        setError(err.message);
      }
    }, [connectStream]);

    const scanCameras = useCallback(async () => {
      setScanning(true);
      try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
          throw new Error("Browser camera capture is not available.");
        }
        let devices = navigator.mediaDevices.enumerateDevices
          ? await navigator.mediaDevices.enumerateDevices()
          : [];
        let permissionStream = null;
        const hasNamedCamera = devices.some((device) => device.kind === "videoinput" && device.label);
        if (!hasNamedCamera && !browserStreamRef.current) {
          permissionStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: true });
          devices = navigator.mediaDevices.enumerateDevices
            ? await navigator.mediaDevices.enumerateDevices()
            : [];
        }
        if (permissionStream) {
          permissionStream.getTracks().forEach((track) => track.stop());
        }
        const scannedCameras = devices
          .filter((device) => device.kind === "videoinput")
          .map((device, index) => ({
            deviceId: device.deviceId,
            label: device.label || `Camera ${index + 1}`,
          }));
        const cameras = scannedCameras.length
          ? scannedCameras
          : [{ deviceId: "", label: "Default Camera" }];
        setCameraOptions(cameras);
        if (cameras.length && !cameras.some((item) => item.deviceId === selectedCameraId)) {
          setSelectedCameraId(cameras[0].deviceId);
        }
        setError("");
      } catch (err) {
        setError(err.message);
      } finally {
        setScanning(false);
      }
    }, [selectedCameraId]);

    const sendBrowserFrame = useCallback(async () => {
      const video = browserVideoRef.current;
      if (!video || video.readyState < 2 || browserBusyRef.current) return;
      const canvas = browserCanvasRef.current || document.createElement("canvas");
      browserCanvasRef.current = canvas;
      const targetWidth = Number((status && status.config && status.config.width) || video.videoWidth || 1280);
      const targetHeight = Number((status && status.config && status.config.height) || video.videoHeight || 720);
      canvas.width = targetWidth;
      canvas.height = targetHeight;
      const context = canvas.getContext("2d");
      if (!context) return;
      context.drawImage(video, 0, 0, targetWidth, targetHeight);
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.76));
      if (!blob) return;
      browserBusyRef.current = true;
      try {
        const response = await fetch("/api/v1/vision/frame", {
          method: "POST",
          headers: { "Content-Type": "image/jpeg" },
          body: blob,
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `HTTP ${response.status}`);
        }
        const data = await response.json();
        setStatus(data);
        setError(data.error || "");
        connectStream();
      } catch (err) {
        setBrowserCameraError(err.message);
      } finally {
        browserBusyRef.current = false;
      }
    }, [connectStream, status]);

    const stopBrowserCamera = useCallback(() => {
      if (browserIntervalRef.current) {
        window.clearInterval(browserIntervalRef.current);
        browserIntervalRef.current = null;
      }
      if (browserStreamRef.current) {
        browserStreamRef.current.getTracks().forEach((track) => track.stop());
        browserStreamRef.current = null;
      }
      if (browserVideoRef.current) {
        browserVideoRef.current.pause();
        browserVideoRef.current.srcObject = null;
      }
      setBrowserCameraActive(false);
      setBrowserCameraError("");
    }, []);

    const startBrowserCamera = useCallback(async () => {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setBrowserCameraError("Browser camera capture is not available.");
        return;
      }
      try {
        stopBrowserCamera();
        const targetWidth = Number((status && status.config && status.config.width) || 1280);
        const targetHeight = Number((status && status.config && status.config.height) || 720);
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            ...(selectedCameraId ? { deviceId: { exact: selectedCameraId } } : {}),
            width: { ideal: targetWidth },
            height: { ideal: targetHeight },
          },
        });
        const video = browserVideoRef.current || document.createElement("video");
        browserVideoRef.current = video;
        video.muted = true;
        video.playsInline = true;
        video.srcObject = stream;
        browserStreamRef.current = stream;
        await video.play();
        setBrowserCameraActive(true);
        setBrowserCameraError("");
        connectStream();
        await sendBrowserFrame();
        const targetFps = Math.min(5, Number((status && status.config && status.config.fps) || 5));
        const intervalMs = Math.max(200, Math.round(1000 / Math.max(1, targetFps)));
        browserIntervalRef.current = window.setInterval(sendBrowserFrame, intervalMs);
      } catch (err) {
        stopBrowserCamera();
        setBrowserCameraError(err.message);
      }
    }, [connectStream, selectedCameraId, sendBrowserFrame, status, stopBrowserCamera]);

    const stopVision = useCallback(async () => {
      stopBrowserCamera();
      disconnectStream();
      setMetadata(null);
      try {
        const data = await fetchJSON("/api/v1/vision/stop", { method: "POST" });
        setStatus(data);
      } catch (err) {
        setError(err.message);
      }
    }, [disconnectStream, stopBrowserCamera]);

    useEffect(() => {
      loadStatus();
      return () => {
        stopBrowserCamera();
        disconnectStream();
        if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
      };
    }, [disconnectStream, loadStatus, stopBrowserCamera]);
    useInterval(loadStatus, 5000);

    const cfg = (metadata && metadata.camera) || (status && status.config) || {};
    const model = status ? (status.model_path || (status.model && status.model.path) || "not set") : "not set";
    const running = metadata ? metadata.running : status && status.running;
    const frameId = metadata ? metadata.frame_id : status && status.frame_id;
    const updated = metadata ? metadata.timestamp : status && status.timestamp;
    const recognition = (metadata && metadata.recognition) || (status && status.recognition) || {};
    const identity = identityStatus && identityStatus.status ? identityStatus.status : null;
    const statusText = recognition.pipeline_status || (running ? "running" : status && status.enabled ? "ready" : "disabled");
    const statusClass = statusText === "running" ? "ok" : statusText === "error" || statusText === "disabled" ? "err" : "dim";
    const source = recognition.source || (metadata && metadata.source) || "opencv";
    const selectedOption = cameraOptions.find((item) => item.deviceId === selectedCameraId);
    const cameraDetail = selectedOption
      ? selectedOption.label
      : cameraOptions.length ? "select a camera" : "scan cameras first";

    return h(React.Fragment, null,
      h("div", { className: "toolbar" },
        h("button", { className: "btn-sm", onClick: scanCameras, disabled: scanning }, scanning ? "Scanning…" : "Scan Cameras"),
        h("select", {
          value: selectedCameraId,
          onChange: (event) => setSelectedCameraId(event.target.value),
          title: "Camera",
        },
          cameraOptions.length
            ? cameraOptions.map((item) => h("option", { key: item.deviceId, value: item.deviceId }, item.label))
            : h("option", { value: "" }, "No camera scanned"),
        ),
        h("button", { className: browserCameraActive ? "btn-sm active" : "btn-sm", onClick: startBrowserCamera, disabled: browserCameraActive }, browserCameraActive ? "Connected" : "Connect"),
        h("button", { className: "btn-sm", onClick: stopVision, disabled: !browserCameraActive && !running }, "Stop"),
      ),
      h("div", { className: "item-meta", style: { marginTop: "4px" } }, cameraDetail),
      h("div", { className: "vision-preview" }, frameUrl
        ? h("img", { src: frameUrl, alt: "Vision stream" })
        : h("div", { className: "dim", style: { padding: "12px" } }, "No frame yet.")),
      h("div", { className: "kv-grid" },
        h("span", null, "Status"), h("span", { className: statusClass }, statusText),
        h("span", null, "Frame"), h("span", null, frameId ?? "—"),
        h("span", null, "People"), h("span", null, detections.length),
        h("span", null, "Camera"), h("span", null, `${cfg.index ?? cfg.camera_index ?? "—"} · ${cfg.width ?? "—"}x${cfg.height ?? "—"} · ${cfg.fps ?? "—"}fps`),
        h("span", null, "Input"), h("span", null, source),
        h("span", null, "Model"), h("span", { title: model }, String(model).split("/").pop()),
        h("span", null, "Updated"), h("span", null, formatTime(updated)),
      ),
      h(RealtimeRecognitionStatus, { recognition, identity, detections }),
      error ? h("div", { className: "err" }, error) : null,
      browserCameraError ? h("div", { className: "err" }, browserCameraError) : null,
      h(DetectionList, { detections }),
      h(EventList, { events }),
    );
  }

  function RealtimeRecognitionStatus({ recognition, identity, detections }) {
    const personCount = recognition.person_count ?? (detections ? detections.length : 0);
    const age = recognition.frame_age_ms == null ? "—" : `${recognition.frame_age_ms} ms`;
    const presence = recognition.person_present ? "present" : "absent";
    return h("div", { className: "recognition-status" },
      h("div", { className: "item-meta" }, "Realtime Recognition"),
      h("div", { className: "kv-grid" },
        h("span", null, "Pipeline"), h("span", { className: recognition.pipeline_status === "running" ? "ok" : recognition.pipeline_status === "error" ? "err" : "dim" }, recognition.pipeline_status || "—"),
        h("span", null, "Camera"), h("span", null, recognition.camera_status || "—"),
        h("span", null, "Source"), h("span", null, recognition.source || "—"),
        h("span", null, "Detector"), h("span", null, recognition.detector_status || "—"),
        h("span", null, "Frame age"), h("span", null, age),
        h("span", null, "Presence"), h("span", null, `${presence} · ${personCount} people`),
        h("span", null, "Threshold"), h("span", null, `${recognition.confidence_threshold ?? "—"} · enter ${recognition.enter_frames ?? "—"} frames`),
        h("span", null, "Access"), h("span", { className: recognition.access_hint ? "err" : "ok" }, recognition.access_hint ? "blocked or busy" : "available"),
        h("span", null, "Identity gate"), h("span", null, identity ? `${identity.runtime_state || "—"} · ${identity.last_decision || "—"}` : "—"),
        h("span", null, "Encounter"), h("span", null, identity ? `${identity.encounter_status || "—"} · ${identity.intent_status || "—"}` : "—"),
        h("span", null, "Bio match"), h("span", null, identity ? `face ${identity.face_confidence_level || "none"} · voice ${identity.voice_confidence_level || "none"} · combined ${identity.combined_confidence_level || "none"}` : "—"),
      ),
      recognition.access_hint ? h("div", { className: "err" }, recognition.access_hint) : null,
    );
  }

  function DetectionList({ detections }) {
    if (!detections || detections.length === 0) {
      return h("div", { className: "detection-list" }, h("div", { className: "dim" }, "Recognition: no person detected."));
    }
    return h("div", { className: "detection-list" },
      detections.slice(0, 6).map((det, index) => {
        const confidence = Number(det.confidence || 0);
        const pct = clamp(Math.round(confidence * 100), 0, 100);
        const bbox = det.bbox || {};
        return h("div", { className: "detection-row", key: `${index}-${pct}` },
          h("div", null, `${det.label || "person"} ${index + 1}`),
          h("div", null,
            h("div", { style: { display: "flex", justifyContent: "space-between", gap: "8px" } },
              h("span", { className: "ok" }, `${pct}%`),
              h("span", { className: "bbox" }, `x ${bbox.x1 ?? "—"}-${bbox.x2 ?? "—"} · y ${bbox.y1 ?? "—"}-${bbox.y2 ?? "—"}`),
            ),
            h("div", { className: "confidence" }, h("div", { className: "confidence-fill", style: { width: `${pct}%` } })),
          ),
        );
      }),
    );
  }

  function EventList({ events }) {
    if (!events || events.length === 0) {
      return h("div", { className: "events-list" }, "No recent vision events.");
    }
    return h("div", { className: "events-list" },
      events.slice(0, 6).map((event, index) => h("div", { key: index },
        `${formatTime(event.timestamp)} · ${event.event_type || event.type || ""}${event.reason ? ` · ${event.reason}` : ""}`,
      )),
    );
  }

  function DialogPanel() {
    const [rows, setRows] = useState([]);
    const [text, setText] = useState("");
    const [sending, setSending] = useState(false);
    const logRef = useRef(null);

    const load = useCallback(async () => {
      try {
        const data = await fetchJSON("/api/v1/interaction-log?limit=30");
        setRows(normalizeInteractionRows(data));
      } catch {
        setRows([]);
      }
    }, []);

    useEffect(() => {
      load();
      const onReset = () => load();
      const onTurnComplete = (event) => {
        const detail = event.detail || {};
        if (detail.source === "audio_dialog" && detail.output) {
          const now = new Date().toISOString();
          setRows((current) => [...current, {
            id: `audio-user-${Date.now()}`,
            role: "user",
            raw_text: detail.input_text || "",
            turn_at: now,
          }, {
            id: `audio-entity-${Date.now()}`,
            role: "entity",
            expression_output: detail.output.output_text || "",
            delay_ms: detail.output.delay_ms,
            visual_mode: detail.output.visual_mode,
            policy_action: "audio_dialog",
            turn_at: now,
          }]);
        }
        window.setTimeout(load, 250);
      };
      window.addEventListener("entity:turn-complete", onTurnComplete);
      window.addEventListener("entity:session-reset", onReset);
      return () => {
        window.removeEventListener("entity:turn-complete", onTurnComplete);
        window.removeEventListener("entity:session-reset", onReset);
      };
    }, [load]);

    useEffect(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [rows]);

    const send = useCallback(async () => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
      const submitStartedAt = nowMs();
      setText("");
      setSending(true);
      const optimistic = {
        id: `pending-${Date.now()}`,
        role: "user",
        raw_text: trimmed,
        turn_at: new Date().toISOString(),
      };
      setRows((current) => [...current, optimistic]);
      try {
        const output = await fetchJSON("/api/v1/dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: trimmed }),
        });
        const responseAt = nowMs();
        postPresentationLatency("dashboard.text_dialog.response", submitStartedAt, {
          latencyRecordId: output.latency_record_id,
          metadata: { input_chars: trimmed.length },
        });
        setRows((current) => [...current, {
          id: `entity-${Date.now()}`,
          role: "entity",
          expression_output: output.text,
          delay_ms: output.delay_ms,
          visual_mode: output.visual_mode,
          turn_at: new Date().toISOString(),
        }]);
        window.requestAnimationFrame(() => {
          postPresentationLatency("dashboard.text_dialog.render", responseAt, {
            latencyRecordId: output.latency_record_id,
            metadata: { text_chars: String(output.text || "").length },
          });
        });
        window.dispatchEvent(new CustomEvent("entity:turn-complete"));
      } catch (error) {
        setRows((current) => [...current, {
          id: `error-${Date.now()}`,
          role: "system",
          raw_text: `[Error] ${error.message}`,
          turn_at: new Date().toISOString(),
        }]);
      } finally {
        setSending(false);
      }
    }, [sending, text]);

    const messages = useMemo(() => rows.flatMap((row) => {
      const out = [];
      if (row.raw_text) out.push({ role: row.role || "user", text: row.raw_text, ts: row.turn_at, key: `${row.id}-raw` });
      if (row.expression_output !== null && row.expression_output !== undefined) {
        out.push({ role: "entity", text: row.expression_output || "...", ts: row.turn_at, meta: [row.policy_action, row.delay_ms ? `${row.delay_ms}ms` : "", row.visual_mode].filter(Boolean).join(" · "), key: `${row.id}-entity` });
      }
      return out;
    }), [rows]);

    return h(React.Fragment, null,
      h("div", { className: "dialog-log", ref: logRef },
        messages.map((message) => h(Message, { key: message.key, message })),
      ),
      h("div", { className: "dialog-input-row" },
        h("input", {
          className: "dialog-input",
          value: text,
          onChange: (event) => setText(event.target.value),
          onKeyDown: (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          },
          placeholder: "Send a message…",
        }),
        h("button", { className: "btn-sm", onClick: send, disabled: sending }, sending ? "Sending…" : "Send"),
      ),
    );
  }

  function Message({ message }) {
    const meta = [formatTime(message.ts), message.meta].filter(Boolean).join(" · ");
    return h("div", { className: "msg" },
      h("div", { className: `msg-role ${message.role}` }, message.role),
      h("div", null,
        h("div", { className: "msg-text" }, escapeText(message.text)),
        h("div", { className: "msg-meta" }, meta),
      ),
    );
  }

  function MemorySummary() {
    const [summary, setSummary] = useState(null);
    const [previewQuery, setPreviewQuery] = useState("");
    const [preview, setPreview] = useState(null);

    const load = useCallback(async () => {
      try {
        const [episodic, reflective] = await Promise.all([
          fetchJSON("/api/v1/memory/episodic?limit=200"),
          fetchJSON("/api/v1/memory/reflective"),
        ]);
        setSummary({
          episodic: episodic.length,
          unreflected: episodic.filter((item) => !item.reflected).length,
          reflective: reflective.length,
          latestReflection: reflective[0] && reflective[0].content,
        });
      } catch {
        setSummary(null);
      }
    }, []);

    useEffect(() => {
      load();
      const refresh = () => load();
      window.addEventListener("entity:turn-complete", refresh);
      window.addEventListener("entity:session-reset", refresh);
      return () => {
        window.removeEventListener("entity:turn-complete", refresh);
        window.removeEventListener("entity:session-reset", refresh);
      };
    }, [load]);
    useInterval(load, 10000);

    const runPreview = useCallback(async () => {
      const query = previewQuery.trim();
      if (!query) return;
      try {
        setPreview(await fetchJSON(`/api/v1/memory/preview?query=${encodeURIComponent(query)}`));
      } catch (error) {
        setPreview({ error: error.message, results: [] });
      }
    }, [previewQuery]);

    return h(React.Fragment, null,
      summary ? h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Episodic events"), h("td", null, summary.episodic)),
        h("tr", null, h("td", null, "Unreflected"), h("td", null, summary.unreflected)),
        h("tr", null, h("td", null, "Active reflections"), h("td", null, summary.reflective)),
      )) : h("div", { className: "dim" }, "Loading memory summary…"),
      summary && summary.latestReflection ? h("div", { className: "item" },
        h("div", { className: "item-meta" }, "Latest reflection"),
        h("div", { className: "item-text" }, String(summary.latestReflection).slice(0, 220)),
      ) : null,
      h("div", { className: "form-grid", style: { marginTop: "10px" } },
        h("label", { className: "wide" }, "Preview query",
          h("input", {
            value: previewQuery,
            onChange: (event) => setPreviewQuery(event.target.value),
            onKeyDown: (event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                runPreview();
              }
            },
            placeholder: "Preview memory for a query…",
          }),
        ),
        h("div", { className: "wide toolbar" }, h("button", { className: "btn-sm", onClick: runPreview }, "Preview")),
      ),
      preview ? h("div", { className: "item" },
        preview.error ? h("div", { className: "err" }, preview.error) : h("div", { className: "item-meta" }, `${(preview.results || []).length} result(s)`),
        (preview.results || []).slice(0, 5).map((item, index) => h("div", { className: "item-text", key: index }, `${item.memory_type || ""} · score ${item.score ?? ""}: ${String(item.content || "").slice(0, 220)}`)),
      ) : null,
    );
  }

  function RuntimeSidebar() {
    const [tab, setTab] = useState("runtime");
    return h(React.Fragment, null,
      h("div", { className: "tabs" },
        ["runtime", "memory", "history"].map((name) => h("button", {
          key: name,
          className: `tab ${tab === name ? "active" : ""}`,
          onClick: () => setTab(name),
        }, name === "runtime" ? "Runtime" : name === "memory" ? "Memory Curation" : "Session & History")),
      ),
      h("div", { className: "tab-content" },
        tab === "runtime" ? h(RuntimePane) : tab === "memory" ? h(MemoryCurationPane) : h(SessionHistoryPane),
      ),
    );
  }

  function RuntimePane() {
    const [llm, setLlm] = useState(null);
    const [embedding, setEmbedding] = useState(null);
    const [stats, setStats] = useState(null);
    const [latency, setLatency] = useState(null);
    const [audioLatency, setAudioLatency] = useState(null);
    const [presentationLatency, setPresentationLatency] = useState(null);
    const [harness, setHarness] = useState(null);
    const [visitor, setVisitor] = useState(null);
    const [identity, setIdentity] = useState(null);

    const load = useCallback(async () => {
      const [llmConfig, embeddingConfig, llmStats, latencyStats, audioLatencyStats, presentationLatencyStats, harnessStatus, visitorStatus, identityStatus] = await Promise.all([
        fetchJSON("/api/v1/config/llm").catch(() => null),
        fetchJSON("/api/v1/config/embedding").catch(() => null),
        fetchJSON("/api/v1/stats/llm").catch(() => null),
        fetchJSON("/api/v1/stats/latency?n=1").catch(() => null),
        fetchJSON("/api/v1/stats/audio-latency?n=8").catch(() => null),
        fetchJSON("/api/v1/stats/presentation-latency?n=8").catch(() => null),
        fetchJSON("/api/v1/harness/status").catch(() => null),
        fetchJSON("/api/v1/visitors/current").catch(() => null),
        fetchJSON("/api/v1/identity/status").catch(() => null),
      ]);
      setLlm(llmConfig);
      setEmbedding(embeddingConfig);
      setStats(llmStats && llmStats.summary);
      setLatency(latencyStats);
      setAudioLatency(audioLatencyStats);
      setPresentationLatency(presentationLatencyStats);
      setHarness(harnessStatus);
      setVisitor(visitorStatus);
      setIdentity(identityStatus);
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 10000);

    return h(React.Fragment, null,
      h(VisitorSection, { data: visitor, onSaved: load }),
      h(IdentityGatingSection, { data: identity }),
      h(LLMConfigSection, { data: llm, onSaved: load }),
      h(EmbeddingConfigSection, { data: embedding, onSaved: load }),
      h(AudioPane),
      h(HarnessSection, { harness }),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Diagnostics"),
        stats ? h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Total calls"), h("td", null, stats.total_calls)),
          h("tr", null, h("td", null, "Success"), h("td", { className: "ok" }, stats.success_count)),
          h("tr", null, h("td", null, "Failure"), h("td", { className: stats.failure_count > 0 ? "err" : "dim" }, stats.failure_count)),
          h("tr", null, h("td", null, "Avg latency"), h("td", null, `${stats.avg_duration_ms} ms`)),
          h("tr", null, h("td", null, "Tokens"), h("td", null, `${stats.total_prompt_tokens} / ${stats.total_completion_tokens}`)),
        )) : h("div", { className: "dim" }, "Loading diagnostics…"),
      ),
      h(LatencySection, { latency, audioLatency, presentationLatency }),
    );
  }

  function VisitorSection({ data, onSaved }) {
    const [known, setKnown] = useState([]);
    const [visitorId, setVisitorId] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [saving, setSaving] = useState(false);
    const current = data && data.visitor ? data.visitor : null;

    const loadKnown = useCallback(async () => {
      setKnown(await fetchJSON("/api/v1/visitors?limit=80").catch(() => []));
    }, []);

    useEffect(() => { loadKnown(); }, [loadKnown]);
    useInterval(loadKnown, 15000);

    const create = useCallback(async () => {
      setSaving(true);
      try {
        await fetchJSON("/api/v1/visitors", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            visitor_id: visitorId || null,
            display_name: displayName || null,
          }),
        });
        setVisitorId("");
        setDisplayName("");
        await onSaved();
        await loadKnown();
        window.dispatchEvent(new CustomEvent("entity:session-reset"));
      } catch (error) {
        alert(`Visitor update failed: ${error.message}`);
      } finally {
        setSaving(false);
      }
    }, [visitorId, displayName, onSaved, loadKnown]);

    const select = useCallback(async (id) => {
      setSaving(true);
      try {
        await fetchJSON("/api/v1/visitors/current", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ visitor_id: id || null }),
        });
        await onSaved();
        window.dispatchEvent(new CustomEvent("entity:session-reset"));
      } catch (error) {
        alert(`Visitor select failed: ${error.message}`);
      } finally {
        setSaving(false);
      }
    }, [onSaved]);

    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Visitor Identity"),
      h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Current visitor"), h("td", null, current ? `${current.display_name || current.id} · ${current.id}` : "none")),
        h("tr", null, h("td", null, "Scope"), h("td", null, current ? "same visitor sessions included in retrieval" : "current session only")),
      )),
      h("div", { className: "toolbar", style: { marginTop: "8px" } },
        h("input", {
          value: visitorId,
          placeholder: "visitor id optional",
          onChange: (event) => setVisitorId(event.target.value),
        }),
        h("input", {
          value: displayName,
          placeholder: "display name optional",
          onChange: (event) => setDisplayName(event.target.value),
        }),
        h("button", { className: "btn-sm", disabled: saving, onClick: create }, saving ? "Saving…" : "Create / Set"),
        h("button", { className: "btn-sm", disabled: saving || !current, onClick: () => select(null) }, "Clear"),
      ),
      known.length ? h("div", { className: "card-list compact-list" },
        known.slice(0, 5).map((item) => h("button", {
          key: item.id,
          className: `session-item ${item.active ? "active" : ""}`,
          onClick: () => select(item.id),
          disabled: saving,
        },
          h("div", { className: "session-title" }, h("span", null, item.display_name || item.id), h("span", null, item.active ? "active" : "")),
          h("div", { className: "session-meta" }, `${item.session_count || 0} sessions · ${item.turn_count || 0} turns`),
        )),
      ) : h("div", { className: "dim" }, "No visitor profiles yet."),
    );
  }

  function IdentityGatingSection({ data }) {
    const status = data && data.status ? data.status : null;
    const constraints = data && data.v1_constraints ? data.v1_constraints : {};
    const events = data && Array.isArray(data.recent_events) ? data.recent_events : [];
    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Identity & Session Gating"),
      status ? h(React.Fragment, null,
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Runtime"), h("td", null, status.runtime_state || "—")),
          h("tr", null, h("td", null, "Session decision"), h("td", null, status.last_decision || "—")),
          h("tr", null, h("td", null, "Primary visitor"), h("td", null, status.primary_visitor_id || "unknown")),
          h("tr", null, h("td", null, "Candidate"), h("td", null, status.candidate_visitor_id || "none")),
          h("tr", null, h("td", null, "Encounter / intent"), h("td", null, `${status.encounter_status || "—"} · ${status.intent_status || "—"}`)),
          h("tr", null, h("td", null, "Identity"), h("td", null, `${status.identity_status || "—"} · face ${status.face_confidence_level || "none"} · voice ${status.voice_confidence_level || "none"} · combined ${status.combined_confidence_level || "none"}`)),
          h("tr", null, h("td", null, "Waiting confirm"), h("td", null, status.waiting_for_identity_confirmation ? "yes" : "no")),
          h("tr", null, h("td", null, "Interruptions"), h("td", null, status.interruption_count || 0)),
        )),
        h("div", { className: "item" },
          h("div", { className: "item-meta" }, "V1 constraints"),
          h("div", { className: "item-text" },
            `single visitor ${constraints.single_primary_visitor_per_session ? "on" : "off"} · group session ${constraints.group_session_enabled ? "on" : "off"} · wide-angle identity ${constraints.wide_angle_identity_input_enabled ? "on" : "off"}`,
          ),
        ),
        events.length ? h("details", { className: "item" },
          h("summary", { className: "item-meta" }, "Recent gating events"),
          events.slice().reverse().map((event) => h("div", { className: "item-text", key: event.id },
            `${event.kind}: ${event.decision} · ${event.summary}`,
          )),
        ) : null,
      ) : h("div", { className: "dim" }, "Identity/session gating status unavailable."),
    );
  }

  function LLMConfigSection({ data, onSaved }) {
    const [mode, setMode] = useState("official");
    const [model, setModel] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [authToken, setAuthToken] = useState("");
    const [baseUrl, setBaseUrl] = useState("");
    const [messagesEndpoint, setMessagesEndpoint] = useState("");
    const [disableProxy, setDisableProxy] = useState(false);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState("");

    useEffect(() => {
      if (!data) return;
      setMode(data.mode || "official");
      setModel(data.ENTITY_LLM_MODEL || "");
      setBaseUrl(data.ANTHROPIC_BASE_URL || "");
      setMessagesEndpoint(data.ENTITY_LLM_MESSAGES_ENDPOINT || "");
      setDisableProxy(String(data.ENTITY_LLM_DISABLE_SYSTEM_PROXY || "").toLowerCase() === "true");
      setApiKey("");
      setAuthToken("");
      setError(data.error || "");
    }, [data]);

    const save = useCallback(async () => {
      setSaving(true);
      setError("");
      try {
        await fetchJSON("/api/v1/config/llm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            mode,
            model,
            api_key: apiKey,
            auth_token: authToken,
            base_url: baseUrl,
            messages_endpoint: messagesEndpoint,
            disable_system_proxy: disableProxy,
          }),
        });
        await onSaved();
      } catch (err) {
        setError(err.message);
      } finally {
        setSaving(false);
      }
    }, [apiKey, authToken, baseUrl, disableProxy, messagesEndpoint, mode, model, onSaved]);

    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "LLM Provider"),
      data ? h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Source"), h("td", null, data.source || "—")),
        h("tr", null, h("td", null, "Current key"), h("td", null, data.ANTHROPIC_API_KEY || data.ANTHROPIC_AUTH_TOKEN || "—")),
      )) : h("div", { className: "dim" }, "Loading LLM config…"),
      h("div", { className: "form-grid" },
        h("label", null, "Mode",
          h("select", { value: mode, onChange: (event) => setMode(event.target.value) },
            h("option", { value: "official" }, "official"),
            h("option", { value: "supplier" }, "supplier"),
            h("option", { value: "custom_endpoint" }, "custom endpoint"),
          ),
        ),
        h("label", null, "Model",
          h("input", { value: model, onChange: (event) => setModel(event.target.value), placeholder: "ENTITY_LLM_MODEL" }),
        ),
        h("label", null, "API key",
          h("input", { value: apiKey, onChange: (event) => setApiKey(event.target.value), placeholder: "leave blank to keep current", type: "password" }),
        ),
        h("label", null, "Auth token",
          h("input", { value: authToken, onChange: (event) => setAuthToken(event.target.value), placeholder: "leave blank to keep current", type: "password" }),
        ),
        h("label", null, "Base URL",
          h("input", { value: baseUrl, onChange: (event) => setBaseUrl(event.target.value), placeholder: "ANTHROPIC_BASE_URL" }),
        ),
        h("label", null, "Messages endpoint",
          h("input", { value: messagesEndpoint, onChange: (event) => setMessagesEndpoint(event.target.value), placeholder: "optional custom endpoint" }),
        ),
        h("label", { className: "wide inline-check" },
          h("input", { type: "checkbox", checked: disableProxy, onChange: (event) => setDisableProxy(event.target.checked) }),
          " Disable system proxy",
        ),
      ),
      h("div", { className: "toolbar" }, h("button", { className: "btn-sm", onClick: save, disabled: saving }, saving ? "Saving…" : "Apply LLM")),
      error ? h("div", { className: "err" }, error) : null,
    );
  }

  function EmbeddingConfigSection({ data, onSaved }) {
    const [mode, setMode] = useState("disabled");
    const [model, setModel] = useState("");
    const [apiKey, setApiKey] = useState("");
    const [baseUrl, setBaseUrl] = useState("");
    const [endpoint, setEndpoint] = useState("");
    const [saving, setSaving] = useState(false);
    const [testing, setTesting] = useState(false);
    const [error, setError] = useState("");
    const [testResult, setTestResult] = useState("");

    useEffect(() => {
      if (!data) return;
      setMode(data.mode || "disabled");
      setModel(data.ENTITY_EMBEDDING_MODEL || "");
      setBaseUrl(data.ENTITY_EMBEDDING_BASE_URL || "");
      setEndpoint(data.ENTITY_EMBEDDING_ENDPOINT || "");
      setApiKey("");
      setError(data.error || "");
      setTestResult("");
    }, [data]);

    const payload = useCallback(() => ({
      mode,
      model,
      api_key: apiKey,
      base_url: baseUrl,
      endpoint,
    }), [apiKey, baseUrl, endpoint, mode, model]);

    const applyConfig = useCallback(async () => {
      await fetchJSON("/api/v1/config/embedding", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      await onSaved();
    }, [onSaved, payload]);

    const save = useCallback(async () => {
      setSaving(true);
      setError("");
      setTestResult("");
      try {
        await applyConfig();
      } catch (err) {
        setError(err.message);
      } finally {
        setSaving(false);
      }
    }, [applyConfig]);

    const test = useCallback(async () => {
      setTesting(true);
      setError("");
      setTestResult("");
      try {
        await applyConfig();
        const result = await fetchJSON("/api/v1/config/embedding/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: "memory retrieval test" }),
        });
        setTestResult(`${result.model} · ${result.dimension} dims · ${result.latency_ms} ms`);
      } catch (err) {
        setError(err.message);
      } finally {
        setTesting(false);
      }
    }, [applyConfig]);

    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Embedding Provider"),
      data ? h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Source"), h("td", null, data.source || "—")),
        h("tr", null, h("td", null, "Current key"), h("td", null, data.ENTITY_EMBEDDING_API_KEY || "—")),
      )) : h("div", { className: "dim" }, "Loading embedding config…"),
      h("div", { className: "form-grid" },
        h("label", null, "Mode",
          h("select", { value: mode, onChange: (event) => setMode(event.target.value) },
            h("option", { value: "disabled" }, "disabled"),
            h("option", { value: "openai_compatible" }, "openai compatible"),
          ),
        ),
        h("label", null, "Model",
          h("input", { value: model, onChange: (event) => setModel(event.target.value), placeholder: "ENTITY_EMBEDDING_MODEL" }),
        ),
        h("label", null, "API key",
          h("input", { value: apiKey, onChange: (event) => setApiKey(event.target.value), placeholder: "leave blank to keep current", type: "password" }),
        ),
        h("label", null, "Base URL",
          h("input", { value: baseUrl, onChange: (event) => setBaseUrl(event.target.value), placeholder: "ENTITY_EMBEDDING_BASE_URL" }),
        ),
        h("label", { className: "wide" }, "Endpoint",
          h("input", { value: endpoint, onChange: (event) => setEndpoint(event.target.value), placeholder: "optional full embeddings endpoint" }),
        ),
      ),
      h("div", { className: "toolbar" },
        h("button", { className: "btn-sm", onClick: save, disabled: saving || testing }, saving ? "Saving…" : "Apply Embedding"),
        h("button", { className: "btn-sm", onClick: test, disabled: saving || testing || mode === "disabled" }, testing ? "Testing…" : "Test Embedding"),
      ),
      testResult ? h("div", { className: "ok" }, testResult) : null,
      error ? h("div", { className: "err" }, error) : null,
    );
  }

  function HarnessSection({ harness }) {
    const latest = harness && harness.latest;
    const summaryLayers = latest && latest.summary && latest.summary.layers ? latest.summary.layers : {};
    const layerNames = harness && Array.isArray(harness.layers) ? harness.layers : [
      "input", "state", "memory", "policy", "prompt", "generation", "output", "presentation",
    ];
    const promptLayer = summaryLayers.prompt;
    const promptPartials = promptLayer && promptLayer.metadata && Array.isArray(promptLayer.metadata.partials)
      ? promptLayer.metadata.partials.join(" · ")
      : "";
    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Harness"),
      latest ? h(React.Fragment, null,
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Last trace"), h("td", null, `${latest.source} · ${latest.success ? "ok" : "error"} · ${compactId(latest.trace_id)}`)),
          layerNames.map((layerName) => {
            const layer = summaryLayers[layerName];
            return h("tr", { key: layerName },
              h("td", null, layerName),
              h("td", null, layer
                ? `${layer.status}${layer.decision ? ` · ${layer.decision}` : ""}`
                : "—"),
            );
          }),
        )),
        promptPartials ? h("div", { className: "item" },
          h("div", { className: "item-meta" }, "Prompt partials"),
          h("div", { className: "item-text" }, promptPartials),
        ) : null,
        h("details", { className: "item" },
          h("summary", { className: "item-meta" }, "Latest trace summary"),
          layerNames.map((layerName) => {
            const layer = summaryLayers[layerName];
            if (!layer) return null;
            return h("div", { className: "item-text", key: `${layerName}-summary` },
              `${layerName}: ${layer.summary}`,
            );
          }),
        ),
      ) : h("div", { className: "dim" }, "No harness trace yet."),
    );
  }

  function LatencySection({ latency, audioLatency, presentationLatency }) {
    const latest = latency && latency.recent && latency.recent.length ? latency.recent[latency.recent.length - 1] : null;
    const turnSummary = latency && latency.summary;
    const steps = latest && latest.steps ? latest.steps.slice().sort((a, b) => b.duration_ms - a.duration_ms).slice(0, 8) : [];
    const audioKinds = audioLatency && audioLatency.summary && audioLatency.summary.kinds
      ? Object.entries(audioLatency.summary.kinds).sort((a, b) => b[1].avg_ms - a[1].avg_ms).slice(0, 6)
      : [];
    const presentationKinds = presentationLatency && presentationLatency.summary && presentationLatency.summary.kinds
      ? Object.entries(presentationLatency.summary.kinds).sort((a, b) => b[1].avg_ms - a[1].avg_ms).slice(0, 6)
      : [];
    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Latency Breakdown"),
      latest ? h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Last turn"), h("td", null, `${latest.source} · ${latest.total_ms} ms`)),
        h("tr", null, h("td", null, "Avg turn"), h("td", null, turnSummary ? `${turnSummary.avg_total_ms} ms` : "—")),
        steps.map((step) => h("tr", { key: `${step.name}-${step.duration_ms}` },
          h("td", null, step.name),
          h("td", null, `${step.duration_ms} ms${step.blocking ? "" : " bg"}`),
        )),
      )) : h("div", { className: "dim" }, "No turn latency yet."),
      audioKinds.length ? h("table", null, h("tbody", null,
        audioKinds.map(([kind, data]) => h("tr", { key: kind },
          h("td", null, kind),
          h("td", null, `${data.avg_ms} ms · ${data.count}`),
        )),
      )) : h("div", { className: "dim" }, "No audio latency yet."),
      presentationKinds.length ? h("table", null, h("tbody", null,
        presentationKinds.map(([kind, data]) => h("tr", { key: kind },
          h("td", null, kind),
          h("td", null, `${data.avg_ms} ms · ${data.count}`),
        )),
      )) : h("div", { className: "dim" }, "No presentation latency yet."),
    );
  }

  function AudioPane() {
    const [status, setStatus] = useState(null);
    const [partial, setPartial] = useState("");
    const [finalText, setFinalText] = useState("");
    const [latestDialog, setLatestDialog] = useState(null);
    const [error, setError] = useState("");
    const [recording, setRecording] = useState(false);
    const [voiceMode, setVoiceMode] = useState(true);
    const [voiceActivity, setVoiceActivity] = useState("idle");
    const [dialogPending, setDialogPending] = useState(false);
    const [playbackUnlocked, setPlaybackUnlocked] = useState(false);
    const [playbackBlocked, setPlaybackBlocked] = useState(false);
    const [playbackDetail, setPlaybackDetail] = useState("not unlocked");
    const [bargeInDetail, setBargeInDetail] = useState("idle");
    const [sttStreamState, setSttStreamState] = useState("stopped");
    const [sttCloseDetail, setSttCloseDetail] = useState("none");
    const [lastSttEvent, setLastSttEvent] = useState("none");
    const [reconnectDetail, setReconnectDetail] = useState("none");
    const socketRef = useRef(null);
    const mediaRef = useRef(null);
    const audioContextRef = useRef(null);
    const sourceRef = useRef(null);
    const processorRef = useRef(null);
    const muteRef = useRef(null);
    const playerRef = useRef(null);
    const voiceModeRef = useRef(true);
    const recordingRef = useRef(false);
    const dialogPendingRef = useRef(false);
    const suppressMicRef = useRef(false);
    const playbackUnlockedRef = useRef(false);
    const playbackStreamRef = useRef("");
    const playbackTimingRef = useRef(null);
    const bargeInFramesRef = useRef(0);
    const manualStopRef = useRef(false);
    const reconnectTimerRef = useRef(null);

    useEffect(() => { voiceModeRef.current = voiceMode; }, [voiceMode]);
    useEffect(() => { recordingRef.current = recording; }, [recording]);
    useEffect(() => { dialogPendingRef.current = dialogPending; }, [dialogPending]);
    useEffect(() => { playbackUnlockedRef.current = playbackUnlocked; }, [playbackUnlocked]);

    const loadStatus = useCallback(async () => {
      try {
        const data = await fetchJSON("/api/v1/audio/status");
        setStatus(data);
        const streamEvent = data && data.stt && data.stt.last_stream_event;
        if (streamEvent) {
          const reason = streamEvent.reason || "closed";
          setSttCloseDetail(`${reason} · ${streamEvent.recoverable ? "recoverable" : "fatal"}`);
          setLastSttEvent(streamEvent.message || reason);
        }
      } catch (err) {
        setError(err.message);
      }
    }, []);

    useEffect(() => { loadStatus(); }, [loadStatus]);
    useInterval(loadStatus, 5000);

    const cleanupMicInput = useCallback(() => {
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (processorRef.current) processorRef.current.disconnect();
      if (sourceRef.current) sourceRef.current.disconnect();
      if (muteRef.current) muteRef.current.disconnect();
      if (mediaRef.current) mediaRef.current.getTracks().forEach((track) => track.stop());
      if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
      processorRef.current = null;
      sourceRef.current = null;
      muteRef.current = null;
      mediaRef.current = null;
      audioContextRef.current = null;
    }, []);

    const stopMic = useCallback(() => {
      manualStopRef.current = true;
      const socket = socketRef.current;
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "stop" }));
      }
      if (socket) socket.close();
      socketRef.current = null;
      cleanupMicInput();
      setRecording(false);
      setVoiceActivity("idle");
      setSttStreamState("stopped");
      setSttCloseDetail("manual stop");
      setReconnectDetail("none");
      setBargeInDetail("idle");
      bargeInFramesRef.current = 0;
      suppressMicRef.current = false;
    }, [cleanupMicInput]);

    useEffect(() => stopMic, [stopMic]);

    const unlockPlayback = useCallback(async () => {
      if (!playerRef.current) return false;
      const player = playerRef.current;
      const previousSrc = player.getAttribute("src") || "";
      const previousMuted = player.muted;
      try {
        player.muted = true;
        player.volume = 1;
        player.src = SILENT_WAV;
        player.load();
        await player.play();
        player.pause();
        player.currentTime = 0;
        if (previousSrc) player.src = previousSrc;
        player.muted = previousMuted;
        playbackUnlockedRef.current = true;
        setPlaybackUnlocked(true);
        setPlaybackBlocked(false);
        setPlaybackDetail("ready after user gesture");
        return true;
      } catch (err) {
        player.muted = previousMuted;
        if (previousSrc) player.src = previousSrc;
        playbackUnlockedRef.current = false;
        setPlaybackUnlocked(false);
        setPlaybackBlocked(true);
        const message = err && err.name === "NotAllowedError"
          ? "Playback permission was not granted by this browser gesture."
          : describeMediaError(player, "Playback unlock failed.");
        setPlaybackDetail(message);
        setError("Playback is blocked by the browser. Click Enable Playback, then Speak Latest.");
        return false;
      }
    }, []);

    const stopPlayback = useCallback((detail = "interrupted") => {
      const player = playerRef.current;
      const hadPlayback = Boolean(playbackStreamRef.current || (player && player.getAttribute("src")));
      if (player) {
        player.pause();
        player.removeAttribute("src");
        player.load();
      }
      playbackStreamRef.current = "";
      playbackTimingRef.current = null;
      bargeInFramesRef.current = 0;
      suppressMicRef.current = false;
      setPlaybackBlocked(false);
      setVoiceActivity(recordingRef.current ? "listening" : "idle");
      if (hadPlayback) {
        const detailText = String(detail || "interrupted");
        setPlaybackDetail(detailText);
        setBargeInDetail(detailText.startsWith("barge-in") ? "detected, playback stopped" : "idle");
      }
    }, []);

    const playStream = useCallback(async (streamId, timing = {}) => {
      if (!streamId || !playerRef.current) return false;
      suppressMicRef.current = true;
      bargeInFramesRef.current = 0;
      setVoiceActivity("speaking");
      setPlaybackBlocked(false);
      setBargeInDetail("armed while speaking");
      const player = playerRef.current;
      playbackStreamRef.current = streamId;
      const streamReceivedAt = timing.streamReceivedAt || nowMs();
      playbackTimingRef.current = {
        streamId,
        latencyRecordId: timing.latencyRecordId || null,
        streamReceivedAt,
      };
      player.muted = false;
      player.volume = 1;
      player.src = `/api/v1/audio/tts/stream/${encodeURIComponent(streamId)}?t=${Date.now()}`;
      player.load();
      try {
        await player.play();
        postPresentationLatency("dashboard.audio.play_resolved", streamReceivedAt, {
          latencyRecordId: timing.latencyRecordId,
          metadata: { stream_id: streamId },
        });
        playbackUnlockedRef.current = true;
        setPlaybackUnlocked(true);
        setPlaybackDetail(`playing ${compactId(streamId)}`);
        return true;
      } catch (err) {
        postPresentationLatency("dashboard.audio.play_resolved", streamReceivedAt, {
          latencyRecordId: timing.latencyRecordId,
          success: false,
          error: err && err.name ? err.name : "play_failed",
          metadata: { stream_id: streamId },
        });
        playbackTimingRef.current = null;
        suppressMicRef.current = false;
        bargeInFramesRef.current = 0;
        setVoiceActivity(recordingRef.current ? "listening" : "idle");
        setPlaybackBlocked(true);
        setBargeInDetail("idle");
        const message = err && err.name === "NotAllowedError"
          ? "Playback blocked: enable once from this browser tab."
          : describeMediaError(player, "Playback failed.");
        setPlaybackDetail(message);
        setError("Playback is blocked by the browser. Click Enable Playback or Speak Latest.");
        return false;
      }
    }, []);

    const submitTranscript = useCallback(async (value) => {
      const transcript = String(value || "").trim();
      if (!transcript || dialogPendingRef.current) return;
      const finalStartedAt = nowMs();
      let playbackStarted = false;
      try {
        setError("");
        setFinalText(transcript);
        setDialogPending(true);
        dialogPendingRef.current = true;
        suppressMicRef.current = true;
        setVoiceActivity("thinking");
        const result = await fetchJSON("/api/v1/audio/dialog", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript }),
        });
        const responseAt = nowMs();
        postPresentationLatency("dashboard.audio_dialog.response", finalStartedAt, {
          latencyRecordId: result.latency_record_id,
          metadata: {
            audio_session_id: result.audio_session_id,
            transcript_chars: transcript.length,
          },
        });
        setLatestDialog(result);
        window.dispatchEvent(new CustomEvent("entity:turn-complete", {
          detail: {
            source: "audio_dialog",
            input_text: transcript,
            output: result,
          },
        }));
        loadStatus();
        if (result.tts_stream_id) {
          playbackStarted = await playStream(result.tts_stream_id, {
            latencyRecordId: result.latency_record_id,
            streamReceivedAt: responseAt,
          });
        }
      } catch (err) {
        setError(err.message);
      } finally {
        setDialogPending(false);
        dialogPendingRef.current = false;
        if (!playbackStarted) {
          suppressMicRef.current = false;
          setVoiceActivity(recordingRef.current ? "listening" : "idle");
        }
      }
    }, [loadStatus, playStream]);

    const startMic = useCallback(async () => {
      if (recording) return;
      try {
        setError("");
        setPartial("");
        setSttStreamState("connecting");
        setSttCloseDetail("none");
        setReconnectDetail("none");
        manualStopRef.current = false;
        stopPlayback();
        await unlockPlayback();
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
        });
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        const context = new AudioContextClass();
        await context.resume();
        const targetRate = Number(status && status.stt && status.stt.sample_rate) || 16000;
        const chunkMs = Number(status && status.stt && status.stt.chunk_ms) || 200;
        const socket = new WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api/v1/audio/stt/stream`);
        socket.binaryType = "arraybuffer";
        socket.onopen = () => {
          setSttStreamState("open");
          setLastSttEvent("websocket open");
          socket.send(JSON.stringify({
            type: "start",
            format: "pcm_s16le",
            sample_rate: targetRate,
            channels: 1,
            chunk_ms: chunkMs,
          }));
        };
        socket.onmessage = (event) => {
          if (typeof event.data !== "string") return;
          let data = null;
          try { data = JSON.parse(event.data); } catch { return; }
          if (data.type === "transcript.partial") setPartial(data.text || "");
          if (data.type === "stt.start") {
            setSttStreamState("streaming");
            setLastSttEvent(`session ${compactId(data.session_id || "")}`);
          }
          if (data.type === "stt.stream_closed") {
            const reason = data.reason || "closed";
            const recoverable = data.recoverable ? "recoverable" : "fatal";
            setSttStreamState("closed");
            setSttCloseDetail(`${reason} · ${recoverable}`);
            setLastSttEvent(data.message || reason);
          }
          if (data.type === "transcript.final") {
            const text = data.text || "";
            setFinalText(text);
            setPartial("");
            if (voiceModeRef.current) submitTranscript(text);
          }
          if (data.type === "error" || data.type === "warning") {
            setError(`${data.code || data.type}${data.message ? `: ${data.message}` : ""}`);
          }
        };
        socket.onerror = () => setError("Audio STT stream connection failed.");
        socket.onclose = () => {
          const shouldReconnect = !manualStopRef.current && voiceModeRef.current;
          socketRef.current = null;
          cleanupMicInput();
          setRecording(false);
          setVoiceActivity(shouldReconnect ? "reconnecting" : "idle");
          setSttStreamState(shouldReconnect ? "reconnecting" : "stopped");
          setReconnectDetail(shouldReconnect ? "scheduled after stream close" : "none");
          if (shouldReconnect) {
            reconnectTimerRef.current = window.setTimeout(() => {
              reconnectTimerRef.current = null;
              if (!manualStopRef.current) startMic();
            }, 450);
          }
        };

        const source = context.createMediaStreamSource(stream);
        const processor = context.createScriptProcessor(4096, 1, 1);
        const mute = context.createGain();
        mute.gain.value = 0;
        processor.onaudioprocess = (event) => {
          if (!socketRef.current || socketRef.current.readyState !== WebSocket.OPEN) return;
          const input = event.inputBuffer.getChannelData(0);
          const pcm = downsampleToInt16(input, context.sampleRate, targetRate);
          if (pcm.byteLength <= 0) return;
          if (playbackStreamRef.current) {
            if (pcmHasVoiceActivity(pcm)) {
              bargeInFramesRef.current += 1;
            } else {
              bargeInFramesRef.current = Math.max(0, bargeInFramesRef.current - 1);
            }
            if (bargeInFramesRef.current >= 2) {
              stopPlayback("barge-in: user speech detected");
              socketRef.current.send(pcm);
              return;
            }
          }
          if (suppressMicRef.current || dialogPendingRef.current) {
            socketRef.current.send(new Int16Array(pcm.byteLength / 2).buffer);
            return;
          }
          socketRef.current.send(pcm);
        };
        source.connect(processor);
        processor.connect(mute);
        mute.connect(context.destination);

        socketRef.current = socket;
        mediaRef.current = stream;
        audioContextRef.current = context;
        sourceRef.current = source;
        processorRef.current = processor;
        muteRef.current = mute;
        setRecording(true);
        setVoiceActivity("listening");
      } catch (err) {
        stopMic();
        setSttStreamState("error");
        setError(err.message || String(err));
      }
    }, [cleanupMicInput, recording, status, stopMic, stopPlayback, submitTranscript, unlockPlayback]);

    const sendFinal = useCallback(async () => {
      submitTranscript(finalText);
    }, [finalText, submitTranscript]);

    const speakLatest = useCallback(() => {
      const streamId = latestDialog && latestDialog.tts_stream_id
        ? latestDialog.tts_stream_id
        : status && status.tts && status.tts.last_stream_id;
      playStream(streamId);
    }, [latestDialog, playStream, status]);

    const enabled = status && status.enabled;
    return h("div", { className: "section audio-section" },
      h("div", { className: "section-title" }, "Audio Adapter"),
      h("div", { className: "toolbar" },
        h("span", { className: "dim" }, "Mic"),
        h("button", {
          className: `btn-sm ${recording || sttStreamState === "connecting" || sttStreamState === "reconnecting" ? "active" : ""}`,
          onClick: startMic,
          disabled: recording || sttStreamState === "connecting" || sttStreamState === "reconnecting",
        }, recording ? "Mic On" : sttStreamState === "reconnecting" ? "Reconnecting" : "Mic Start"),
        h("button", { className: "btn-sm", onClick: stopMic, disabled: !recording }, "Mic Stop"),
        h("span", { className: "dim" }, "Playback"),
        h("button", { className: `btn-sm ${playbackUnlocked ? "active" : ""}`, onClick: unlockPlayback }, playbackUnlocked ? "Playback Ready" : "Enable Playback"),
        h("button", { className: `btn-sm ${voiceActivity === "speaking" ? "active" : ""}`, onClick: () => stopPlayback(), disabled: voiceActivity !== "speaking" }, "Stop Speaking"),
      ),
      h("div", { className: "toolbar" },
        h("span", { className: "dim" }, "Dialogue"),
        h("button", {
          className: `btn-sm ${voiceMode ? "active" : ""}`,
          onClick: () => setVoiceMode((value) => !value),
        }, voiceMode ? "Voice Auto On" : "Voice Auto Off"),
        h("button", { className: `btn-sm ${dialogPending ? "active" : ""}`, onClick: sendFinal, disabled: dialogPending }, dialogPending ? "Thinking" : "Send Final"),
        h("button", { className: "btn-sm", onClick: speakLatest }, "Speak Latest"),
        h("button", { className: "btn-sm", onClick: loadStatus }, "Refresh Status"),
      ),
      h("div", { className: "kv-grid audio-kv" },
        h("span", null, "Provider"), h("span", null, status ? status.provider : "—"),
        h("span", null, "Provider status"), h("span", { className: enabled ? "ok" : "err" }, status ? (enabled ? "enabled" : status.reason) : "loading"),
        h("span", null, "Mic"), h("span", { className: recording ? "ok" : "dim" }, recording ? "recording" : "stopped"),
        h("span", null, "STT stream"), h("span", { className: sttStreamState === "streaming" ? "ok" : sttStreamState === "error" ? "err" : "dim" }, sttStreamState),
        h("span", null, "STT close"), h("span", { className: "dim" }, sttCloseDetail),
        h("span", null, "Last STT event"), h("span", { className: "dim" }, lastSttEvent),
        h("span", null, "Reconnect"), h("span", { className: sttStreamState === "reconnecting" ? "ok" : "dim" }, reconnectDetail),
        h("span", null, "Playback"), h("span", { className: playbackBlocked ? "err" : playbackUnlocked ? "ok" : "dim" }, playbackBlocked ? "blocked" : playbackUnlocked ? "ready" : "locked"),
        h("span", null, "Playback detail"), h("span", { className: playbackBlocked ? "err" : "dim" }, playbackDetail),
        h("span", null, "Barge-in"), h("span", { className: bargeInDetail.startsWith("detected") ? "ok" : "dim" }, bargeInDetail),
        h("span", null, "Voice mode"), h("span", { className: voiceMode && recording ? "ok" : "" }, `${voiceMode ? "auto" : "manual"} · ${voiceActivity}`),
        h("span", null, "STT"), h("span", null, status && status.stt ? `${status.stt.sample_rate || "—"}Hz · ${status.stt.chunk_ms || "—"}ms · ${status.stt.active_sessions || 0} active` : "—"),
        h("span", null, "STT endpoint"), h("span", null, status && status.stt ? `${status.stt.endpoint || "—"} · ${status.stt.resource_id || "—"}` : "—"),
        h("span", null, "TTS"), h("span", null, status && status.tts ? `${status.tts.output_format || "—"} · ${status.tts.sample_rate || "—"}Hz · ${status.tts.voice_type || "voice not set"}` : "—"),
        h("span", null, "TTS endpoint"), h("span", null, status && status.tts ? `${status.tts.endpoint || "—"} · ${status.tts.resource_id || "—"}` : "—"),
        h("span", null, "Logids"), h("span", null, status ? `stt ${status.stt && status.stt.last_logid ? compactId(status.stt.last_logid) : "—"} · tts ${status.tts && status.tts.last_logid ? compactId(status.tts.last_logid) : "—"}` : "—"),
      ),
      h("label", { className: "audio-label" }, "Partial",
        h("div", { className: "audio-transcript partial" }, partial || "—"),
      ),
      h("label", { className: "audio-label" }, "Final transcript",
        h("textarea", {
          value: finalText,
          onChange: (event) => setFinalText(event.target.value),
          placeholder: "Final transcript from STT…",
        }),
      ),
      latestDialog ? h("div", { className: "item" },
        h("div", { className: "item-meta" }, `tts: ${latestDialog.tts_stream_id || latestDialog.audio_disabled_reason || "silent"}`),
        h("div", { className: "item-text" }, latestDialog.output_text || "..."),
      ) : null,
      error ? h("div", { className: "err" }, error) : null,
      h("audio", {
        ref: playerRef,
        className: "hidden-audio",
        preload: "auto",
        playsInline: true,
        onPlaying: () => {
          const timing = playbackTimingRef.current;
          if (timing) {
            postPresentationLatency("dashboard.audio.playing", timing.streamReceivedAt, {
              latencyRecordId: timing.latencyRecordId,
              metadata: { stream_id: timing.streamId },
            });
          }
        },
        onEnded: () => {
          const timing = playbackTimingRef.current;
          if (timing) {
            postPresentationLatency("dashboard.audio.ended", timing.streamReceivedAt, {
              latencyRecordId: timing.latencyRecordId,
              metadata: { stream_id: timing.streamId },
            });
          }
          playbackStreamRef.current = "";
          playbackTimingRef.current = null;
          bargeInFramesRef.current = 0;
          suppressMicRef.current = false;
          setVoiceActivity(recordingRef.current ? "listening" : "idle");
          setPlaybackDetail("ended");
          setBargeInDetail("idle");
        },
        onError: () => {
          const timing = playbackTimingRef.current;
          if (timing) {
            postPresentationLatency("dashboard.audio.error", timing.streamReceivedAt, {
              latencyRecordId: timing.latencyRecordId,
              success: false,
              error: "media_error",
              metadata: { stream_id: timing.streamId },
            });
          }
          playbackStreamRef.current = "";
          playbackTimingRef.current = null;
          bargeInFramesRef.current = 0;
          suppressMicRef.current = false;
          setVoiceActivity(recordingRef.current ? "listening" : "idle");
          setPlaybackBlocked(true);
          setPlaybackDetail(describeMediaError(playerRef.current, "Playback stream error."));
          setBargeInDetail("idle");
        },
      }),
    );
  }

  function ConfigSection({ title, data, fields }) {
    return h("div", { className: "section" },
      h("div", { className: "section-title" }, title),
      data ? h("table", null, h("tbody", null,
        fields.map((field) => h("tr", { key: field },
          h("td", { className: "dim" }, field),
          h("td", { className: field === "error" && data[field] ? "err" : "" }, String(data[field] || "—")),
        )),
      )) : h("div", { className: "dim" }, "Loading…"),
    );
  }

  function MemoryCurationPane() {
    const [view, setView] = useState("raw");
    return h(React.Fragment, null,
      h("div", { className: "toolbar", style: { marginBottom: "10px" } },
        ["raw", "proposals", "managed", "influence"].map((name) => h("button", {
          key: name,
          className: "btn-sm",
          onClick: () => setView(name),
        }, name)),
      ),
      view === "raw" ? h(RawArchive) : view === "proposals" ? h(MemoryProposals) : view === "managed" ? h(ManagedMemoryList) : h(InfluenceTrace),
    );
  }

  function RawArchive() {
    const [rows, setRows] = useState([]);
    const load = useCallback(async () => {
      setRows(await fetchJSON("/api/v1/interaction-log?limit=80").catch(() => []));
    }, []);
    useEffect(() => { load(); }, [load]);
    return h("div", { className: "card-list" }, rows.map((row) => h("div", { className: "item", key: row.id },
      h("div", { className: "item-meta" }, `turn #${row.id} · ${row.role || ""} · ${row.turn_at || ""} · ${row.policy_action || "—"}`),
      row.raw_text ? h("div", { className: "item-text" }, String(row.raw_text).slice(0, 420)) : null,
      row.expression_output ? h("div", { className: "item-text dim" }, String(row.expression_output).slice(0, 420)) : null,
    )));
  }

  function MemoryProposals() {
    const [rows, setRows] = useState([]);
    const load = useCallback(async () => {
      const data = await fetchJSON("/api/v1/managed-memory/proposals?status=pending&limit=120").catch(() => ({ proposals: [] }));
      setRows(data.proposals || []);
    }, []);
    useEffect(() => { load(); }, [load]);

    const action = async (id, kind) => {
      try {
        if (kind === "commit") {
          await fetchJSON("/api/v1/managed-memory/commit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ proposal_ids: [id], operations: [] }),
          });
        } else {
          await fetchJSON(`/api/v1/managed-memory/proposals/${id}/reject`, { method: "POST" });
        }
        load();
      } catch (error) {
        alert(error.message);
      }
    };

    return h("div", { className: "card-list" }, rows.length ? rows.map((row) => h("div", { className: "item", key: row.id },
      h("div", { className: "item-meta" }, `proposal #${row.id} · ${row.operation} · ${row.status} · confidence ${row.confidence}`),
      h("div", { className: "item-text" }, String(row.content || row.reason || "").slice(0, 360)),
      h("div", { className: "item-actions" },
        h("button", { className: "btn-sm", onClick: () => action(row.id, "commit") }, "Commit"),
        h("button", { className: "btn-sm", onClick: () => action(row.id, "reject") }, "Reject"),
      ),
    )) : h("div", { className: "dim" }, "No pending proposals."));
  }

  function ManagedMemoryList() {
    const [rows, setRows] = useState([]);
    const load = useCallback(async () => {
      const data = await fetchJSON("/api/v1/managed-memory?status=active&q=&limit=80").catch(() => ({ rows: [] }));
      setRows(data.rows || []);
    }, []);
    useEffect(() => { load(); }, [load]);
    return h("div", { className: "card-list" }, rows.length ? rows.map((row) => h("div", { className: "item", key: row.id },
      h("div", { className: "item-meta" }, `managed #${row.id} · ${row.status} · ${row.memory_kind} · confidence ${row.confidence}`),
      h("div", { className: "item-text" }, String(row.content || "").slice(0, 420)),
    )) : h("div", { className: "dim" }, "No active managed memories."));
  }

  function InfluenceTrace() {
    const [rows, setRows] = useState([]);
    const load = useCallback(async () => {
      const data = await fetchJSON("/api/v1/managed-memory/influence-log?limit=8").catch(() => ({ rows: [] }));
      setRows(data.rows || []);
    }, []);
    useEffect(() => { load(); }, [load]);
    return h("div", { className: "card-list" }, rows.length ? rows.map((row, index) => h("div", { className: "item", key: index },
      h("div", { className: "item-meta" }, `turn ${row.turn_id || "—"} · ${row.policy_action || ""} · ${row.influenced_at || ""}`),
      h("div", { className: "item-text" }, String(row.query || "").slice(0, 260)),
    )) : h("div", { className: "dim" }, "No influence trace yet."));
  }

  function SessionHistoryPane() {
    const [sessions, setSessions] = useState([]);
    const [selected, setSelected] = useState("");
    const [detail, setDetail] = useState(null);

    const loadSessions = useCallback(async () => {
      const data = await fetchJSON("/api/v1/sessions").catch(() => []);
      setSessions(data);
      const active = data.find((item) => item.active) || data[0];
      setSelected((current) => current || (active && active.id) || "");
    }, []);

    useEffect(() => { loadSessions(); }, [loadSessions]);
    useInterval(loadSessions, 15000);

    useEffect(() => {
      if (!selected) return;
      Promise.all([
        fetchJSON(`/api/v1/sessions/${encodeURIComponent(selected)}/conversation?limit=200`),
        fetchJSON(`/api/v1/sessions/${encodeURIComponent(selected)}/memory/episodic?limit=50`),
        fetchJSON(`/api/v1/sessions/${encodeURIComponent(selected)}/memory/reflective`),
      ]).then(([conversation, episodic, reflective]) => {
        setDetail({ conversation, episodic, reflective });
      }).catch(() => setDetail(null));
    }, [selected]);

    return h("div", { className: "history-grid" },
      h("div", { className: "session-list" }, sessions.map((session) => h("button", {
        key: session.id,
        className: `session-item ${selected === session.id ? "active" : ""}`,
        onClick: () => setSelected(session.id),
      },
        h("div", { className: "session-title" }, h("span", null, compactId(session.id)), h("span", null, session.active ? "active" : session.ended_at ? "archived" : "open")),
        h("div", { className: "session-meta" }, `${session.session_type || "test"} · ${session.turn_count} turns · ${session.memory_count} episodic`),
      ))),
      h("div", { className: "session-detail" },
        detail ? h(React.Fragment, null,
          h("div", { className: "item-meta" }, `${compactId(selected)} · ${(detail.conversation.turns || []).length} turns · ${detail.episodic.length} episodic · ${detail.reflective.length} reflections`),
          (detail.conversation.turns || []).map((turn, index) => h("div", { className: "item", key: index },
            h("div", { className: "item-meta" }, `user · ${formatTime(turn.turn_at)}`),
            h("div", { className: "item-text" }, turn.user_text || ""),
            h("div", { className: "item-meta" }, `entity · ${turn.policy_action || ""}`),
            h("div", { className: "item-text" }, turn.entity_text || "..."),
          )),
        ) : h("div", { className: "dim" }, "Select a session…")),
    );
  }

  function downsampleToInt16(input, sourceRate, targetRate) {
    if (!input || input.length === 0) return new ArrayBuffer(0);
    const ratio = sourceRate / targetRate;
    const outputLength = Math.max(1, Math.floor(input.length / ratio));
    const buffer = new ArrayBuffer(outputLength * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < outputLength; i += 1) {
      const start = Math.floor(i * ratio);
      const end = Math.min(input.length, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = start; j < end; j += 1) sum += input[j];
      const sample = clamp(sum / Math.max(1, end - start), -1, 1);
      view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    }
    return buffer;
  }

  function pcmHasVoiceActivity(buffer) {
    const samples = new Int16Array(buffer);
    if (!samples.length) return false;
    let peak = 0;
    let squareSum = 0;
    for (let i = 0; i < samples.length; i += 1) {
      const value = Math.abs(samples[i]);
      if (value > peak) peak = value;
      squareSum += value * value;
    }
    const rms = Math.sqrt(squareSum / samples.length);
    return peak >= 3500 || rms >= 850;
  }

  function ConfigModal({ onClose }) {
    const [configs, setConfigs] = useState(null);
    const [active, setActive] = useState("");

    useEffect(() => {
      fetchJSON("/api/v1/config").then((data) => {
        setConfigs(data);
        setActive(Object.keys(data)[0] || "");
      }).catch(() => setConfigs({ error: "Failed to load config." }));
    }, []);

    const keys = configs ? Object.keys(configs) : [];

    return h("div", { className: "config-overlay", onMouseDown: (event) => { if (event.target === event.currentTarget) onClose(); } },
      h("div", { className: "config-modal" },
        h("div", { className: "config-modal-header" },
          h("span", null, "YAML Configuration"),
          h("button", { className: "btn-sm", onClick: onClose }, "Close"),
        ),
        h("div", { className: "config-tabs" },
          keys.map((key) => h("button", {
            key,
            className: "btn-sm",
            onClick: () => setActive(key),
          }, key)),
        ),
        h("pre", { className: "config-pre" }, configs ? JSON.stringify(configs[active] || configs, null, 2) : "Loading…"),
      ),
    );
  }

  ReactDOM.createRoot(document.getElementById("root")).render(h(App));
})();
