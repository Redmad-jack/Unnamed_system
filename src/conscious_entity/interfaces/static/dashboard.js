(function () {
  "use strict";

  const { useCallback, useEffect, useMemo, useRef, useState } = React;
  const h = React.createElement;

  const STATE_KEYS = [
    "desperation_pressure", "confusion", "anger", "fatigue_level", "exposure_pressure",
    "inquiry", "care_response", "positive_opening", "memory_gravity", "happiness",
  ];

  const STATE_LABELS = {
    memory_gravity: "memory_gravity / 恋旧",
    happiness: "happiness (display)",
  };

  const MOTION_LABELS = {
    stopped: "Stopped",
    forward: "Forward",
    reverse: "Reverse",
    turning_left: "Forward left",
    turning_right: "Forward right",
    reverse_left: "Reverse left",
    reverse_right: "Reverse right",
    spin_left: "Spin left",
    spin_right: "Spin right",
    roaming: "Roaming",
    mixed: "Mixed",
  };

  const LAYOUT_DEFAULTS = {
    left: 440,
    right: 420,
    bottom: 430,
  };

  const SILENT_WAV =
    "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQQAAAAAAA==";
  const BARGE_IN_GRACE_MS = 900;
  const BARGE_IN_TRIGGER_FRAMES = 5;
  const BARGE_IN_PEAK_THRESHOLD = 6000;
  const BARGE_IN_RMS_THRESHOLD = 1200;
  const TTS_PREFETCH_WAIT_MS = 120;

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

  async function fetchNDJSON(url, options, onEvent) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const text = await response.text().catch(() => "");
      throw new Error(text || response.statusText || String(response.status));
    }
    if (!response.body) return;
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;
        onEvent(JSON.parse(trimmed));
      }
    }
    buffer += decoder.decode();
    const trimmed = buffer.trim();
    if (trimmed) onEvent(JSON.parse(trimmed));
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

  function ttsStreamUrl(streamId) {
    return `/api/v1/audio/tts/stream/${encodeURIComponent(streamId)}?t=${Date.now()}`;
  }

  function revokeObjectUrl(objectUrl) {
    if (!objectUrl) return;
    try {
      window.URL.revokeObjectURL(objectUrl);
    } catch {
      // Best effort cleanup only.
    }
  }

  function browserCameraCapability() {
    const mediaDevices = Boolean(navigator.mediaDevices);
    return {
      secure_context: Boolean(window.isSecureContext),
      media_devices: mediaDevices,
      get_user_media: Boolean(mediaDevices && navigator.mediaDevices.getUserMedia),
      enumerate_devices: Boolean(mediaDevices && navigator.mediaDevices.enumerateDevices),
      protocol: window.location.protocol,
      user_agent: navigator.userAgent,
    };
  }

  function errorSummary(error) {
    if (!error) return "unknown error";
    const name = error.name || "Error";
    const message = error.message || String(error);
    return `${name}: ${message}`;
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
      .map((row) => ({ ...row, response_plan: parseResponsePlan(row) }))
      .sort((a, b) => rowTimeMs(a) - rowTimeMs(b) || rowOrder(a) - rowOrder(b));
  }

  function parseResponsePlan(row) {
    if (!row) return null;
    if (row.response_plan && typeof row.response_plan === "object") return row.response_plan;
    const raw = row.response_plan_json;
    if (!raw || typeof raw !== "string") return null;
    try {
      const parsed = JSON.parse(raw);
      return parsed && typeof parsed === "object" ? parsed : null;
    } catch {
      return null;
    }
  }

  function responsePlanText(row) {
    const plan = parseResponsePlan(row);
    if (!plan) return row && row.expression_output;
    const fullResponse = String(plan.full_response || "").trim() || String(plan.second_unit || "").trim();
    const unitText = [
      plan.first_unit,
      fullResponse,
    ]
      .map((unit) => String(unit || "").trim())
      .filter(Boolean)
      .join("\n");
    return unitText || plan.combined_text || (row && row.expression_output);
  }

  function finalSecondUnitText(event) {
    const plan = event && event.response_plan;
    if (plan && typeof plan === "object") {
      return String(plan.full_response || "").trim() || String(plan.second_unit || "").trim();
    }
    return String(event && event.text ? event.text : "").trim();
  }

  function firstUnitRenderableText(event) {
    if (!event || event.phase !== "first_unit") return "";
    const plan = event.response_plan;
    const candidates = [
      event.text,
      event.output_text,
      event.progressive_text,
      plan && typeof plan === "object" ? plan.first_unit : "",
    ];
    for (const candidate of candidates) {
      const text = String(candidate || "").trim();
      if (text) return text;
    }
    return "";
  }

  function appendProgressiveText(current, next) {
    const left = String(current || "").trim();
    const right = String(next || "").trim();
    if (!right) return left;
    return left ? `${left}\n${right}` : right;
  }

  function vocalMarkerLabel(value) {
    const key = String(value || "none");
    if (key === "thinking") return "vocal: 嗯……";
    if (key === "sigh") return "vocal: 唉。";
    return key && key !== "none" ? `vocal: ${key}` : "";
  }

  function bodyActionLabel(value) {
    const labels = {
      pause: "body: pause",
      lean_in: "body: lean in",
      step_back: "body: step back",
      turn_away_30deg: "body: 转身 30 度",
      circle_back: "body: circle back",
      withdraw: "body: withdraw",
      distance_increase: "body: distance increase",
    };
    const key = String(value || "none");
    return key && key !== "none" ? (labels[key] || `body: ${key}`) : "";
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
    const [armState, setArmState] = useState({ status: "idle", detail: "not armed" });
    const armStreamsRef = useRef([]);

    useEffect(() => { writeLayout(layout); }, [layout]);
    useEffect(() => () => {
      armStreamsRef.current.forEach((stream) => {
        stream.getTracks().forEach((track) => track.stop());
      });
    }, []);

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

    const armExhibition = useCallback(async () => {
      setArmState({ status: "arming", detail: "requesting camera, mic, playback" });
      armStreamsRef.current.forEach((stream) => {
        stream.getTracks().forEach((track) => track.stop());
      });
      armStreamsRef.current = [];

      const results = [];
      const requestMedia = async (kind, constraints) => {
        try {
          const stream = await navigator.mediaDevices.getUserMedia(constraints);
          armStreamsRef.current.push(stream);
          const track = stream.getTracks()[0];
          results.push({ kind, ok: true, label: track ? track.label : kind });
        } catch (error) {
          results.push({ kind, ok: false, error: errorSummary(error) });
        }
      };

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        const detail = "browser media API unavailable";
        setArmState({ status: "error", detail });
        fetchJSON("/api/v1/vision/client-log", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "exhibition_arm_unavailable",
            detail: { summary: detail, capability: browserCameraCapability() },
            at: new Date().toISOString(),
          }),
        }).catch(() => null);
        return;
      }

      await requestMedia("camera", { audio: false, video: true });
      await requestMedia("mic", { audio: true, video: false });

      let playbackOk = false;
      let playbackError = null;
      try {
        const player = new Audio(SILENT_WAV);
        player.volume = 0.01;
        await player.play();
        player.pause();
        playbackOk = true;
      } catch (error) {
        playbackError = errorSummary(error);
      }

      const failed = results.filter((item) => !item.ok);
      if (!playbackOk) {
        failed.push({ kind: "playback", ok: false, error: playbackError || "playback unlock failed" });
      }
      const detail = failed.length
        ? failed.map((item) => `${item.kind}: ${item.error}`).join(" | ")
        : `camera, mic, playback ready`;
      setArmState({ status: failed.length ? "error" : "ready", detail });
      fetchJSON("/api/v1/vision/client-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: failed.length ? "exhibition_arm_error" : "exhibition_arm_ready",
          detail: {
            summary: detail,
            results,
            playback: { ok: playbackOk, error: playbackError },
            capability: browserCameraCapability(),
          },
          at: new Date().toISOString(),
        }),
      }).catch(() => null);
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
        armState,
        onArm: armExhibition,
        onConfig: () => setConfigOpen(true),
      }),
      h("main", { className, style: gridStyle },
        h(Panel, { title: "Entity State", className: "state-panel" }, h(EntityState)),
        h(Panel, { title: "Vision", className: "vision-panel", bodyClassName: "vision-body" }, h(VisionPanel)),
        h(Panel, { title: "Dialog", className: "dialog-panel", bodyClassName: "dialog-panel" }, h(DialogPanel)),
        h(Panel, { title: "Memory System", className: "memory-panel" }, h(MemorySummary, {
          onSave: saveConversation,
          onReset: resetMemory,
        })),
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

  function Header({ health, sessionType, onSessionTypeChange, armState, onArm, onConfig }) {
    const status = health && health.status ? health.status : "connecting";
    const armStatus = armState && armState.status ? armState.status : "idle";
    const armLabel = armStatus === "arming" ? "ARMING" : `ARM: ${armStatus.toUpperCase()}`;
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
      h("button", { className: "btn-sm", onClick: onConfig }, "YAML Config"),
      h("button", {
        className: armStatus === "ready" ? "btn-sm active arm-button" : `btn-sm arm-button ${armStatus === "error" ? "err-action" : ""}`,
        onClick: onArm,
        disabled: armStatus === "arming",
        title: armState ? armState.detail : "",
      }, armLabel),
      h("div", { className: "header-spacer" }),
      h("span", { className: "session-label" }, health && health.session_id ? `session: ${compactId(health.session_id)} · ${sessionType} · visitor: ${health.visitor_id ? compactId(health.visitor_id) : "none"}` : "session: —"),
    );
  }

  function EntityState() {
    const [state, setState] = useState(null);
    const [displayHappiness, setDisplayHappiness] = useState(() => Math.random());

    const load = useCallback(async () => {
      try {
        setState(await fetchJSON("/api/v1/state"));
      } catch {
        setState(null);
      }
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 2000);
    useInterval(() => { setDisplayHappiness(Math.random()); }, 10000);

    if (!state) return h("div", { className: "dim" }, "Loading state…");

    return h(React.Fragment, null,
      STATE_KEYS.map((key) => {
        const raw = key === "happiness" ? displayHappiness : Number(state[key] || 0);
        const pct = clamp(Math.round(raw * 100), 0, 100);
        const label = STATE_LABELS[key] || key;
        return h("div", { className: "state-var", key },
          h("div", { className: "state-var-name" }, label),
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
    const [cameraOptions, setCameraOptions] = useState(() => [{ deviceId: "", label: "Default Camera" }]);
    const [scanning, setScanning] = useState(false);
    const [browserCameraActive, setBrowserCameraActive] = useState(false);
    const [browserCameraError, setBrowserCameraError] = useState("");
    const [cameraDebug, setCameraDebug] = useState({
      action: "idle",
      detail: "Default Camera is available before scanning.",
    });
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

    const reportCameraDebug = useCallback((event, detail = {}) => {
      const payload = {
        event,
        detail: {
          ...detail,
          capability: browserCameraCapability(),
        },
        at: new Date().toISOString(),
      };
      setCameraDebug({
        action: event,
        detail: detail.summary || JSON.stringify(payload.detail),
      });
      fetchJSON("/api/v1/vision/client-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }).catch(() => null);
    }, []);

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
      setBrowserCameraError("");
      reportCameraDebug("scan_start", { summary: "Scan requested." });
      try {
        const capability = browserCameraCapability();
        if (!capability.get_user_media) {
          const cameras = [{ deviceId: "", label: "Default Camera" }];
          setCameraOptions(cameras);
          setSelectedCameraId("");
          const message = "Browser camera API is not available in this webview/browser.";
          setError(message);
          reportCameraDebug("scan_unavailable", { summary: message, capability });
          return;
        }
        let devices = navigator.mediaDevices.enumerateDevices
          ? await navigator.mediaDevices.enumerateDevices()
          : [];
        let permissionStream = null;
        let permissionError = null;
        const hasNamedCamera = devices.some((device) => device.kind === "videoinput" && device.label);
        if (!hasNamedCamera && !browserStreamRef.current) {
          try {
            permissionStream = await navigator.mediaDevices.getUserMedia({ audio: false, video: true });
            devices = navigator.mediaDevices.enumerateDevices
              ? await navigator.mediaDevices.enumerateDevices()
              : [];
          } catch (err) {
            permissionError = errorSummary(err);
          }
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
        if (permissionError) {
          setError(`Camera permission check failed: ${permissionError}`);
        } else {
          setError("");
        }
        reportCameraDebug("scan_done", {
          summary: `Scan finished: ${cameras.length} option(s).${permissionError ? " Permission check failed." : ""}`,
          device_count: devices.filter((device) => device.kind === "videoinput").length,
          options: cameras.map((camera) => camera.label),
          permission_error: permissionError,
        });
      } catch (err) {
        const message = errorSummary(err);
        setCameraOptions([{ deviceId: "", label: "Default Camera" }]);
        setSelectedCameraId("");
        setError(message);
        reportCameraDebug("scan_error", { summary: message });
      } finally {
        setScanning(false);
      }
    }, [reportCameraDebug, selectedCameraId]);

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
        const message = "Browser camera capture is not available.";
        setBrowserCameraError(message);
        reportCameraDebug("connect_unavailable", { summary: message });
        return;
      }
      try {
        stopBrowserCamera();
        setBrowserCameraError("");
        setError("");
        const targetWidth = Number((status && status.config && status.config.width) || 1280);
        const targetHeight = Number((status && status.config && status.config.height) || 720);
        const selected = cameraOptions.find((item) => item.deviceId === selectedCameraId);
        reportCameraDebug("connect_start", {
          summary: `Connect requested: ${selected ? selected.label : "Default Camera"}.`,
          selected_camera: selected ? selected.label : "Default Camera",
          selected_camera_id_present: Boolean(selectedCameraId),
        });
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
        const track = stream.getVideoTracks()[0] || null;
        if (track && !selectedCameraId) {
          const label = track.label || "Default Camera";
          setCameraOptions([{ deviceId: "", label }]);
        }
        reportCameraDebug("connect_done", {
          summary: `Connected: ${(track && track.label) || "Default Camera"}.`,
          track_label: track && track.label,
          track_settings: track && track.getSettings ? track.getSettings() : null,
        });
        connectStream();
        await sendBrowserFrame();
        const targetFps = Math.min(5, Number((status && status.config && status.config.fps) || 5));
        const intervalMs = Math.max(200, Math.round(1000 / Math.max(1, targetFps)));
        browserIntervalRef.current = window.setInterval(sendBrowserFrame, intervalMs);
      } catch (err) {
        stopBrowserCamera();
        const message = errorSummary(err);
        setBrowserCameraError(message);
        reportCameraDebug("connect_error", { summary: message });
      }
    }, [
      cameraOptions,
      connectStream,
      reportCameraDebug,
      selectedCameraId,
      sendBrowserFrame,
      status,
      stopBrowserCamera,
    ]);

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
      h("div", { className: "item-meta" }, `Camera debug: ${cameraDebug.action} · ${cameraDebug.detail}`),
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
    const audioSecondRowIdRef = useRef(null);

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
        if (detail.source === "audio_dialog_progressive") {
          const now = new Date().toISOString();
          if (detail.phase === "first_unit") {
            const firstText = firstUnitRenderableText(detail);
            audioSecondRowIdRef.current = null;
            setRows((current) => {
              const nextRows = [...current];
              if (detail.input_text) {
                nextRows.push({
                  id: `audio-user-${Date.now()}`,
                  role: "user",
                  raw_text: detail.input_text,
                  turn_at: now,
                });
              }
              if (firstText) {
                nextRows.push({
                  id: `audio-first-${Date.now()}`,
                  role: "entity",
                  progressive_text: firstText,
                  phase: "first_unit",
                  visual_mode: detail.visual_mode,
                  vocal_marker: detail.vocal_marker,
                  body_action: detail.body_action,
                  policy_action: "audio_dialog_progressive",
                  turn_at: now,
                });
              }
              return nextRows;
            });
          } else if (detail.phase === "second_delta" && detail.text) {
            const deltaText = String(detail.text || "").trim();
            if (!deltaText) return;
            if (!audioSecondRowIdRef.current) {
              const secondRowId = `audio-second-${Date.now()}`;
              audioSecondRowIdRef.current = secondRowId;
              setRows((current) => [...current, {
                id: secondRowId,
                role: "entity",
                progressive_text: deltaText,
                phase: "second_delta",
                visual_mode: detail.visual_mode,
                vocal_marker: detail.vocal_marker,
                body_action: detail.body_action,
                policy_action: "audio_dialog_progressive",
                turn_at: now,
              }]);
            } else {
              const secondRowId = audioSecondRowIdRef.current;
              setRows((current) => current.map((row) => (
                row.id === secondRowId
                  ? {
                    ...row,
                    progressive_text: appendProgressiveText(row.progressive_text, deltaText),
                    phase: "second_delta",
                    visual_mode: detail.visual_mode || row.visual_mode,
                    vocal_marker: detail.vocal_marker || row.vocal_marker,
                    body_action: detail.body_action || row.body_action,
                  }
                  : row
              )));
            }
          } else if (detail.phase === "final") {
            const secondText = finalSecondUnitText(detail);
            const secondRowId = audioSecondRowIdRef.current;
            if (secondRowId) {
              setRows((current) => {
                if (!secondText) {
                  return current.filter((row) => row.id !== secondRowId);
                }
                return current.map((row) => (
                  row.id === secondRowId
                    ? {
                      ...row,
                      progressive_text: secondText,
                      phase: "final",
                      response_plan: detail.response_plan || null,
                      visual_mode: detail.visual_mode || row.visual_mode,
                      vocal_marker: detail.vocal_marker || row.vocal_marker,
                      body_action: detail.body_action || row.body_action,
                    }
                    : row
                ));
              });
              audioSecondRowIdRef.current = null;
            } else if (secondText) {
              setRows((current) => [...current, {
                id: `audio-final-${Date.now()}`,
                role: "entity",
                progressive_text: secondText,
                phase: "final",
                response_plan: detail.response_plan || null,
                visual_mode: detail.visual_mode,
                vocal_marker: detail.vocal_marker,
                body_action: detail.body_action,
                policy_action: "audio_dialog_progressive",
                turn_at: now,
              }]);
            }
          }
          return;
        }
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
            response_plan: detail.output.response_plan || null,
            delay_ms: detail.output.delay_ms,
            visual_mode: detail.output.visual_mode,
            vocal_marker: detail.output.vocal_marker,
            body_action: detail.output.body_action,
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
      let secondRowId = null;
      let sawSecondDelta = false;
      let finalPayload = null;
      const optimistic = {
        id: `pending-${Date.now()}`,
        role: "user",
        raw_text: trimmed,
        turn_at: new Date().toISOString(),
      };
      setRows((current) => [...current, optimistic]);
      try {
        await fetchNDJSON("/api/v1/dialog/progressive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text: trimmed }),
        }, (event) => {
          if (event.phase === "first_unit") {
            const firstText = firstUnitRenderableText(event);
            if (!firstText) return;
            setRows((current) => [...current, {
              id: `entity-first-${Date.now()}`,
              role: "entity",
              progressive_text: firstText,
              phase: "first_unit",
              visual_mode: event.visual_mode,
              vocal_marker: event.vocal_marker,
              body_action: event.body_action,
              turn_at: new Date().toISOString(),
            }]);
          } else if (event.phase === "second_delta" && event.text) {
            const deltaText = String(event.text || "").trim();
            if (!deltaText) return;
            sawSecondDelta = true;
            if (!secondRowId) {
              secondRowId = `entity-second-${Date.now()}`;
              setRows((current) => [...current, {
                id: secondRowId,
                role: "entity",
                progressive_text: deltaText,
                phase: "second_delta",
                visual_mode: event.visual_mode,
                vocal_marker: event.vocal_marker,
                body_action: event.body_action,
                policy_action: event.policy_action,
                turn_at: new Date().toISOString(),
              }]);
            } else {
              setRows((current) => current.map((row) => (
                row.id === secondRowId
                  ? {
                    ...row,
                    progressive_text: appendProgressiveText(row.progressive_text, deltaText),
                    phase: "second_delta",
                    visual_mode: event.visual_mode || row.visual_mode,
                    vocal_marker: event.vocal_marker || row.vocal_marker,
                    body_action: event.body_action || row.body_action,
                    policy_action: event.policy_action || row.policy_action,
                  }
                  : row
              )));
            }
          } else if (event.phase === "final") {
            finalPayload = event;
            const secondText = finalSecondUnitText(event);
            if (sawSecondDelta && secondRowId) {
              setRows((current) => {
                if (!secondText) {
                  return current.filter((row) => row.id !== secondRowId);
                }
                return current.map((row) => (
                  row.id === secondRowId
                    ? {
                      ...row,
                      progressive_text: secondText,
                      phase: "final",
                      response_plan: event.response_plan || null,
                      delay_ms: event.delay_ms,
                      visual_mode: event.visual_mode || row.visual_mode,
                      vocal_marker: event.vocal_marker || row.vocal_marker,
                      body_action: event.body_action || row.body_action,
                    }
                    : row
                ));
              });
            } else {
              setRows((current) => [...current, {
                id: `entity-final-${Date.now()}`,
                role: "entity",
                progressive_text: event.text || "",
                phase: "final",
                response_plan: event.response_plan || null,
                delay_ms: event.delay_ms,
                visual_mode: event.visual_mode,
                vocal_marker: event.vocal_marker,
                body_action: event.body_action,
                turn_at: new Date().toISOString(),
              }]);
            }
          } else if (event.phase === "error") {
            throw new Error(event.error || "Progressive dialog failed");
          }
        });
        const responseAt = nowMs();
        postPresentationLatency("dashboard.text_dialog.response", submitStartedAt, {
          latencyRecordId: finalPayload && finalPayload.latency_record_id,
          metadata: { input_chars: trimmed.length },
        });
        window.requestAnimationFrame(() => {
          const renderedText = finalPayload
            ? (finalSecondUnitText(finalPayload) || finalPayload.text || "")
            : "";
          postPresentationLatency("dashboard.text_dialog.render", responseAt, {
            latencyRecordId: finalPayload && finalPayload.latency_record_id,
            metadata: { text_chars: String(renderedText || "").length },
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
      if (row.progressive_text !== null && row.progressive_text !== undefined) {
        out.push({ role: "entity", text: row.progressive_text || "...", ts: row.turn_at, meta: [row.phase, row.policy_action, vocalMarkerLabel(row.vocal_marker), bodyActionLabel(row.body_action), row.visual_mode].filter(Boolean).join(" · "), key: `${row.id}-progressive` });
      } else if (row.expression_output !== null && row.expression_output !== undefined) {
        out.push({ role: "entity", text: responsePlanText(row) || "...", ts: row.turn_at, meta: [row.policy_action, vocalMarkerLabel(row.vocal_marker), bodyActionLabel(row.body_action), row.visual_mode].filter(Boolean).join(" · "), key: `${row.id}-entity` });
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

  function MemorySummary({ onSave, onReset }) {
    const [summary, setSummary] = useState(null);
    const [previewQuery, setPreviewQuery] = useState("");
    const [preview, setPreview] = useState(null);
    const [firstGate, setFirstGate] = useState(null);
    const [firstGateSaving, setFirstGateSaving] = useState(false);

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

    const loadFirstGate = useCallback(async () => {
      try {
        setFirstGate(await fetchJSON("/api/v1/runtime/first-unit-gate"));
      } catch {
        setFirstGate(null);
      }
    }, []);

    useEffect(() => {
      load();
      loadFirstGate();
      const refresh = () => load();
      window.addEventListener("entity:turn-complete", refresh);
      window.addEventListener("entity:session-reset", refresh);
      return () => {
        window.removeEventListener("entity:turn-complete", refresh);
        window.removeEventListener("entity:session-reset", refresh);
      };
    }, [load, loadFirstGate]);
    useInterval(load, 10000);
    useInterval(loadFirstGate, 10000);

    const runPreview = useCallback(async () => {
      const query = previewQuery.trim();
      if (!query) return;
      try {
        setPreview(await fetchJSON(`/api/v1/memory/preview?query=${encodeURIComponent(query)}`));
      } catch (error) {
        setPreview({ error: error.message, results: [] });
      }
    }, [previewQuery]);

    const toggleFirstGate = useCallback(async () => {
      const nextEnabled = !(firstGate && firstGate.enabled);
      setFirstGateSaving(true);
      try {
        setFirstGate(await fetchJSON("/api/v1/runtime/first-unit-gate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: nextEnabled }),
        }));
      } catch (error) {
        alert(`First-unit gate update failed: ${error.message}`);
      } finally {
        setFirstGateSaving(false);
      }
    }, [firstGate]);

    return h(React.Fragment, null,
      h("div", { className: "toolbar memory-actions" },
        h("button", { className: "btn-sm", onClick: onSave }, "Save Dialog"),
        h("button", { className: "btn-sm", onClick: onReset }, "Reset Memory / New Session"),
        h("button", {
          className: `btn-sm ${firstGate && firstGate.enabled ? "active" : ""}`,
          onClick: toggleFirstGate,
          disabled: firstGateSaving || firstGate === null,
        }, firstGateSaving ? "Saving…" : `Short First Silent: ${firstGate && firstGate.enabled ? "ON" : "OFF"}`),
      ),
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
    const tabs = [
      ["runtime", "Runtime"],
      ["memory", "Memory Curation"],
      ["hardware", "Hardware"],
      ["history", "Session & History"],
    ];
    return h(React.Fragment, null,
      h("div", { className: "tabs" },
        tabs.map(([name, label]) => h("button", {
          key: name,
          className: `tab ${tab === name ? "active" : ""}`,
          onClick: () => setTab(name),
        }, label)),
      ),
      h("div", { className: "tab-content" },
        tab === "runtime" ? h(RuntimePane)
          : tab === "memory" ? h(MemoryCurationPane)
            : tab === "hardware" ? h(HardwareMotionPane)
              : h(SessionHistoryPane),
      ),
    );
  }

  function yn(value) {
    if (value === null || value === undefined) return "—";
    return value ? "yes" : "no";
  }

  function ageText(ms) {
    if (ms === null || ms === undefined) return "never";
    if (ms < 1000) return `${Math.round(ms)} ms`;
    return `${(ms / 1000).toFixed(1)} s`;
  }

  function motionDisplay(value) {
    return MOTION_LABELS[value] || value || "Unknown";
  }

  function statusTone(value) {
    return value ? "ok" : "err";
  }

  function isEditableTarget(target) {
    if (!target) return false;
    const tag = String(target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || Boolean(target.isContentEditable);
  }

  function isTeleopKey(code) {
    return [
      "KeyW", "KeyA", "KeyS", "KeyD",
      "ArrowUp", "ArrowLeft", "ArrowDown", "ArrowRight",
      "ShiftLeft", "ShiftRight", "ControlLeft", "ControlRight",
    ].includes(code);
  }

  function computeTeleopIntent(keys) {
    const slow = keys.has("ControlLeft") || keys.has("ControlRight");
    const fast = keys.has("ShiftLeft") || keys.has("ShiftRight");
    const speed = slow ? 60 : fast ? 180 : 80;
    let throttle = 0;
    let turn = 0;
    if (keys.has("KeyW") || keys.has("ArrowUp")) throttle += speed;
    if (keys.has("KeyS") || keys.has("ArrowDown")) throttle -= speed;
    if (keys.has("KeyA") || keys.has("ArrowLeft")) turn -= speed;
    if (keys.has("KeyD") || keys.has("ArrowRight")) turn += speed;
    return { type: "intent", throttle, turn, duration_ms: 180 };
  }

  function HardwareMotionPane() {
    const [body, setBody] = useState(null);
    const [bridge, setBridge] = useState(null);
    const [ports, setPorts] = useState([]);
    const [port, setPort] = useState("");
    const [baud, setBaud] = useState("115200");
    const [error, setError] = useState("");
    const [bridgeError, setBridgeError] = useState("");
    const [commandBusy, setCommandBusy] = useState("");
    const [teleopActive, setTeleopActive] = useState(false);
    const [teleopStatus, setTeleopStatus] = useState("idle");
    const keysRef = useRef(new Set());
    const teleopSocketRef = useRef(null);
    const teleopTimerRef = useRef(null);
    const sendTeleopRef = useRef(() => {});

    const load = useCallback(async () => {
      try {
        const [bodyData, bridgeData, portsData] = await Promise.all([
          fetchJSON("/api/v1/body/status"),
          fetchJSON("/api/v1/body/bridge/status").catch(() => null),
          fetchJSON("/api/v1/body/ports").catch(() => null),
        ]);
        setBody(bodyData);
        setBridge(bridgeData || (portsData && portsData.bridge) || null);
        const nextPorts = portsData && Array.isArray(portsData.ports) ? portsData.ports : [];
        setPorts(nextPorts);
        setPort((current) => current || (bridgeData && bridgeData.port) || (nextPorts[0] && nextPorts[0].device) || "");
        setError("");
      } catch (err) {
        setError(err.message);
      }
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 1000);

    const controller = body && body.controller ? body.controller : {};
    const motion = body && body.motion ? body.motion : {};
    const obstacle = body && body.obstacle ? body.obstacle : {};
    const tof = body && body.tof ? body.tof : {};
    const sensors = Array.isArray(tof.sensors) ? tof.sensors : [];
    const motors = body && Array.isArray(body.motors) ? body.motors : [];
    const motorDuties = motion.motor_duties || {};
    const bridgeConnected = Boolean(bridge && bridge.connected);
    const bridgeEnabled = !bridge || bridge.enabled !== false;

    const connectBridge = async () => {
      const selectedPort = String(port || "").trim();
      if (!selectedPort) {
        setBridgeError("Select or enter a serial port first.");
        return;
      }
      setCommandBusy("connect");
      try {
        const data = await fetchJSON("/api/v1/body/bridge/connect", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ port: selectedPort, baud: Number(baud) || 115200 }),
        });
        setBridge(data);
        setBridgeError("");
      } catch (err) {
        setBridgeError(err.message);
      } finally {
        setCommandBusy("");
      }
    };

    const disconnectBridge = async () => {
      setTeleopActive(false);
      setCommandBusy("disconnect");
      try {
        const data = await fetchJSON("/api/v1/body/bridge/disconnect", { method: "POST" });
        setBridge(data);
        setBridgeError("");
      } catch (err) {
        setBridgeError(err.message);
      } finally {
        setCommandBusy("");
      }
    };

    const sendCommand = async (command) => {
      setCommandBusy(command);
      try {
        const data = await fetchJSON("/api/v1/body/command", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ command }),
        });
        setBridge(data);
        setBridgeError("");
        await load();
      } catch (err) {
        setBridgeError(err.message);
      } finally {
        setCommandBusy("");
      }
    };

    const sendTeleopFrame = useCallback((overridePayload = null) => {
      const socket = teleopSocketRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      const payload = overridePayload || computeTeleopIntent(keysRef.current);
      socket.send(JSON.stringify(payload));
      if (payload.type === "kill") {
        setTeleopStatus("kill stop sent");
      } else {
        setTeleopStatus(`tx throttle ${payload.throttle} turn ${payload.turn}`);
      }
    }, []);
    sendTeleopRef.current = sendTeleopFrame;

    useEffect(() => {
      if (!teleopActive) {
        if (teleopTimerRef.current) {
          window.clearInterval(teleopTimerRef.current);
          teleopTimerRef.current = null;
        }
        if (teleopSocketRef.current) {
          teleopSocketRef.current.close();
          teleopSocketRef.current = null;
        }
        keysRef.current.clear();
        return undefined;
      }
      if (!bridgeConnected) {
        setTeleopStatus("connect serial bridge first");
        setTeleopActive(false);
        return undefined;
      }
      const socket = new WebSocket(`${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/api/v1/body/teleop`);
      teleopSocketRef.current = socket;
      setTeleopStatus("connecting");
      socket.onopen = () => {
        setTeleopStatus("ready");
        sendTeleopRef.current();
        teleopTimerRef.current = window.setInterval(() => sendTeleopRef.current(), 80);
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "error") {
            setTeleopStatus(`error: ${payload.error || "unknown"}`);
          } else if (payload.command) {
            setTeleopStatus(`ack ${payload.command}`);
          } else {
            setTeleopStatus(payload.type || "event");
          }
        } catch (_) {
          setTeleopStatus("event");
        }
      };
      socket.onerror = () => setTeleopStatus("websocket error");
      socket.onclose = () => {
        if (teleopTimerRef.current) {
          window.clearInterval(teleopTimerRef.current);
          teleopTimerRef.current = null;
        }
        teleopSocketRef.current = null;
        keysRef.current.clear();
        setTeleopStatus("closed");
      };
      return () => {
        if (teleopTimerRef.current) {
          window.clearInterval(teleopTimerRef.current);
          teleopTimerRef.current = null;
        }
        if (teleopSocketRef.current) {
          teleopSocketRef.current.close();
          teleopSocketRef.current = null;
        }
        keysRef.current.clear();
      };
    }, [bridgeConnected, teleopActive]);

    useEffect(() => {
      if (!teleopActive) return undefined;
      const keydown = (event) => {
        if (isEditableTarget(event.target)) return;
        if (event.code === "Escape") {
          event.preventDefault();
          setTeleopActive(false);
          return;
        }
        if (event.code === "Space") {
          event.preventDefault();
          keysRef.current.clear();
          sendTeleopRef.current({ type: "kill" });
          return;
        }
        if (!isTeleopKey(event.code)) return;
        event.preventDefault();
        keysRef.current.add(event.code);
        sendTeleopRef.current();
      };
      const keyup = (event) => {
        if (isEditableTarget(event.target)) return;
        if (!isTeleopKey(event.code)) return;
        event.preventDefault();
        keysRef.current.delete(event.code);
        sendTeleopRef.current();
      };
      window.addEventListener("keydown", keydown);
      window.addEventListener("keyup", keyup);
      return () => {
        window.removeEventListener("keydown", keydown);
        window.removeEventListener("keyup", keyup);
      };
    }, [teleopActive]);

    if (error) {
      return h("div", { className: "section" },
        h("div", { className: "section-title" }, "Hardware / Motion"),
        h("div", { className: "err" }, error),
      );
    }
    if (!body) {
      return h("div", { className: "dim" }, "Loading hardware status...");
    }

    return h(React.Fragment, null,
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Hardware / Motion"),
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Telemetry"), h("td", { className: body.connected ? "ok" : "err" }, body.connected ? "fresh" : "offline / stale")),
          h("tr", null, h("td", null, "Last packet"), h("td", null, `${body.last_packet_type || "none"} · ${ageText(body.last_packet_age_ms)}`)),
          h("tr", null, h("td", null, "TCA9548A 0x70"), h("td", { className: statusTone(controller.tca_0x70) }, yn(controller.tca_0x70))),
          h("tr", null, h("td", null, "I2C pins"), h("td", null, `SDA ${controller.sda ?? "—"} · SCL ${controller.scl ?? "—"}`)),
          h("tr", null, h("td", null, "Armed"), h("td", null, yn(controller.motor_armed))),
          h("tr", null, h("td", null, "Avoidance"), h("td", null, yn(controller.avoidance_enabled))),
          h("tr", null, h("td", null, "Roam"), h("td", null, `${yn(controller.roam_enabled)} · ${controller.roam_mode || "stopped"}`)),
        )),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Serial Bridge"),
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Dependency"), h("td", { className: bridgeEnabled ? "ok" : "err" }, bridgeEnabled ? "pyserial ready" : "serial dependency missing")),
          h("tr", null, h("td", null, "Connection"), h("td", { className: bridgeConnected ? "ok" : "err" }, bridgeConnected ? "connected" : "disconnected")),
          h("tr", null, h("td", null, "Port"), h("td", null, bridge && bridge.port ? bridge.port : "—")),
          h("tr", null, h("td", null, "RX / TX"), h("td", null, `${bridge && bridge.rx_count ? bridge.rx_count : 0} / ${bridge && bridge.tx_count ? bridge.tx_count : 0}`)),
          h("tr", null, h("td", null, "Event"), h("td", null, bridge && bridge.last_event ? bridge.last_event : "—")),
          h("tr", null, h("td", null, "Last line"), h("td", null, bridge && bridge.last_line ? String(bridge.last_line).slice(0, 120) : "—")),
        )),
        h("div", { className: "bridge-controls" },
          h("select", {
            className: "compact-select",
            value: port,
            disabled: bridgeConnected,
            onChange: (event) => setPort(event.target.value),
            onFocus: () => setTeleopActive(false),
          },
            port ? h("option", { value: port }, port) : h("option", { value: "" }, "Select port"),
            ports.filter((item) => item.device !== port).map((item) => h("option", { key: item.device, value: item.device }, `${item.device}${item.description ? ` · ${item.description}` : ""}`)),
          ),
          h("input", {
            className: "compact-input",
            value: port,
            disabled: bridgeConnected,
            onChange: (event) => setPort(event.target.value),
            onFocus: () => setTeleopActive(false),
            placeholder: "/dev/cu.usbmodem...",
          }),
          h("input", {
            className: "compact-input baud-input",
            value: baud,
            disabled: bridgeConnected,
            onChange: (event) => setBaud(event.target.value),
            onFocus: () => setTeleopActive(false),
            placeholder: "115200",
          }),
          h("button", { className: "btn-sm", disabled: commandBusy || bridgeConnected || !bridgeEnabled, onClick: connectBridge }, commandBusy === "connect" ? "Connecting…" : "Connect"),
          h("button", { className: "btn-sm", disabled: commandBusy || !bridgeConnected, onClick: disconnectBridge }, commandBusy === "disconnect" ? "Disconnecting…" : "Disconnect"),
        ),
        bridgeError ? h("div", { className: "err" }, bridgeError) : bridge && bridge.last_error ? h("div", { className: "err" }, bridge.last_error) : null,
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Controls"),
        h("div", { className: "toolbar" },
          ["arm", "motors off", "avoidance on", "avoidance off", "telemetry on", "telemetry off", "tof", "status"].map((command) => h("button", {
            key: command,
            className: command === "motors off" ? "btn-sm danger" : "btn-sm",
            disabled: commandBusy || !bridgeConnected,
            onClick: () => sendCommand(command),
          }, commandBusy === command ? "Sending…" : command)),
        ),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Keyboard Teleop"),
        h("button", {
          className: `teleop-capture ${teleopActive ? "active" : ""}`,
          disabled: !bridgeConnected,
          onClick: () => setTeleopActive((value) => !value),
        },
          h("span", { className: "teleop-title" }, teleopActive ? "Teleop Active" : "Click to Capture Keyboard"),
          h("span", { className: "teleop-help" }, "WASD / arrows move · Shift fast 180 · Ctrl slow 60 · Space kill stop · Esc release"),
          h("span", { className: "teleop-status" }, teleopStatus),
        ),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Current Motion"),
        h("div", { className: `motion-readout motion-${motion.label || "unknown"}` },
          h("div", { className: "motion-label" }, motionDisplay(motion.label)),
          h("div", { className: "motion-detail" }, motion.detail || "—"),
        ),
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Left / Right"), h("td", null, `${motion.left_duty ?? 0} / ${motion.right_duty ?? 0}`)),
          h("tr", null, h("td", null, "Motor duties"), h("td", null, `M1 ${motorDuties.m1 ?? 0} · M2 ${motorDuties.m2 ?? 0} · M3 ${motorDuties.m3 ?? 0} · M4 ${motorDuties.m4 ?? 0}`)),
          h("tr", null, h("td", null, "Clipped"), h("td", null, yn(motion.clipped))),
        )),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Obstacle Gate"),
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "State"), h("td", null, obstacle.state || "unknown")),
          h("tr", null, h("td", null, "Reason"), h("td", null, obstacle.reason || "—")),
          h("tr", null, h("td", null, "Front L / R"), h("td", null, `${obstacle.front_left_mm ?? "—"} / ${obstacle.front_right_mm ?? "—"} mm`)),
          h("tr", null, h("td", null, "Suggested turn"), h("td", null, obstacle.suggested_turn ?? "—")),
        )),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "ToF Array"),
        h("div", { className: "item-meta" },
          `${tof.present_count ?? 0}/${tof.expected_count ?? 4} present · ${tof.initialized_count ?? 0} initialized · ${tof.valid_count ?? 0} valid`,
        ),
        h("div", { className: "tof-grid" }, sensors.map((sensor) => h(TofSensorCard, {
          key: sensor.channel,
          sensor,
        }))),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Motor Channels"),
        h("table", null,
          h("thead", null, h("tr", null, h("th", null, "Motor"), h("th", null, "Duty"), h("th", null, "PWM"), h("th", null, "DIR"))),
          h("tbody", null, motors.map((motor) => h("tr", { key: motor.motor },
            h("td", null, `${motor.name || `M${motor.motor}`} · ${motor.position || "—"}`),
            h("td", null, motor.duty ?? 0),
            h("td", null, motor.pwm_pin ?? "—"),
            h("td", null, motor.dir_pin ?? "—"),
          ))),
        ),
      ),
      h("div", { className: "section" },
        h("div", { className: "section-title" }, "Last Hardware Event"),
        body.last_ack ? h("div", { className: "item-text" }, `ack: ${body.last_ack.action || body.last_ack.type || "—"}`) : h("div", { className: "dim" }, "No ack yet."),
        body.last_error ? h("div", { className: "err" }, `error: ${body.last_error.error || "unknown"}`) : null,
      ),
    );
  }

  function TofSensorCard({ sensor }) {
    const valid = Boolean(sensor.present && sensor.initialized && sensor.range_valid && !sensor.timeout);
    return h("div", { className: `tof-card ${valid ? "ok" : sensor.present ? "warn" : "offline"}` },
      h("div", { className: "tof-card-head" },
        h("span", null, `${sensor.channel}: ${sensor.name || "tof"}`),
        h("span", null, valid ? "valid" : sensor.present ? "check" : "offline"),
      ),
      h("div", { className: "tof-distance" }, sensor.distance_mm === null || sensor.distance_mm === undefined ? "—" : `${sensor.distance_mm} mm`),
      h("div", { className: "kv-grid" },
        h("span", null, "Present"), h("span", null, yn(sensor.present)),
        h("span", null, "Initialized"), h("span", null, yn(sensor.initialized)),
        h("span", null, "Fresh"), h("span", null, yn(sensor.fresh)),
        h("span", null, "Range valid"), h("span", null, yn(sensor.range_valid)),
        h("span", null, "Timeout"), h("span", null, yn(sensor.timeout)),
        h("span", null, "Age"), h("span", null, ageText(sensor.age_ms)),
        h("span", null, "Status"), h("span", null, sensor.status || "—"),
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
    const [faceIdentity, setFaceIdentity] = useState(null);

    const load = useCallback(async () => {
      const [llmConfig, embeddingConfig, llmStats, latencyStats, audioLatencyStats, presentationLatencyStats, harnessStatus, visitorStatus, identityStatus, faceIdentityStatus] = await Promise.all([
        fetchJSON("/api/v1/config/llm").catch(() => null),
        fetchJSON("/api/v1/config/embedding").catch(() => null),
        fetchJSON("/api/v1/stats/llm").catch(() => null),
        fetchJSON("/api/v1/stats/latency?n=1").catch(() => null),
        fetchJSON("/api/v1/stats/audio-latency?n=8").catch(() => null),
        fetchJSON("/api/v1/stats/presentation-latency?n=8").catch(() => null),
        fetchJSON("/api/v1/harness/status").catch(() => null),
        fetchJSON("/api/v1/visitors/current").catch(() => null),
        fetchJSON("/api/v1/identity/status").catch(() => null),
        fetchJSON("/api/v1/identity/face/status").catch(() => null),
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
      setFaceIdentity(faceIdentityStatus);
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 10000);

    return h(React.Fragment, null,
      h(VisitorIdentitySection, { visitorData: visitor, identityData: identity, faceIdentityData: faceIdentity, onSaved: load }),
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

  function VisitorIdentitySection({ visitorData, identityData, faceIdentityData, onSaved }) {
    const [known, setKnown] = useState([]);
    const [visitorId, setVisitorId] = useState("");
    const [displayName, setDisplayName] = useState("");
    const [saving, setSaving] = useState(false);
    const [configSaving, setConfigSaving] = useState(false);
    const [configError, setConfigError] = useState("");
    const [identitySaving, setIdentitySaving] = useState(false);
    const [faceSaving, setFaceSaving] = useState(false);
    const [faceError, setFaceError] = useState("");
    const current = visitorData && visitorData.visitor ? visitorData.visitor : null;
    const status = identityData && identityData.status ? identityData.status : null;
    const constraints = identityData && identityData.v1_constraints ? identityData.v1_constraints : {};
    const config = identityData && identityData.config ? identityData.config : {};
    const events = identityData && Array.isArray(identityData.recent_events) ? identityData.recent_events : [];
    const autoBind = Boolean(config.auto_bind_high_confidence);
    const faceModel = faceIdentityData && faceIdentityData.model ? faceIdentityData.model : {};
    const faceStore = faceIdentityData && faceIdentityData.store ? faceIdentityData.store : {};
    const faceCapture = faceIdentityData && faceIdentityData.last_capture ? faceIdentityData.last_capture : null;
    const facePending = faceIdentityData && faceIdentityData.pending_capture ? faceIdentityData.pending_capture : null;
    const faceMatch = faceCapture && Array.isArray(faceCapture.matches) && faceCapture.matches.length ? faceCapture.matches[0] : null;
    const faceAuto = faceIdentityData && faceIdentityData.auto_capture ? faceIdentityData.auto_capture : {};
    const currentFaceSignatures = current && current.metadata && current.metadata.identity && current.metadata.identity.signatures && Array.isArray(current.metadata.identity.signatures.face)
      ? current.metadata.identity.signatures.face
      : [];

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

    const toggleAutoBind = useCallback(async () => {
      setConfigSaving(true);
      setConfigError("");
      try {
        await fetchJSON("/api/v1/identity/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ auto_bind_high_confidence: !autoBind }),
        });
        await onSaved();
      } catch (error) {
        setConfigError(error.message);
      } finally {
        setConfigSaving(false);
      }
    }, [autoBind, onSaved]);

    const captureFace = useCallback(async () => {
      setFaceSaving(true);
      setFaceError("");
      try {
        await fetchJSON("/api/v1/identity/face/capture", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ apply_to_gating: true }),
        });
        await onSaved();
      } catch (error) {
        setFaceError(error.message);
      } finally {
        setFaceSaving(false);
      }
    }, [onSaved]);

    const enrollFace = useCallback(async () => {
      if (!current) return;
      setFaceSaving(true);
      setFaceError("");
      try {
        await fetchJSON("/api/v1/identity/face/enroll", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ visitor_id: current.id }),
        });
        await onSaved();
        await loadKnown();
      } catch (error) {
        setFaceError(error.message);
      } finally {
        setFaceSaving(false);
      }
    }, [current, onSaved, loadKnown]);

    const confirmCandidate = useCallback(async (accepted) => {
      setIdentitySaving(true);
      setConfigError("");
      try {
        await fetchJSON("/api/v1/identity/confirm", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ accepted }),
        });
        await onSaved();
        await loadKnown();
        if (accepted) {
          window.dispatchEvent(new CustomEvent("entity:session-reset"));
        }
      } catch (error) {
        setConfigError(error.message);
      } finally {
        setIdentitySaving(false);
      }
    }, [onSaved, loadKnown]);

    const deactivateFaceSignature = useCallback(async (signatureId) => {
      if (!current || !signatureId) return;
      setFaceSaving(true);
      setFaceError("");
      try {
        await fetchJSON("/api/v1/identity/face/signature/deactivate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ visitor_id: current.id, signature_id: signatureId }),
        });
        await onSaved();
        await loadKnown();
      } catch (error) {
        setFaceError(error.message);
      } finally {
        setFaceSaving(false);
      }
    }, [current, onSaved, loadKnown]);

    return h("div", { className: "section" },
      h("div", { className: "section-title" }, "Visitor Identity & Gating"),
      h("table", null, h("tbody", null,
        h("tr", null, h("td", null, "Current visitor"), h("td", null, current ? `${current.display_name || current.id} · ${current.id}` : "none")),
        h("tr", null, h("td", null, "Scope"), h("td", null, current ? "same visitor sessions included in retrieval" : "current session only")),
        status ? h("tr", null, h("td", null, "Primary visitor"), h("td", null, status.primary_visitor_id || "unknown")) : null,
        status ? h("tr", null, h("td", null, "Candidate"), h("td", null, status.candidate_visitor_id || "none")) : null,
        status ? h("tr", null, h("td", null, "Visitor memory"), h("td", null, status.visitor_memory_allowed ? "allowed" : "blocked until confirmed")) : null,
        status ? h("tr", null, h("td", null, "Runtime"), h("td", null, status.runtime_state || "—")) : null,
        status ? h("tr", null, h("td", null, "Session decision"), h("td", null, status.last_decision || "—")) : null,
        status ? h("tr", null, h("td", null, "Encounter / intent"), h("td", null, `${status.encounter_status || "—"} · ${status.intent_status || "—"}`)) : null,
        status ? h("tr", null, h("td", null, "Identity"), h("td", null, `${status.identity_status || "—"} · face ${status.face_confidence_level || "none"} · voice ${status.voice_confidence_level || "none"} · combined ${status.combined_confidence_level || "none"}`)) : null,
        status ? h("tr", null, h("td", null, "Waiting confirm"), h("td", null, status.waiting_for_identity_confirmation ? "yes" : "no")) : null,
        status ? h("tr", null, h("td", null, "Last rejection"), h("td", null, status.last_capture_rejection ? `${status.last_capture_rejection.reason || "rejected"} · ${status.last_capture_rejection.source || "capture"}` : "none")) : null,
        status ? h("tr", null, h("td", null, "Natural confirm"), h("td", null, status.last_natural_confirmation ? `${status.last_natural_confirmation.status || "—"} · ${status.last_natural_confirmation.candidate_visitor_id || "none"}` : "none")) : null,
        status ? h("tr", null, h("td", null, "Interruptions"), h("td", null, status.interruption_count || 0)) : null,
        h("tr", null, h("td", null, "Auto-bind"), h("td", null, autoBind ? "high confidence on" : "high confidence off")),
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
        h("button", {
          className: autoBind ? "btn-sm active" : "btn-sm",
          disabled: configSaving || !identityData || identityData.enabled === false,
          onClick: toggleAutoBind,
          title: "Only auto-binds high-confidence candidates when no primary visitor exists and dialogue is not active.",
        }, configSaving ? "Saving…" : `Auto-bind ${autoBind ? "On" : "Off"}`),
        h("button", {
          className: "btn-sm",
          disabled: identitySaving || !status || !status.candidate_visitor_id,
          onClick: () => confirmCandidate(true),
        }, identitySaving ? "Working…" : "Confirm Candidate"),
        h("button", {
          className: "btn-sm",
          disabled: identitySaving || !status || !status.candidate_visitor_id,
          onClick: () => confirmCandidate(false),
        }, "Reject Candidate"),
      ),
      configError ? h("div", { className: "err" }, configError) : null,
      h("div", { className: "item" },
        h("div", { className: "item-meta" }, "Face Signature"),
        h("table", null, h("tbody", null,
          h("tr", null, h("td", null, "Provider"), h("td", null, `${faceModel.provider || "insightface_arcface"} · ${faceModel.model_name || "buffalo_l"}`)),
          h("tr", null, h("td", null, "Model"), h("td", null, faceModel.loaded ? "loaded" : (faceModel.disabled_reason || "not loaded"))),
          h("tr", null, h("td", null, "Signature store"), h("td", null, `${faceStore.signature_count || 0} face signature(s)`)),
          h("tr", null, h("td", null, "Auto capture"), h("td", null, faceAuto.in_flight ? "running" : `idle · cooldown ${faceAuto.cooldown_remaining_seconds || 0}s`)),
          h("tr", null, h("td", null, "Pending capture"), h("td", null, facePending ? `${facePending.capture_id} · ${facePending.quality_summary ? JSON.stringify(facePending.quality_summary) : "quality ok"}` : "none")),
          h("tr", null, h("td", null, "Last capture"), h("td", null, faceCapture ? `${faceCapture.accepted ? "accepted" : "rejected"} · ${faceCapture.reason}` : "none")),
          h("tr", null, h("td", null, "Last match"), h("td", null, faceMatch ? `${faceMatch.visitor_id} · ${faceMatch.level} · ${faceMatch.score}` : "none")),
        )),
        h("div", { className: "toolbar", style: { marginTop: "8px" } },
          h("button", { className: "btn-sm", disabled: faceSaving || !faceIdentityData, onClick: captureFace }, faceSaving ? "Working…" : "Capture Face"),
          h("button", { className: "btn-sm", disabled: faceSaving || !current || !facePending, onClick: enrollFace }, "Enroll Current"),
        ),
        currentFaceSignatures.length ? h("div", { className: "card-list compact-list" },
          currentFaceSignatures.slice(0, 4).map((item) => h("button", {
            key: item.signature_id || item.reference,
            className: `session-item ${item.status === "inactive" ? "" : "active"}`,
            disabled: faceSaving || item.status === "inactive",
            onClick: () => deactivateFaceSignature(item.signature_id),
            title: "Deactivate this face signature. It will not delete the private .npz file.",
          },
            h("div", { className: "session-title" }, h("span", null, item.signature_id || "face signature"), h("span", null, item.status || "active")),
            h("div", { className: "session-meta" }, item.reference || "local reference redacted"),
          )),
        ) : null,
        faceError ? h("div", { className: "err" }, faceError) : null,
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
      status ? h(React.Fragment, null,
        h("div", { className: "item" },
          h("div", { className: "item-meta" }, "V1 constraints"),
          h("div", { className: "item-text" },
            `single visitor ${constraints.single_primary_visitor_per_session ? "on" : "off"} · auto-bind high confidence ${autoBind ? "on" : "off"} · group session ${constraints.group_session_enabled ? "on" : "off"} · wide-angle identity ${constraints.wide_angle_identity_input_enabled ? "on" : "off"}`,
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
    const [playbackQueueDepth, setPlaybackQueueDepth] = useState(0);
    const [playbackCurrentStream, setPlaybackCurrentStream] = useState("");
    const [playbackPrefetchDetail, setPlaybackPrefetchDetail] = useState("none");
    const [lastPlaybackEvent, setLastPlaybackEvent] = useState("none");
    const [bargeInDetail, setBargeInDetail] = useState("idle");
    const [sttStreamState, setSttStreamState] = useState("stopped");
    const [sttCloseDetail, setSttCloseDetail] = useState("none");
    const [lastSttEvent, setLastSttEvent] = useState("none");
    const [reconnectDetail, setReconnectDetail] = useState("none");
    const [latestTtsStreamId, setLatestTtsStreamId] = useState("");
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
    const playbackQueueRef = useRef([]);
    const playbackPlayingRef = useRef(false);
    const playbackTimingRef = useRef(null);
    const playbackWatchdogRef = useRef(null);
    const playbackPrefetchRef = useRef(null);
    const playNextQueuedStreamRef = useRef(null);
    const playbackStartedAtRef = useRef(0);
    const bargeInFramesRef = useRef(0);
    const activeAudioTurnRef = useRef(0);
    const suppressedPlaybackTurnRef = useRef(0);
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

    const updatePlaybackQueueDepth = useCallback(() => {
      setPlaybackQueueDepth(playbackQueueRef.current.length);
    }, []);

    const clearPlaybackWatchdog = useCallback(() => {
      if (playbackWatchdogRef.current) {
        window.clearTimeout(playbackWatchdogRef.current);
        playbackWatchdogRef.current = null;
      }
    }, []);

    const clearPlaybackPrefetch = useCallback(() => {
      const entry = playbackPrefetchRef.current;
      if (entry) {
        if (entry.controller) entry.controller.abort();
        revokeObjectUrl(entry.objectUrl);
      }
      playbackPrefetchRef.current = null;
      setPlaybackPrefetchDetail("none");
    }, []);

    const prefetchQueuedHead = useCallback(() => {
      const next = playbackQueueRef.current[0];
      if (!next || !next.streamId) {
        if (playbackPrefetchRef.current) clearPlaybackPrefetch();
        return null;
      }
      const existing = playbackPrefetchRef.current;
      if (existing && existing.streamId === next.streamId) return existing;
      clearPlaybackPrefetch();
      const streamId = next.streamId;
      const startedAt = nowMs();
      const controller = new AbortController();
      const entry = {
        streamId,
        status: "pending",
        controller,
        objectUrl: "",
        startedAt,
        error: "",
        promise: null,
      };
      playbackPrefetchRef.current = entry;
      setPlaybackPrefetchDetail(`pending ${compactId(streamId)}`);
      entry.promise = fetch(ttsStreamUrl(streamId), { signal: controller.signal })
        .then((response) => {
          if (!response.ok) {
            throw new Error(response.statusText || String(response.status));
          }
          return response.blob();
        })
        .then((blob) => {
          if (playbackPrefetchRef.current !== entry) return null;
          entry.objectUrl = window.URL.createObjectURL(blob);
          entry.status = "ready";
          entry.controller = null;
          setPlaybackPrefetchDetail(`ready ${compactId(streamId)}`);
          postPresentationLatency("dashboard.audio.prefetch_ready", startedAt, {
            latencyRecordId: next.timing && next.timing.latencyRecordId,
            metadata: { stream_id: streamId, byte_size: blob.size },
          });
          return entry;
        })
        .catch((err) => {
          if (err && err.name === "AbortError") return null;
          if (playbackPrefetchRef.current === entry) {
            entry.status = "error";
            entry.controller = null;
            entry.error = err && err.message ? err.message : "prefetch_error";
            setPlaybackPrefetchDetail(`error ${compactId(streamId)}`);
          }
          postPresentationLatency("dashboard.audio.prefetch_error", startedAt, {
            latencyRecordId: next.timing && next.timing.latencyRecordId,
            success: false,
            error: err && err.name ? err.name : "prefetch_error",
            metadata: { stream_id: streamId },
          });
          return null;
        });
      return entry;
    }, [clearPlaybackPrefetch]);

    const consumePlaybackPrefetch = useCallback(async (streamId, timing = {}) => {
      const entry = playbackPrefetchRef.current;
      if (!entry || entry.streamId !== streamId) return null;
      if (entry.status === "pending" && entry.promise) {
        await Promise.race([
          entry.promise,
          new Promise((resolve) => window.setTimeout(resolve, TTS_PREFETCH_WAIT_MS)),
        ]);
      }
      const current = playbackPrefetchRef.current;
      if (!current || current.streamId !== streamId) return null;
      if (current.status === "ready" && current.objectUrl) {
        playbackPrefetchRef.current = null;
        setPlaybackPrefetchDetail(`hit ${compactId(streamId)}`);
        postPresentationLatency("dashboard.audio.prefetch_hit", current.startedAt, {
          latencyRecordId: timing.latencyRecordId,
          metadata: { stream_id: streamId },
        });
        return current;
      }
      if (current.status === "pending") {
        postPresentationLatency("dashboard.audio.prefetch_miss", current.startedAt, {
          latencyRecordId: timing.latencyRecordId,
          metadata: { stream_id: streamId, wait_ms: TTS_PREFETCH_WAIT_MS },
        });
        clearPlaybackPrefetch();
        setPlaybackPrefetchDetail(`miss ${compactId(streamId)}`);
      }
      return null;
    }, [clearPlaybackPrefetch]);

    useEffect(() => { loadStatus(); }, [loadStatus]);
    useEffect(() => () => {
      const entry = playbackPrefetchRef.current;
      if (entry) {
        if (entry.controller) entry.controller.abort();
        revokeObjectUrl(entry.objectUrl);
      }
      playbackPrefetchRef.current = null;
    }, []);
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
      setVoiceActivity(playbackStreamRef.current ? "speaking" : "idle");
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

    const stopPlayback = useCallback((detail = "interrupted", options = {}) => {
      const invalidateTurn = Boolean(options && (options.invalidateTurn || options.cancelDialog));
      const clearQueue = !(options && options.clearQueue === false);
      if (invalidateTurn) {
        activeAudioTurnRef.current += 1;
      }
      if (options.cancelDialog) {
        setDialogPending(false);
        dialogPendingRef.current = false;
      }
      if (options.suppressTurnPlayback) {
        suppressedPlaybackTurnRef.current = activeAudioTurnRef.current;
      }
      clearPlaybackWatchdog();
      clearPlaybackPrefetch();
      const player = playerRef.current;
      const currentTiming = playbackTimingRef.current;
      const hadPlayback = Boolean(playbackStreamRef.current || (player && player.getAttribute("src")));
      if (player) {
        player.pause();
        player.removeAttribute("src");
        player.load();
      }
      revokeObjectUrl(currentTiming && currentTiming.objectUrl);
      if (clearQueue) playbackQueueRef.current = [];
      playbackPlayingRef.current = false;
      playbackStreamRef.current = "";
      playbackTimingRef.current = null;
      playbackStartedAtRef.current = 0;
      if (clearQueue) setPlaybackQueueDepth(0);
      else updatePlaybackQueueDepth();
      setPlaybackCurrentStream("");
      setLastPlaybackEvent(String(detail || "interrupted"));
      bargeInFramesRef.current = 0;
      suppressMicRef.current = false;
      setPlaybackBlocked(false);
      setVoiceActivity(recordingRef.current ? "listening" : "idle");
      if (hadPlayback) {
        const detailText = String(detail || "interrupted");
        setPlaybackDetail(detailText);
        setBargeInDetail(detailText.startsWith("barge-in") ? "detected, playback stopped" : "idle");
      }
    }, [clearPlaybackPrefetch, clearPlaybackWatchdog, updatePlaybackQueueDepth]);

    const startPlaybackStream = useCallback(async (streamId, timing = {}) => {
      if (!streamId || !playerRef.current) return false;
      clearPlaybackWatchdog();
      suppressMicRef.current = true;
      playbackPlayingRef.current = true;
      bargeInFramesRef.current = 0;
      setVoiceActivity("speaking");
      setPlaybackBlocked(false);
      setBargeInDetail("armed while speaking");
      setPlaybackCurrentStream(streamId);
      setLastPlaybackEvent(`starting ${compactId(streamId)}`);
      const player = playerRef.current;
      playbackStreamRef.current = streamId;
      playbackStartedAtRef.current = nowMs();
      const streamReceivedAt = timing.streamReceivedAt || nowMs();
      const prefetchedEntry = await consumePlaybackPrefetch(streamId, timing);
      const prefetchedObjectUrl = prefetchedEntry && prefetchedEntry.objectUrl ? prefetchedEntry.objectUrl : "";
      const playbackSrc = prefetchedObjectUrl || ttsStreamUrl(streamId);
      const prefetched = Boolean(prefetchedObjectUrl);
      if (playbackStreamRef.current !== streamId || !playbackPlayingRef.current) {
        revokeObjectUrl(prefetchedObjectUrl);
        return false;
      }
      playbackTimingRef.current = {
        streamId,
        latencyRecordId: timing.latencyRecordId || null,
        streamReceivedAt,
        prefetched,
        objectUrl: prefetchedObjectUrl || null,
      };
      player.muted = false;
      player.volume = 1;
      player.src = playbackSrc;
      player.load();
      try {
        await player.play();
        postPresentationLatency("dashboard.audio.play_resolved", streamReceivedAt, {
          latencyRecordId: timing.latencyRecordId,
          metadata: { stream_id: streamId, prefetched },
        });
        playbackUnlockedRef.current = true;
        setPlaybackUnlocked(true);
        setPlaybackDetail(`playing ${compactId(streamId)}`);
        setLastPlaybackEvent(`playing ${compactId(streamId)}`);
        prefetchQueuedHead();
        const textChars = Number(timing.textChars || 0);
        const watchdogMs = clamp(6000 + textChars * 240, 8000, 30000);
        playbackWatchdogRef.current = window.setTimeout(() => {
          if (playbackStreamRef.current !== streamId) return;
          const currentTiming = playbackTimingRef.current;
          if (currentTiming) {
            postPresentationLatency("dashboard.audio.watchdog_recovered", currentTiming.streamReceivedAt, {
              latencyRecordId: currentTiming.latencyRecordId,
              metadata: {
                stream_id: currentTiming.streamId,
                watchdog_ms: watchdogMs,
                prefetched: Boolean(currentTiming.prefetched),
              },
            });
          }
          const activePlayer = playerRef.current;
          if (activePlayer) {
            activePlayer.pause();
            activePlayer.removeAttribute("src");
            activePlayer.load();
          }
          revokeObjectUrl(currentTiming && currentTiming.objectUrl);
          playbackWatchdogRef.current = null;
          playbackTimingRef.current = null;
          playbackStreamRef.current = "";
          playbackPlayingRef.current = false;
          suppressMicRef.current = false;
          setPlaybackCurrentStream("");
          setPlaybackDetail(`watchdog advanced ${compactId(streamId)}`);
          setLastPlaybackEvent(`watchdog advanced ${compactId(streamId)}`);
          if (playNextQueuedStreamRef.current) playNextQueuedStreamRef.current();
        }, watchdogMs);
        return true;
      } catch (err) {
        clearPlaybackWatchdog();
        player.pause();
        player.removeAttribute("src");
        player.load();
        playbackPlayingRef.current = false;
        playbackStreamRef.current = "";
        playbackStartedAtRef.current = 0;
        postPresentationLatency("dashboard.audio.play_resolved", streamReceivedAt, {
          latencyRecordId: timing.latencyRecordId,
          success: false,
          error: err && err.name ? err.name : "play_failed",
          metadata: { stream_id: streamId, prefetched },
        });
        revokeObjectUrl(prefetchedObjectUrl);
        playbackTimingRef.current = null;
        playbackStreamRef.current = "";
        setPlaybackCurrentStream("");
        setLastPlaybackEvent(`play failed ${compactId(streamId)}`);
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
        if (err && err.name === "NotAllowedError") {
          playbackUnlockedRef.current = false;
          setPlaybackUnlocked(false);
          playbackQueueRef.current = [];
          clearPlaybackPrefetch();
          updatePlaybackQueueDepth();
        } else if (playbackQueueRef.current.length && playNextQueuedStreamRef.current) {
          playNextQueuedStreamRef.current();
        }
        return false;
      }
    }, [
      clearPlaybackPrefetch,
      clearPlaybackWatchdog,
      consumePlaybackPrefetch,
      prefetchQueuedHead,
      updatePlaybackQueueDepth,
    ]);

    const playNextQueuedStream = useCallback(() => {
      const next = playbackQueueRef.current.shift();
      updatePlaybackQueueDepth();
      if (!next) {
        clearPlaybackWatchdog();
        clearPlaybackPrefetch();
        playbackPlayingRef.current = false;
        playbackStreamRef.current = "";
        playbackTimingRef.current = null;
        playbackStartedAtRef.current = 0;
        bargeInFramesRef.current = 0;
        suppressMicRef.current = false;
        setPlaybackCurrentStream("");
        setVoiceActivity(recordingRef.current ? "listening" : "idle");
        setPlaybackDetail("ended");
        setLastPlaybackEvent("queue empty");
        setBargeInDetail("idle");
        return false;
      }
      startPlaybackStream(next.streamId, next.timing);
      return true;
    }, [clearPlaybackPrefetch, clearPlaybackWatchdog, startPlaybackStream, updatePlaybackQueueDepth]);
    playNextQueuedStreamRef.current = playNextQueuedStream;

    const enqueueTtsStream = useCallback((streamId, timing = {}) => {
      if (!streamId) return false;
      playbackQueueRef.current.push({ streamId, timing });
      updatePlaybackQueueDepth();
      setLastPlaybackEvent(`queued ${compactId(streamId)}`);
      if (!playbackPlayingRef.current) {
        playNextQueuedStream();
      } else {
        prefetchQueuedHead();
      }
      return true;
    }, [playNextQueuedStream, prefetchQueuedHead, updatePlaybackQueueDepth]);

    const submitTranscript = useCallback(async (value) => {
      const transcript = String(value || "").trim();
      if (!transcript || dialogPendingRef.current) return;
      const finalStartedAt = nowMs();
      let playbackStarted = false;
      let finalPayload = null;
      const turnToken = activeAudioTurnRef.current + 1;
      activeAudioTurnRef.current = turnToken;
      suppressedPlaybackTurnRef.current = 0;
      try {
        setError("");
        setFinalText(transcript);
        setDialogPending(true);
        dialogPendingRef.current = true;
        suppressMicRef.current = true;
        setVoiceActivity("thinking");
        await fetchNDJSON("/api/v1/audio/dialog/progressive", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ transcript }),
        }, (event) => {
          if (!event || event.phase === "error") {
            throw new Error(event && event.error ? event.error : "Progressive audio dialog failed.");
          }
          if (turnToken !== activeAudioTurnRef.current) return;
          if (event.phase !== "first_unit" && event.phase !== "second_delta" && event.phase !== "final") return;
          const firstText = firstUnitRenderableText(event);
          const payload = Object.assign({}, event, {
            input_text: transcript,
            output_text: event.phase === "first_unit" ? firstText : event.text || "",
          });
          if (event.phase !== "first_unit" || firstText) {
            setLatestDialog(payload);
          }
          window.dispatchEvent(new CustomEvent("entity:turn-complete", {
            detail: {
              source: "audio_dialog_progressive",
              input_text: transcript,
              phase: event.phase,
              index: event.index,
              text: event.phase === "first_unit" ? firstText : event.text || "",
              output_text: payload.output_text || "",
              progressive_text: event.progressive_text || "",
              response_plan: event.response_plan || null,
              visual_mode: event.visual_mode || null,
              vocal_marker: event.vocal_marker || null,
              body_action: event.body_action || null,
            },
          }));
          if (event.phase === "final") {
            finalPayload = payload;
          }
          if (event.tts_stream_id) {
            setLatestTtsStreamId(event.tts_stream_id);
          }
          if (event.tts_stream_id && suppressedPlaybackTurnRef.current !== turnToken) {
            playbackStarted = enqueueTtsStream(event.tts_stream_id, {
              latencyRecordId: event.latency_record_id || null,
              streamReceivedAt: nowMs(),
              textChars: String(event.text || "").length,
            }) || playbackStarted;
          }
        });
        if (turnToken === activeAudioTurnRef.current && finalPayload) {
          setLatestDialog(finalPayload);
          postPresentationLatency("dashboard.audio_dialog.response", finalStartedAt, {
            latencyRecordId: finalPayload.latency_record_id,
            metadata: {
              audio_session_id: finalPayload.audio_session_id,
              transcript_chars: transcript.length,
            },
          });
        }
        loadStatus();
      } catch (err) {
        if (turnToken === activeAudioTurnRef.current) {
          setError(err.message);
        }
      } finally {
        if (turnToken === activeAudioTurnRef.current) {
          setDialogPending(false);
          dialogPendingRef.current = false;
          if (!playbackStarted || suppressedPlaybackTurnRef.current === turnToken) {
            suppressMicRef.current = false;
            setVoiceActivity(recordingRef.current ? "listening" : "idle");
          }
        }
      }
    }, [enqueueTtsStream, loadStatus]);

    const startMic = useCallback(async (options = {}) => {
      if (recording) return;
      const preservePlayback = Boolean(options && options.preservePlayback);
      try {
        setError("");
        setPartial("");
        setSttStreamState("connecting");
        setSttCloseDetail("none");
        setReconnectDetail("none");
        manualStopRef.current = false;
        if (!preservePlayback) {
          stopPlayback("mic start", { invalidateTurn: false });
          await unlockPlayback();
        } else if (!playbackStreamRef.current) {
          await unlockPlayback();
        }
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
          const playbackActive = Boolean(playbackStreamRef.current);
          socketRef.current = null;
          cleanupMicInput();
          setRecording(false);
          setVoiceActivity(shouldReconnect ? (playbackActive ? "speaking" : "reconnecting") : playbackActive ? "speaking" : "idle");
          setSttStreamState(shouldReconnect ? "reconnecting" : "stopped");
          setReconnectDetail(shouldReconnect ? "scheduled after stream close" : "none");
          if (shouldReconnect) {
            reconnectTimerRef.current = window.setTimeout(() => {
              reconnectTimerRef.current = null;
              if (!manualStopRef.current) startMic({ preservePlayback: true });
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
            const playbackAgeMs = Math.max(0, nowMs() - playbackStartedAtRef.current);
            if (playbackAgeMs >= BARGE_IN_GRACE_MS && pcmHasVoiceActivity(pcm)) {
              bargeInFramesRef.current += 1;
            } else {
              bargeInFramesRef.current = Math.max(0, bargeInFramesRef.current - 1);
            }
            if (bargeInFramesRef.current >= BARGE_IN_TRIGGER_FRAMES) {
              stopPlayback("barge-in: user speech detected", {
                cancelDialog: true,
                suppressTurnPlayback: true,
                invalidateTurn: true,
              });
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
        setVoiceActivity(playbackStreamRef.current ? "speaking" : "listening");
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
      const streamId = latestTtsStreamId || (latestDialog && latestDialog.tts_stream_id);
      if (!streamId) {
        setError("No fresh TTS stream is available for replay.");
        return;
      }
      enqueueTtsStream(streamId);
    }, [enqueueTtsStream, latestDialog, latestTtsStreamId]);

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
        h("button", {
          className: `btn-sm ${voiceActivity === "speaking" ? "active" : ""}`,
          onClick: () => stopPlayback("manual stop speaking", {
            cancelDialog: dialogPendingRef.current,
            suppressTurnPlayback: true,
            invalidateTurn: true,
          }),
          disabled: voiceActivity !== "speaking",
        }, "Stop Speaking"),
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
        h("span", null, "Playback stream"), h("span", { className: playbackCurrentStream ? "ok" : "dim" }, playbackCurrentStream ? compactId(playbackCurrentStream) : "none"),
        h("span", null, "Playback queue"), h("span", { className: playbackQueueDepth > 0 ? "ok" : "dim" }, String(playbackQueueDepth)),
        h("span", null, "Playback prefetch"), h("span", {
          className: playbackPrefetchDetail.startsWith("ready") || playbackPrefetchDetail.startsWith("hit")
            ? "ok"
            : playbackPrefetchDetail.startsWith("error") ? "err" : "dim",
        }, playbackPrefetchDetail),
        h("span", null, "Playback event"), h("span", { className: "dim" }, lastPlaybackEvent),
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
        h("div", { className: "item-meta" }, `tts: ${latestDialog.tts_stream_id || latestTtsStreamId || latestDialog.audio_disabled_reason || "silent"}`),
        h("div", { className: "item-text" }, latestDialog.output_text || latestDialog.text || "..."),
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
              metadata: {
                stream_id: timing.streamId,
                prefetched: Boolean(timing.prefetched),
              },
            });
          }
        },
        onEnded: () => {
          clearPlaybackWatchdog();
          const timing = playbackTimingRef.current;
          if (timing) {
            postPresentationLatency("dashboard.audio.ended", timing.streamReceivedAt, {
              latencyRecordId: timing.latencyRecordId,
              metadata: {
                stream_id: timing.streamId,
                prefetched: Boolean(timing.prefetched),
              },
            });
          }
          revokeObjectUrl(timing && timing.objectUrl);
          playbackTimingRef.current = null;
          setLastPlaybackEvent(`ended ${compactId(playbackStreamRef.current)}`);
          playbackStartedAtRef.current = 0;
          playNextQueuedStream();
        },
        onError: () => {
          clearPlaybackWatchdog();
          const timing = playbackTimingRef.current;
          if (timing) {
            postPresentationLatency("dashboard.audio.error", timing.streamReceivedAt, {
              latencyRecordId: timing.latencyRecordId,
              success: false,
              error: "media_error",
              metadata: {
                stream_id: timing.streamId,
                prefetched: Boolean(timing.prefetched),
              },
            });
          }
          revokeObjectUrl(timing && timing.objectUrl);
          const detail = describeMediaError(playerRef.current, "Playback stream error.");
          playbackStreamRef.current = "";
          setPlaybackCurrentStream("");
          playbackTimingRef.current = null;
          playbackStartedAtRef.current = 0;
          bargeInFramesRef.current = 0;
          suppressMicRef.current = false;
          setLastPlaybackEvent("media error");
          if (!playNextQueuedStream()) {
            playbackPlayingRef.current = false;
            setVoiceActivity(recordingRef.current ? "listening" : "idle");
            setPlaybackBlocked(true);
            setPlaybackDetail(detail);
            setBargeInDetail("idle");
          } else {
            setPlaybackBlocked(false);
            setPlaybackDetail(`skipped stream: ${detail}`);
          }
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
    return peak >= BARGE_IN_PEAK_THRESHOLD && rms >= BARGE_IN_RMS_THRESHOLD;
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
