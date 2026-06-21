(function () {
  "use strict";

  const SESSION_STORAGE_KEY = "stranger-arts-session-v1";
  const DEFAULT_API_BASE = "http://127.0.0.1:8000";
  const config = window.STRANGER_ARTS_CONFIG || {};
  const apiBase = normalizeBaseUrl(config.renderBaseUrl || DEFAULT_API_BASE);
  const state = {
    token: null,
    sessionId: null,
    visitorId: null,
    nickname: null,
    expiresAt: 0,
    busy: false,
    recording: false,
    mediaStream: null,
    audioContext: null,
    processor: null,
    websocket: null,
    audioQueue: [],
    audioPlaying: false,
    playedStreams: new Set(),
  };

  window.StrangerArts = {
    apiBase,
    fetchSurfaceJSON,
  };

  document.addEventListener("DOMContentLoaded", init);

  function init() {
    loadSession();
    bindForms();
    renderSession();
    if (state.token) {
      setStatus("listening");
    }
  }

  function bindForms() {
    const gateForm = byId("arts-gate-form");
    const textForm = byId("arts-text-form");
    const micButton = byId("arts-mic-button");

    gateForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const nickname = byId("arts-nickname").value.trim();
      await startSession(nickname);
    });

    textForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const input = byId("arts-text-input");
      const text = input.value.trim();
      if (!text || state.busy) return;
      input.value = "";
      await sendTurn(text, "text");
    });

    micButton.addEventListener("click", () => {
      if (state.recording) {
        stopRecording();
      } else {
        startRecording();
      }
    });
  }

  async function startSession(nickname) {
    if (!nickname) return;
    setBusy(true);
    setStatus("opening");
    try {
      const response = await fetch(apiUrl("/api/v1/public/session/start"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nickname,
        }),
      });
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json();
      state.token = payload.session_token;
      state.sessionId = payload.session_id;
      state.visitorId = payload.visitor_id;
      state.nickname = payload.nickname;
      state.expiresAt = Number(payload.expires_at || 0) * 1000;
      saveSession();
      renderSession();
      setStatus("listening");
    } catch {
      setStatus("closed");
    } finally {
      setBusy(false);
    }
  }

  async function sendTurn(text, inputMode) {
    if (!state.token) {
      setStatus("closed");
      return;
    }
    setBusy(true);
    setStatus("speaking");
    appendTurn("visitor", text);
    const replyNode = appendTurn("stranger", "");
    let replyText = "";
    try {
      const response = await authorizedFetch("/api/v1/public/dialog/progressive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          input_mode: inputMode,
        }),
      });
      if (!response.ok || !response.body) throw new Error(String(response.status));
      await readNdjson(response.body, (payload) => {
        const phase = String(payload.phase || "");
        const textPart = String(payload.text || "").trim();
        if (textPart && (phase === "first_unit" || phase === "second_delta" || phase === "final")) {
          replyText = mergeReply(replyText, textPart, phase);
          replyNode.textContent = replyText;
          scrollLog();
        }
        if (payload.tts_stream_id) {
          enqueueTts(String(payload.tts_stream_id));
        }
      });
      setStatus("listening");
    } catch {
      replyNode.textContent = "connection lost";
      setStatus("closed");
    } finally {
      setBusy(false);
    }
  }

  async function startRecording() {
    if (!state.token || state.recording || state.busy) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContext();
      const source = audioContext.createMediaStreamSource(stream);
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      const websocket = new WebSocket(wsUrl("/api/v1/public/audio/stt/stream"));
      websocket.binaryType = "arraybuffer";
      state.mediaStream = stream;
      state.audioContext = audioContext;
      state.processor = processor;
      state.websocket = websocket;
      state.recording = true;
      byId("arts-mic-button").classList.add("is-recording");
      setStatus("hearing");

      websocket.onopen = () => {
        websocket.send(JSON.stringify({
          type: "start",
          sample_rate: Math.round(audioContext.sampleRate),
          chunk_ms: 20,
          format: "pcm_s16le",
          channels: 1,
        }));
        source.connect(processor);
        processor.connect(audioContext.destination);
      };

      websocket.onmessage = (event) => {
        let payload = null;
        try {
          payload = JSON.parse(event.data);
        } catch {
          return;
        }
        if (payload && payload.type === "transcript.final" && payload.text) {
          const finalText = String(payload.text).trim();
          stopRecording();
          if (finalText) {
            sendTurn(finalText, "voice_transcript");
          }
        }
      };

      websocket.onerror = () => {
        stopRecording();
        setStatus("closed");
      };

      websocket.onclose = () => {
        if (state.recording) {
          stopRecording();
        }
      };

      processor.onaudioprocess = (event) => {
        if (!state.recording || websocket.readyState !== WebSocket.OPEN) return;
        const samples = event.inputBuffer.getChannelData(0);
        websocket.send(floatToPcm16(samples));
      };
    } catch {
      stopRecording();
      setStatus("closed");
    }
  }

  function stopRecording() {
    state.recording = false;
    byId("arts-mic-button").classList.remove("is-recording");
    if (state.processor) {
      state.processor.disconnect();
      state.processor.onaudioprocess = null;
      state.processor = null;
    }
    if (state.websocket && state.websocket.readyState === WebSocket.OPEN) {
      state.websocket.send(JSON.stringify({ type: "stop" }));
      state.websocket.close(1000);
    }
    state.websocket = null;
    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((track) => track.stop());
      state.mediaStream = null;
    }
    if (state.audioContext) {
      state.audioContext.close().catch(() => {});
      state.audioContext = null;
    }
    if (!state.busy && state.token) {
      setStatus("listening");
    }
  }

  async function fetchSurfaceJSON(url) {
    if (url === "/api/v1/state") {
      if (!state.token) return null;
      const response = await authorizedFetch("/api/v1/public/state");
      if (!response.ok) throw new Error(String(response.status));
      const payload = await response.json();
      return payload.state || null;
    }
    const response = await fetch(apiUrl(url));
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  async function authorizedFetch(path, options) {
    const next = { ...(options || {}) };
    next.headers = { ...(next.headers || {}), Authorization: `Bearer ${state.token}` };
    return fetch(apiUrl(path), next);
  }

  async function readNdjson(body, onPayload) {
    const reader = body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) {
          onPayload(JSON.parse(line));
        }
        newline = buffer.indexOf("\n");
      }
    }
    const tail = buffer.trim();
    if (tail) {
      onPayload(JSON.parse(tail));
    }
  }

  function mergeReply(existing, incoming, phase) {
    if (!existing) return incoming;
    if (phase === "second_delta" && incoming.startsWith(existing)) return incoming;
    if (phase === "final" && existing.includes(incoming)) return existing;
    if (incoming.startsWith(existing)) return incoming;
    return `${existing}\n${incoming}`;
  }

  function appendTurn(role, text) {
    const log = byId("arts-turn-log");
    const node = document.createElement("div");
    node.className = "turn";
    node.dataset.role = role;
    node.textContent = text;
    log.appendChild(node);
    scrollLog();
    return node;
  }

  function scrollLog() {
    const log = byId("arts-turn-log");
    log.scrollTop = log.scrollHeight;
  }

  function enqueueTts(streamId) {
    if (state.playedStreams.has(streamId)) return;
    state.playedStreams.add(streamId);
    state.audioQueue.push(streamId);
    playNextAudio();
  }

  async function playNextAudio() {
    if (state.audioPlaying || state.audioQueue.length === 0) return;
    const streamId = state.audioQueue.shift();
    state.audioPlaying = true;
    try {
      const response = await authorizedFetch(`/api/v1/public/audio/tts/stream/${encodeURIComponent(streamId)}`);
      if (response.ok) {
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        await new Promise((resolve) => {
          audio.onended = resolve;
          audio.onerror = resolve;
          audio.play().catch(resolve);
        });
        URL.revokeObjectURL(url);
      }
    } finally {
      state.audioPlaying = false;
      playNextAudio();
    }
  }

  function floatToPcm16(samples) {
    const buffer = new ArrayBuffer(samples.length * 2);
    const view = new DataView(buffer);
    for (let i = 0; i < samples.length; i += 1) {
      const value = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(i * 2, value < 0 ? value * 0x8000 : value * 0x7fff, true);
    }
    return buffer;
  }

  function renderSession() {
    const hasSession = Boolean(state.token);
    byId("arts-gate-form").hidden = hasSession;
    byId("arts-dialog").hidden = !hasSession;
    byId("arts-text-input").disabled = !hasSession;
    byId("arts-mic-button").disabled = !hasSession;
    if (state.nickname) {
      byId("arts-nickname").value = state.nickname;
    }
  }

  function setBusy(value) {
    state.busy = Boolean(value);
    byId("arts-text-input").disabled = state.busy || !state.token;
    byId("arts-mic-button").disabled = state.busy || !state.token;
  }

  function setStatus(value) {
    byId("arts-status").textContent = value;
  }

  function saveSession() {
    localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify({
      token: state.token,
      sessionId: state.sessionId,
      visitorId: state.visitorId,
      nickname: state.nickname,
      expiresAt: state.expiresAt,
    }));
  }

  function loadSession() {
    try {
      const raw = localStorage.getItem(SESSION_STORAGE_KEY);
      if (!raw) return;
      const payload = JSON.parse(raw);
      if (Number(payload.expiresAt || 0) <= Date.now()) {
        localStorage.removeItem(SESSION_STORAGE_KEY);
        return;
      }
      state.token = payload.token || null;
      state.sessionId = payload.sessionId || null;
      state.visitorId = payload.visitorId || null;
      state.nickname = payload.nickname || null;
      state.expiresAt = Number(payload.expiresAt || 0);
    } catch {
      localStorage.removeItem(SESSION_STORAGE_KEY);
    }
  }

  function apiUrl(path) {
    if (/^https?:\/\//i.test(path)) return path;
    return `${apiBase}${path.startsWith("/") ? path : `/${path}`}`;
  }

  function wsUrl(path) {
    const base = apiBase.replace(/^http:/i, "ws:").replace(/^https:/i, "wss:");
    const separator = path.includes("?") ? "&" : "?";
    return `${base}${path}${separator}session_token=${encodeURIComponent(state.token)}`;
  }

  function normalizeBaseUrl(value) {
    return String(value || DEFAULT_API_BASE).replace(/\/+$/, "");
  }

  function byId(id) {
    return document.getElementById(id);
  }
})();
