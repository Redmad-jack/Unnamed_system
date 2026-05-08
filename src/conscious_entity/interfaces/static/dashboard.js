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
      h("span", { className: "session-label" }, health && health.session_id ? `session: ${compactId(health.session_id)} · ${sessionType}` : "session: —"),
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
    const [metadata, setMetadata] = useState(null);
    const [error, setError] = useState("");
    const [frameUrl, setFrameUrl] = useState("");
    const socketRef = useRef(null);
    const frameUrlRef = useRef("");

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
        const data = await fetchJSON("/api/v1/vision/status");
        setStatus(data);
        setError(data.error || data.disabled_reason || "");
        if (data.running) connectStream();
      } catch (err) {
        setError(err.message);
      }
    }, [connectStream]);

    const start = useCallback(async () => {
      try {
        const data = await fetchJSON("/api/v1/vision/start", { method: "POST" });
        setStatus(data);
        setError("");
        connectStream();
      } catch (err) {
        setError(err.message);
      }
    }, [connectStream]);

    const stop = useCallback(async () => {
      try {
        const data = await fetchJSON("/api/v1/vision/stop", { method: "POST" });
        disconnectStream();
        setStatus(data);
        setMetadata(null);
      } catch (err) {
        setError(err.message);
      }
    }, [disconnectStream]);

    useEffect(() => {
      loadStatus();
      return () => {
        disconnectStream();
        if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
      };
    }, [disconnectStream, loadStatus]);
    useInterval(loadStatus, 5000);

    const cfg = (metadata && metadata.camera) || (status && status.config) || {};
    const model = status ? (status.model_path || (status.model && status.model.path) || "not set") : "not set";
    const running = metadata ? metadata.running : status && status.running;
    const frameId = metadata ? metadata.frame_id : status && status.frame_id;
    const updated = metadata ? metadata.timestamp : status && status.timestamp;

    return h(React.Fragment, null,
      h("div", { className: "toolbar" },
        h("button", { className: "btn-sm", onClick: start }, "Start"),
        h("button", { className: "btn-sm", onClick: stop }, "Stop"),
        h("button", { className: "btn-sm", onClick: () => { disconnectStream(); connectStream(); } }, "Reconnect"),
      ),
      h("div", { className: "vision-preview" }, frameUrl
        ? h("img", { src: frameUrl, alt: "Vision stream" })
        : h("div", { className: "dim", style: { padding: "12px" } }, "No frame yet.")),
      h("div", { className: "kv-grid" },
        h("span", null, "Status"), h("span", { className: running ? "ok" : status && status.enabled ? "dim" : "err" }, running ? "running" : status && status.enabled ? "ready" : "disabled"),
        h("span", null, "Frame"), h("span", null, frameId ?? "—"),
        h("span", null, "People"), h("span", null, detections.length),
        h("span", null, "Camera"), h("span", null, `${cfg.index ?? cfg.camera_index ?? "—"} · ${cfg.width ?? "—"}x${cfg.height ?? "—"} · ${cfg.fps ?? "—"}fps`),
        h("span", null, "Model"), h("span", { title: model }, String(model).split("/").pop()),
        h("span", null, "Updated"), h("span", null, formatTime(updated)),
      ),
      error ? h("div", { className: "err" }, error) : null,
      h(DetectionList, { detections }),
      h(EventList, { events }),
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
        setRows(data || []);
      } catch {
        setRows([]);
      }
    }, []);

    useEffect(() => {
      load();
      const onReset = () => load();
      window.addEventListener("entity:session-reset", onReset);
      return () => window.removeEventListener("entity:session-reset", onReset);
    }, [load]);

    useEffect(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, [rows]);

    const send = useCallback(async () => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;
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
        setRows((current) => [...current, {
          id: `entity-${Date.now()}`,
          role: "entity",
          expression_output: output.text,
          delay_ms: output.delay_ms,
          visual_mode: output.visual_mode,
          turn_at: new Date().toISOString(),
        }]);
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

    const load = useCallback(async () => {
      const [llmConfig, embeddingConfig, llmStats] = await Promise.all([
        fetchJSON("/api/v1/config/llm").catch(() => null),
        fetchJSON("/api/v1/config/embedding").catch(() => null),
        fetchJSON("/api/v1/stats/llm").catch(() => null),
      ]);
      setLlm(llmConfig);
      setEmbedding(embeddingConfig);
      setStats(llmStats && llmStats.summary);
    }, []);

    useEffect(() => { load(); }, [load]);
    useInterval(load, 10000);

    return h(React.Fragment, null,
      h(ConfigSection, { title: "LLM Provider", data: llm, fields: ["mode", "source", "ENTITY_LLM_MODEL", "ANTHROPIC_BASE_URL", "ENTITY_LLM_MESSAGES_ENDPOINT", "error"] }),
      h(ConfigSection, { title: "Embedding Provider", data: embedding, fields: ["mode", "source", "ENTITY_EMBEDDING_MODEL", "ENTITY_EMBEDDING_BASE_URL", "ENTITY_EMBEDDING_ENDPOINT", "error"] }),
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
