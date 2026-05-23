(function () {
  "use strict";

  const THREE_MODULE_PATH = "/particle-display-assets/vendor/three.module.js";
  const POLL_MS = 250;
  const SPEAKING_HOLD_MS = 1200;
  const ORBIT_PARTICLE_COUNT = 2200;
  const CORE_PARTICLE_COUNT = 5600;
  const STREAM_PARTICLE_COUNT = 2400;
  const OUTER_HALO_PARTICLE_COUNT = 5600;
  const SPEECH_BAND_COUNT = 512;
  const CORE_RADIUS = 0.98;
  const SPEAKING_MIN_RADIUS_SCALE = 2 / 3;
  const SPEAKING_MAX_RADIUS_SCALE = 5 / 3;
  const CORE_DEFORMATION_LOBE_COUNT = 13;
  const CORE_SPEECH_TIME_SCALE = 0.5;
  const MIN_BURST_INTERVAL = 0.12;
  const MAX_BURST_INTERVAL = 1.0;
  const WAKE_CHANNEL_NAME = "have_some_ai_wake";
  const WAKE_REQUEST_TYPE = "particle_display_wake_request";
  const WAKE_ACK_TYPE = "control_wake_ack";
  const WAKE_REQUEST_TIMEOUT_MS = 3200;
  const WAKE_ACTIVATION_MS = 600;
  const WAKE_PROMPT_ZH = "按按钮叫醒我";
  const WAKE_PROMPT_EN = "press the button to wake me";

  const QUIET_SIGNALS = Object.freeze({
    speaking: 0,
    brightness: 0.68,
    orbitSpeed: 0.004,
    shake: 0,
    disorder: 0.002,
    radiusPull: 0.94,
    densityBias: 0.18,
    breathe: 0.002,
    breatheSpeed: 0.12,
    particleSize: 0.018,
    glow: 0.18,
    speechEnergy: 0.008,
    speechRate: 0.18,
    spikeHeight: 0.012,
    burstPower: 0.012,
    opacityScale: 0.9,
    haloSpeed: 0.006,
    haloBrightness: 0.55,
    haloSpread: 0.16,
    haloWave: 0.003,
    haloSize: 0.019,
  });

  const SPEAKING_SIGNALS = Object.freeze({
    speaking: 1,
    brightness: QUIET_SIGNALS.brightness,
    orbitSpeed: QUIET_SIGNALS.orbitSpeed,
    shake: QUIET_SIGNALS.shake,
    disorder: QUIET_SIGNALS.disorder,
    radiusPull: QUIET_SIGNALS.radiusPull,
    densityBias: QUIET_SIGNALS.densityBias,
    breathe: QUIET_SIGNALS.breathe,
    breatheSpeed: QUIET_SIGNALS.breatheSpeed,
    particleSize: QUIET_SIGNALS.particleSize,
    glow: QUIET_SIGNALS.glow,
    speechEnergy: 1.2,
    speechRate: 0.88,
    spikeHeight: 0.12,
    burstPower: 0.72,
    opacityScale: QUIET_SIGNALS.opacityScale,
    haloSpeed: QUIET_SIGNALS.haloSpeed,
    haloBrightness: QUIET_SIGNALS.haloBrightness,
    haloSpread: QUIET_SIGNALS.haloSpread,
    haloWave: QUIET_SIGNALS.haloWave,
    haloSize: QUIET_SIGNALS.haloSize,
  });

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function lerp(left, right, amount) {
    return left + (right - left) * amount;
  }

  function smoothstep(edge0, edge1, value) {
    const t = clamp((value - edge0) / (edge1 - edge0), 0, 1);
    return t * t * (3 - 2 * t);
  }

  function sampleBand(values, amount) {
    const scaled = clamp(amount, 0, 1) * (values.length - 1);
    const left = Math.floor(scaled);
    const right = Math.min(values.length - 1, left + 1);
    return lerp(values[left], values[right], scaled - left);
  }

  function randomBetween(min, max) {
    return min + Math.random() * (max - min);
  }

  function randomUnitVector() {
    const z = randomBetween(-1, 1);
    const angle = Math.random() * Math.PI * 2;
    const radius = Math.sqrt(Math.max(0, 1 - z * z));
    return {
      x: Math.cos(angle) * radius,
      y: Math.sin(angle) * radius,
      z,
    };
  }

  function createGlowTexture(THREE) {
    const size = 512;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d");
    const gradient = ctx.createRadialGradient(
      size / 2,
      size / 2,
      size * 0.08,
      size / 2,
      size / 2,
      size * 0.5
    );
    gradient.addColorStop(0, "rgba(230,255,232,0.55)");
    gradient.addColorStop(0.22, "rgba(168,255,196,0.26)");
    gradient.addColorStop(0.54, "rgba(78,224,166,0.08)");
    gradient.addColorStop(0.78, "rgba(35,135,100,0.022)");
    gradient.addColorStop(1, "rgba(35,135,100,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    return texture;
  }

  async function fetchJSON(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function isSystemSpeaking(state) {
    if (!state || typeof state !== "object") return false;
    return (
      state.avatar_system_speaking === true
      || state.mode === "robot_speaking"
      || state.robot_active === true
    );
  }

  function buildSignals(speaking) {
    return { ...(speaking ? SPEAKING_SIGNALS : QUIET_SIGNALS) };
  }

  function cleanText(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function createParticleCue({ root, mainLine, resultLine, optionsLine, subLine } = {}) {
    let lastSignature = "";

    function splitDisplayText(value, mode) {
      const text = cleanText(value);
      if (!text) return { lead: "", options: [] };
      const lines = text.split(/\n+/).map((line) => line.trim()).filter(Boolean);
      if (mode !== "question" || lines.length < 2) {
        return { lead: text, options: [] };
      }
      return {
        lead: lines[0],
        options: lines.slice(1),
      };
    }

    function setMainText(value) {
      const text = cleanText(value);
      mainLine.textContent = text;
      mainLine.classList.toggle("is-long", text.length > 42);
      mainLine.classList.toggle("is-very-long", text.length > 82);
    }

    function setOptions(items) {
      optionsLine.replaceChildren();
      optionsLine.hidden = items.length === 0;
      for (const item of items) {
        const line = document.createElement("p");
        line.className = "particle-option-line";
        line.textContent = item;
        optionsLine.appendChild(line);
      }
    }

    function enter(signature) {
      if (signature === lastSignature) return;
      lastSignature = signature;
      root.hidden = false;
    }

    function hide() {
      lastSignature = "";
      setMainText("");
      setOptions([]);
      resultLine.textContent = "";
      subLine.textContent = "";
      root.hidden = true;
    }

    function setModeClass(mode) {
      root.classList.remove("state-idle", "state-question", "state-robot-speaking", "state-result", "state-error");
      if (mode === "question") root.classList.add("state-question");
      else if (mode === "robot_speaking") root.classList.add("state-robot-speaking");
      else if (mode === "result") root.classList.add("state-result");
      else if (mode === "error") root.classList.add("state-error");
      else root.classList.add("state-idle");
    }

    function render({
      mode = "idle",
      display_text: displayText = "",
      food_name: foodName = "",
      food_subtitle: foodSubtitle = "",
    } = {}) {
      const normalizedMode = cleanText(mode) || "idle";
      setModeClass(normalizedMode);
      resultLine.textContent = "";
      subLine.textContent = "";
      setOptions([]);

      if (normalizedMode === "result") {
        const resultText = cleanText(displayText);
        const title = cleanText(foodName) || resultText;
        if (!title && !resultText) {
          hide();
          return;
        }
        resultLine.textContent = resultText;
        setMainText(title);
        subLine.textContent = cleanText(foodSubtitle);
        enter([normalizedMode, resultText, title, cleanText(foodSubtitle)].join("|"));
        return;
      }

      const text = cleanText(displayText);
      if (!text) {
        hide();
        return;
      }
      const cue = splitDisplayText(text, normalizedMode);
      setMainText(cue.lead);
      setOptions(cue.options);
      enter([normalizedMode, cue.lead, cue.options.join("|")].join("|"));
    }

    return { render };
  }

  function createWakeButtonController({ root, button } = {}) {
    let channel = null;
    let requestId = "";
    let timeoutId = null;
    let active = false;

    function post(message) {
      if (!channel) return;
      channel.postMessage(message);
    }

    function clearPendingTimeout() {
      if (timeoutId === null) return;
      window.clearTimeout(timeoutId);
      timeoutId = null;
    }

    function setVisible(visible) {
      if (!button) return;
      if (visible) {
        button.hidden = false;
        window.requestAnimationFrame(() => {
          button.classList.add("is-visible");
        });
      } else {
        button.classList.remove("is-visible");
        if (!active) button.hidden = true;
      }
    }

    function reset() {
      active = false;
      requestId = "";
      clearPendingTimeout();
      if (!button) return;
      button.disabled = false;
      button.classList.remove("is-activating");
    }

    function handleAck(message) {
      if (!message || message.type !== WAKE_ACK_TYPE || message.requestId !== requestId) return;
      if (message.status === "created") {
        clearPendingTimeout();
        timeoutId = window.setTimeout(() => {
          reset();
          if (button) {
            button.classList.remove("is-visible");
            button.hidden = true;
          }
        }, WAKE_ACTIVATION_MS);
        return;
      }
      reset();
      setVisible(true);
    }

    function handleClick() {
      if (!button || active) return;
      active = true;
      requestId = `wake-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      button.disabled = true;
      button.classList.add("is-activating");
      post({
        type: WAKE_REQUEST_TYPE,
        requestId,
        source: "particle-display",
        sentAt: Date.now(),
      });
      timeoutId = window.setTimeout(() => {
        reset();
        setVisible(true);
      }, WAKE_REQUEST_TIMEOUT_MS);
    }

    function render(state) {
      const mode = cleanText(state?.mode) || "idle";
      const displayText = cleanText(state?.display_text);
      const lowerText = displayText.toLowerCase();
      const shouldShow = (
        mode === "idle"
        && (displayText.includes(WAKE_PROMPT_ZH) || lowerText.includes(WAKE_PROMPT_EN))
      );
      root.classList.toggle("has-wake-button", shouldShow);
      if (!active) setVisible(shouldShow && Boolean(channel));
    }

    function dispose() {
      clearPendingTimeout();
      if (channel) {
        channel.close();
        channel = null;
      }
      if (button) button.removeEventListener("click", handleClick);
    }

    if (button && "BroadcastChannel" in window) {
      channel = new BroadcastChannel(WAKE_CHANNEL_NAME);
      channel.addEventListener("message", (event) => handleAck(event.data));
      button.addEventListener("click", handleClick);
    }

    return { render, dispose };
  }

  class GreenParticleRenderer {
    constructor(host, THREE) {
      this.host = host;
      this.THREE = THREE;
      this.frameId = 0;
      this.disposed = false;
      this.current = buildSignals(false);
      this.target = buildSignals(false);
      this.displayColor = new THREE.Color(0x285f49);
      this.quietColor = new THREE.Color(0x174d3c);
      this.isSpeakingActive = false;
      this.greenPalette = [
        new THREE.Color(0x1b6f4f),
        new THREE.Color(0x2cbf83),
        new THREE.Color(0x66d9af),
        new THREE.Color(0xa4efbb),
        new THREE.Color(0x4ecab7),
      ];
      this.resize = this.resize.bind(this);
      this.animate = this.animate.bind(this);

      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
      this.camera.position.set(0, 0.02, 5.45);

      this.renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setClearColor(0x020807, 0);
      this.host.appendChild(this.renderer.domElement);

      this.clock = new THREE.Clock();
      this.root = new THREE.Group();
      this.scene.add(this.root);

      this.scene.add(new THREE.AmbientLight(0xc8ffd8, 0.38));
      const keyLight = new THREE.PointLight(0x9af0b3, 2.8, 9);
      keyLight.position.set(-2.8, 2.1, 3.2);
      this.scene.add(keyLight);
      const rimLight = new THREE.PointLight(0x43d6b4, 1.5, 8);
      rimLight.position.set(2.6, -1.6, 2.4);
      this.scene.add(rimLight);

      this.createOrb();
      this.createParticles();
      this.createOuterHalo();
      this.createShellFlow();

      if ("ResizeObserver" in window) {
        this.resizeObserver = new ResizeObserver(this.resize);
        this.resizeObserver.observe(this.host);
      } else {
        this.resizeObserver = null;
      }
      window.addEventListener("resize", this.resize);
      this.resize();
    }

    createOrb() {
      const THREE = this.THREE;
      const positions = new Float32Array(CORE_PARTICLE_COUNT * 3);
      const colors = new Float32Array(CORE_PARTICLE_COUNT * 3);
      const middle = Math.floor(CORE_PARTICLE_COUNT / 2);
      const meta = [];
      const step = 2 / CORE_PARTICLE_COUNT;
      const turns = 68;
      let pointIndex = 0;

      for (let y = -1; y <= 1 && pointIndex < CORE_PARTICLE_COUNT; y += step) {
        const phi = Math.acos(y);
        const theta = (2 * turns * phi) % (Math.PI * 2);
        const ring = Math.sin(phi);
        const nx = Math.cos(theta) * ring;
        const ny = Math.cos(phi);
        const nz = Math.sin(theta) * ring;
        const index = pointIndex * 3;
        positions[index] = nx * CORE_RADIUS;
        positions[index + 1] = ny * CORE_RADIUS;
        positions[index + 2] = nz * CORE_RADIUS;
        colors[index] = 0.5;
        colors[index + 1] = 0.86;
        colors[index + 2] = 0.62;
        const mirrorIndex = Math.abs(pointIndex - middle);
        const speechBand = clamp(mirrorIndex / middle, 0, 1);
        meta.push({
          nx,
          ny,
          nz,
          phase: theta + Math.random() * 0.08,
          equator: 1 - Math.abs(ny),
          pole: Math.abs(ny),
          speechBand,
          speed: 0.55 + Math.random() * 1.35,
          speck: Math.random(),
        });
        pointIndex += 1;
      }

      this.coreMeta = meta;
      this.deformationLobes = this.createDeformationLobes();
      this.corePositions = positions;
      this.coreColors = colors;
      this.speechSpectrum = new Float32Array(SPEECH_BAND_COUNT);
      this.speechBursts = new Float32Array(SPEECH_BAND_COUNT);
      this.lastSpectrumTime = 0;
      this.nextBurstAt = 0;
      this.coreGeometry = new THREE.BufferGeometry();
      this.coreGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.coreGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      this.coreMaterial = new THREE.PointsMaterial({
        size: 0.026,
        vertexColors: true,
        transparent: true,
        opacity: 0.86,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      this.coreSphere = new THREE.Points(this.coreGeometry, this.coreMaterial);
      this.root.add(this.coreSphere);

      this.glowTexture = createGlowTexture(THREE);
      this.glowMaterial = new THREE.SpriteMaterial({
        map: this.glowTexture,
        color: 0x84e8ad,
        transparent: true,
        opacity: 0.16,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      });
      this.glow = new THREE.Sprite(this.glowMaterial);
      this.glow.renderOrder = -2;
      this.root.add(this.glow);
    }

    createDeformationLobes() {
      const lobes = [];
      for (let i = 0; i < CORE_DEFORMATION_LOBE_COUNT; i += 1) {
        const direction = randomUnitVector();
        lobes.push({
          ...direction,
          width: randomBetween(0.16, 0.36),
          phase: Math.random() * Math.PI * 2,
          speed: randomBetween(0.18, 1.18),
          strength: randomBetween(0.46, 1.08),
          sign: Math.random() < 0.44 ? -1 : 1,
          band: Math.random(),
          skew: Math.random() * Math.PI * 2,
        });
      }
      return lobes;
    }

    createParticles() {
      const THREE = this.THREE;
      const positions = new Float32Array(ORBIT_PARTICLE_COUNT * 3);
      const colors = new Float32Array(ORBIT_PARTICLE_COUNT * 3);
      const meta = [];

      for (let i = 0; i < ORBIT_PARTICLE_COUNT; i += 1) {
        const band = i / ORBIT_PARTICLE_COUNT;
        const outer = Math.pow(Math.random(), 0.55);
        meta.push({
          phase: Math.random() * Math.PI * 2,
          radius: 1.18 + outer * 2.1 + band * 0.18,
          y: (Math.random() - 0.5) * (0.55 + outer * 0.7),
          speed: 0.38 + Math.random() * 0.96,
          depth: 0.28 + Math.random() * 0.36,
          wobble: 0.5 + Math.random() * 2.4,
          outer,
          spark: Math.random(),
        });
        colors[i * 3] = 0.42;
        colors[i * 3 + 1] = 0.88;
        colors[i * 3 + 2] = 0.58;
      }

      this.particleMeta = meta;
      this.particlePositions = positions;
      this.particleColors = colors;
      this.particleGeometry = new THREE.BufferGeometry();
      this.particleGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.particleGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      this.particleMaterial = new THREE.PointsMaterial({
        size: this.current.particleSize,
        vertexColors: true,
        transparent: true,
        opacity: 0.68,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      this.particles = new THREE.Points(this.particleGeometry, this.particleMaterial);
      this.scene.add(this.particles);
    }

    createOuterHalo() {
      const THREE = this.THREE;
      const positions = new Float32Array(OUTER_HALO_PARTICLE_COUNT * 3);
      const colors = new Float32Array(OUTER_HALO_PARTICLE_COUNT * 3);
      const meta = [];
      const lanes = 18;

      for (let i = 0; i < OUTER_HALO_PARTICLE_COUNT; i += 1) {
        const lane = (i % lanes) - (lanes - 1) / 2;
        const laneBias = lane / lanes;
        const band = Math.pow(Math.random(), 0.62);
        const radius = 2.65 + band * 3.25 + Math.abs(laneBias) * 0.32;
        meta.push({
          phase: Math.random() * Math.PI * 2,
          radius,
          lane: laneBias + (Math.random() - 0.5) * 0.035,
          speed: 0.22 + Math.random() * 1.25,
          depth: 0.18 + Math.random() * 0.82,
          wave: Math.random() * Math.PI * 2,
          spark: Math.random(),
          burstSign: Math.random() < 0.5 ? -1 : 1,
          band,
        });
        colors[i * 3] = 0.38;
        colors[i * 3 + 1] = 0.86;
        colors[i * 3 + 2] = 0.6;
      }

      this.haloMeta = meta;
      this.haloPositions = positions;
      this.haloColors = colors;
      this.haloGeometry = new THREE.BufferGeometry();
      this.haloGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.haloGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      this.haloMaterial = new THREE.PointsMaterial({
        size: this.current.haloSize,
        vertexColors: true,
        transparent: true,
        opacity: 0.38,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      });
      this.outerHaloGroup = new THREE.Group();
      this.outerHaloGroup.position.set(0, -0.02, -0.16);
      this.outerHaloGroup.rotation.x = 0;
      this.outerHaloGroup.rotation.y = 0;
      this.outerHaloGroup.rotation.z = 0;
      this.outerHalo = new THREE.Points(this.haloGeometry, this.haloMaterial);
      this.outerHalo.renderOrder = -1;
      this.outerHaloGroup.add(this.outerHalo);
      this.scene.add(this.outerHaloGroup);
    }

    createShellFlow() {
      const THREE = this.THREE;
      const positions = new Float32Array(STREAM_PARTICLE_COUNT * 3);
      const colors = new Float32Array(STREAM_PARTICLE_COUNT * 3);
      const meta = [];
      const bands = 9;

      for (let i = 0; i < STREAM_PARTICLE_COUNT; i += 1) {
        const band = i % bands;
        const bandOffset = (band - (bands - 1) / 2) / bands;
        const phase = Math.random() * Math.PI * 2;
        const tilt = -0.55 + band * 0.14 + (Math.random() - 0.5) * 0.04;
        meta.push({
          phase,
          tilt,
          bandOffset,
          radius: 0.86 + Math.random() * 0.22,
          speed: 0.45 + Math.random() * 1.2,
          wave: Math.random() * Math.PI * 2,
          spark: Math.random(),
        });
        colors[i * 3] = 0.68;
        colors[i * 3 + 1] = 0.94;
        colors[i * 3 + 2] = 0.72;
      }

      this.streamMeta = meta;
      this.streamPositions = positions;
      this.streamColors = colors;
      this.streamGeometry = new THREE.BufferGeometry();
      this.streamGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.streamGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      this.streamMaterial = new THREE.PointsMaterial({
        size: 0.021,
        vertexColors: true,
        transparent: true,
        opacity: 0.62,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      this.shellFlow = new THREE.Points(this.streamGeometry, this.streamMaterial);
      this.root.add(this.shellFlow);
    }

    setSpeaking(speaking) {
      const active = Boolean(speaking);
      this.target = buildSignals(active);
      if (active && !this.isSpeakingActive) {
        this.current.speaking = Math.max(this.current.speaking, 0.62);
        this.current.speechEnergy = Math.max(this.current.speechEnergy, 0.72);
        this.current.burstPower = Math.max(this.current.burstPower, 0.42);
        this.nextBurstAt = Math.min(this.nextBurstAt, this.clock ? this.clock.elapsedTime : 0);
      }
      this.isSpeakingActive = active;
    }

    start() {
      if (this.disposed) return;
      this.clock.start();
      this.animate();
    }

    resize() {
      const rect = this.host.getBoundingClientRect();
      const width = Math.max(1, Math.floor(rect.width || window.innerWidth));
      const height = Math.max(1, Math.floor(rect.height || window.innerHeight));
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height, false);
    }

    animate() {
      if (this.disposed) return;
      const delta = Math.min(0.05, this.clock.getDelta());
      const time = this.clock.elapsedTime;
      const smooth = clamp(delta * 2.6, 0.02, 0.2);

      Object.keys(this.current).forEach((key) => {
        this.current[key] = lerp(this.current[key], this.target[key], smooth);
      });

      this.updateDisplayColor(time);
      this.updateOrb(time);
      this.updateOuterHalo(time);
      this.updateParticles(time);
      this.renderer.render(this.scene, this.camera);
      this.frameId = window.requestAnimationFrame(this.animate);
    }

    updateDisplayColor(time) {
      const phase = (time * 0.035) % this.greenPalette.length;
      const leftIndex = Math.floor(phase);
      const rightIndex = (leftIndex + 1) % this.greenPalette.length;
      const amount = smoothstep(0, 1, phase - leftIndex);
      this.displayColor.copy(this.greenPalette[leftIndex]).lerp(this.greenPalette[rightIndex], amount);
      this.displayColor.lerp(this.quietColor, 0.6);
    }

    updateOrb(time) {
      const current = this.current;
      const shake = current.shake;
      this.root.position.set(
        Math.sin(time * 38.0) * shake + Math.sin(time * 13.0) * shake * 0.42,
        Math.cos(time * 31.0) * shake * 0.7,
        0
      );
      const breathe = 1 + Math.sin(time * current.breatheSpeed * Math.PI * 2) * current.breathe;
      this.root.scale.setScalar(breathe);
      this.root.rotation.y = Math.sin(time * 0.18) * 0.04;
      this.root.rotation.x = Math.cos(time * 0.14) * 0.02;

      this.glowMaterial.color.copy(this.displayColor);
      this.glowMaterial.opacity = clamp(current.glow * 0.95, 0.08, 0.68);
      const glowScale = 4.1 + current.glow * 2.9 + current.shake * 4.2;
      this.glow.scale.set(glowScale, glowScale, 1);
      this.updateCoreSphere(time);
      this.updateShellFlow(time);
    }

    updateSpeechSpectrum(time) {
      const current = this.current;
      const values = this.speechSpectrum;
      const bursts = this.speechBursts;
      const active = clamp(current.speechEnergy, 0, 1);
      const rate = current.speechRate;
      const delta = clamp(time - this.lastSpectrumTime || 0.016, 0.008, 0.08);
      this.lastSpectrumTime = time;
      const phrase = 0.58 + Math.pow(0.5 + Math.sin(time * rate * 1.35 + 0.7) * 0.5, 2.2) * 0.42;
      const lowGate = Math.pow(0.5 + Math.sin(time * rate * 5.4 + Math.sin(time * 1.7) * 1.1) * 0.5, 2.6);
      const midGate = Math.pow(0.5 + Math.sin(time * rate * 8.3 + 1.9) * 0.5, 3.8);
      const highGate = Math.pow(0.5 + Math.sin(time * rate * 12.8 + Math.sin(time * 3.1) * 0.7) * 0.5, 5.2);
      const baseline = 0.012 + active * 0.075;
      const decay = Math.exp(-delta * (7.6 - current.speaking * 2.2));

      for (let i = 0; i < bursts.length; i += 1) {
        bursts[i] *= decay;
        if (Math.abs(bursts[i]) < 0.008) bursts[i] = 0;
      }

      while (time >= this.nextBurstAt) {
        const burstCount = Math.floor(randomBetween(0, 1.4 + current.burstPower * 4.2));
        for (let n = 0; n < burstCount; n += 1) {
          const zoneRoll = Math.random();
          let center;
          if (zoneRoll < 0.34) {
            center = Math.pow(Math.random(), 2.5) * 0.24;
          } else if (zoneRoll < 0.78) {
            center = 0.58 + Math.pow(Math.random(), 0.55) * 0.42;
          } else {
            center = Math.random();
          }
          const centerIndex = Math.floor(center * (bursts.length - 1));
          const width = 1 + Math.floor(randomBetween(0, 2 + current.burstPower * 3.8));
          const inward = Math.random() < 0.22;
          const sign = inward ? -1 : 1;
          const intensity = randomBetween(0.35, 1.18) * current.burstPower;

          for (let offset = -width; offset <= width; offset += 1) {
            const bandIndex = centerIndex + offset;
            if (bandIndex < 0 || bandIndex >= bursts.length) continue;
            const falloff = Math.pow(1 - Math.abs(offset) / (width + 1), 2.6);
            bursts[bandIndex] = clamp(bursts[bandIndex] + sign * intensity * falloff, -1.05, 1.25);
          }
        }

        const nextInterval = randomBetween(MIN_BURST_INTERVAL, MAX_BURST_INTERVAL)
          / clamp(0.72 + rate * 0.34 + current.burstPower * 0.34, 0.72, 1.75);
        this.nextBurstAt = time + nextInterval;
      }

      for (let i = 0; i < values.length; i += 1) {
        const band = i / (values.length - 1);
        const equatorBand = Math.exp(-band * 4.4);
        const midBand = Math.exp(-Math.abs(band - 0.42) * 5.8);
        const poleBand = Math.pow(smoothstep(0.54, 1, band), 1.75);
        const lowPulse = (0.42 + lowGate * 0.58)
          * (0.62 + Math.sin(time * rate * 3.1 + band * 8.0) * 0.38);
        const midPulse = midGate
          * Math.pow(0.5 + Math.sin(time * rate * 7.2 + band * 21.0 + Math.sin(time * 1.3) * 1.6) * 0.5, 2.2);
        const highPulse = highGate
          * Math.pow(0.5 + Math.sin(time * rate * (15.5 + current.burstPower * 4.0) + band * 49.0 + Math.sin(time * 3.7 + band * 12.0)) * 0.5, 3.8);
        const grain = Math.sin(i * 12.9898 + time * rate * (17.0 + band * 28.0) + Math.sin(time * 2.0 + band * 11.0));
        const irregular = grain * (0.012 + current.burstPower * 0.075);
        const amplitude = baseline
          + active * phrase * (
            equatorBand * lowPulse * 0.32
            + midBand * midPulse * 0.14
            + poleBand * highPulse * 0.32
          )
          + irregular;
        values[i] = clamp(amplitude, 0.008, 0.62);
      }

      return values;
    }

    updateCoreSphere(time) {
      const current = this.current;
      const positions = this.corePositions;
      const colors = this.coreColors;
      const base = this.displayColor;
      const spectrum = this.updateSpeechSpectrum(time);
      const bursts = this.speechBursts;
      const syllable = Math.pow(0.5 + Math.sin(time * current.speechRate * 6.0) * 0.5, 2.4);
      const largeDeform = smoothstep(0.12, 0.72, current.speaking)
        * smoothstep(0.05, 0.78, current.speechEnergy);
      const detailScale = 1 - largeDeform * 0.74;

      for (let i = 0; i < this.coreMeta.length; i += 1) {
        const m = this.coreMeta[i];
        const index = i * 3;
        const bandLevel = sampleBand(spectrum, m.speechBand);
        const burstLevel = sampleBand(bursts, m.speechBand);
        const burstAbs = Math.abs(burstLevel);
        const burstSign = burstLevel < 0 ? -1 : 1;
        const equatorWeight = Math.pow(1 - m.speechBand, 2.2);
        const poleWeight = Math.pow(m.speechBand, 2.35);
        const needleSeed = bandLevel * (0.78 + m.speck * 0.44);
        const needle = Math.pow(clamp(needleSeed, 0, 1.2), 1.2);
        const localMask = Math.pow(0.5 + Math.sin(m.phase * 9.7 + time * (8.0 + m.speed * 5.6)) * 0.5, 2.7);
        const burstNeedle = Math.pow(clamp(burstAbs * (0.72 + m.speck * 0.72) * (0.62 + localMask), 0, 1.7), 1.08);
        const burstScale = burstSign * burstNeedle * (0.12 + current.burstPower * 0.2) * detailScale
          * (0.74 + equatorWeight * 0.48 + poleWeight * 1.38);
        const equatorThrob = equatorWeight * current.speechEnergy * (0.006 + syllable * 0.02) * detailScale;
        const polarNeedle = poleWeight * needle * (0.018 + current.burstPower * 0.07) * detailScale;
        const speechSpike = needle * (current.spikeHeight + 0.006) * detailScale * (0.38 + equatorWeight * 0.32 + poleWeight * 0.74);
        const alwaysRough = (0.006 + m.speck * 0.016)
          * (0.42 + current.speechEnergy)
          * (0.52 + detailScale * 0.48)
          * (0.5 + Math.sin(time * (14.0 + m.speed * 7.0) + m.phase * 3.1) * 0.5);
        const surfaceTremor = Math.sin(time * 24 + m.phase * 3.7)
          * current.shake
          * (0.72 + m.speck + poleWeight * 0.7);
        const instability = Math.sin(time * (3.2 + m.speed) + m.phase + m.speechBand * 11.0)
          * current.disorder
          * (0.012 + poleWeight * 0.04 + equatorWeight * 0.025);
        const fineRadiusScale = 1
          + speechSpike
          + equatorThrob
          + polarNeedle
          + burstScale
          + alwaysRough * detailScale
          + surfaceTremor
          + instability;
        const deformationField = this.largeDeformationField(m, time, bandLevel, burstLevel);
        const outwardScale = 1 + Math.max(0, deformationField) * (SPEAKING_MAX_RADIUS_SCALE - 1);
        const inwardScale = 1 + Math.min(0, deformationField) * (1 - SPEAKING_MIN_RADIUS_SCALE);
        const macroRadiusScale = deformationField >= 0 ? outwardScale : inwardScale;
        // Speaking deformation is intentionally large: 2/3R inward to 5/3R outward.
        const radiusScale = clamp(
          lerp(fineRadiusScale, macroRadiusScale, largeDeform),
          lerp(0.62, SPEAKING_MIN_RADIUS_SCALE, largeDeform),
          lerp(1.22, SPEAKING_MAX_RADIUS_SCALE, largeDeform)
        );
        const radius = CORE_RADIUS * radiusScale;

        positions[index] = m.nx * radius;
        positions[index + 1] = m.ny * radius;
        positions[index + 2] = m.nz * radius;

        const rim = clamp(0.24 + m.equator * 0.16 + m.pole * 0.18 + m.speck * 0.05, 0.1, 0.86);
        const flicker = 0.72
          + Math.sin(time * (7.0 + m.speed * 5.0) + m.phase * 2.2) * 0.035;
        const inwardDim = burstLevel < 0 ? 1 - clamp(burstAbs * 0.32, 0, 0.45) : 1;
        const brightness = clamp((current.brightness * rim * flicker + m.speck * 0.05) * inwardDim, 0.04, 1.58);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.coreSphere.rotation.y = time * (0.018 + current.orbitSpeed * 0.07);
      this.coreSphere.rotation.x = Math.sin(time * 0.23) * (0.016 + current.disorder * 0.12);
      this.coreMaterial.size = clamp(0.019 + current.glow * 0.02, 0.019, 0.044);
      this.coreMaterial.opacity = clamp((0.44 + current.brightness * 0.46) * current.opacityScale, 0.38, 1);
      this.coreGeometry.attributes.position.needsUpdate = true;
      this.coreGeometry.attributes.color.needsUpdate = true;
    }

    largeDeformationField(meta, time, bandLevel, burstLevel) {
      const current = this.current;
      const speech = clamp(current.speaking * current.speechEnergy, 0, 1);
      if (speech <= 0.02) return 0;
      const shapeTime = time * CORE_SPEECH_TIME_SCALE;
      const slowSkew = Math.sin(shapeTime * 0.23 + Math.sin(shapeTime * 0.11) * 2.1);
      const broadNoise =
        Math.sin(meta.nx * 4.7 + meta.ny * 2.9 - meta.nz * 5.3 + shapeTime * (0.42 + meta.speed * 0.11) + meta.phase) * 0.44
        + Math.sin((meta.nx - meta.ny) * 8.9 + meta.nz * 6.7 - shapeTime * (0.73 + meta.speed * 0.17) + meta.speck * 6.283) * 0.31
        + Math.sin(meta.nx * 13.1 + meta.ny * 11.7 + meta.nz * 7.9 + shapeTime * (1.08 + meta.speed * 0.23) + slowSkew) * 0.2;
      let lobeField = 0;
      let lobeWeight = 0;

      for (let i = 0; i < this.deformationLobes.length; i += 1) {
        const lobe = this.deformationLobes[i];
        const dot = meta.nx * lobe.x + meta.ny * lobe.y + meta.nz * lobe.z;
        const influence = Math.pow(smoothstep(1 - lobe.width, 1, dot), 1.55);
        if (influence <= 0.001) continue;
        const drift = Math.sin(shapeTime * lobe.speed + lobe.phase + Math.sin(shapeTime * 0.19 + lobe.skew) * 1.9);
        const chatter = Math.sin(shapeTime * (lobe.speed * 3.7 + 0.53) + lobe.phase * 2.17 + meta.speck * 5.8);
        const lobeBurst = sampleBand(this.speechBursts, lobe.band);
        const lobeSignal = lobe.sign * (0.66 + drift * 0.34)
          + chatter * 0.24
          + lobeBurst * 0.32;
        lobeField += influence * lobe.strength * lobeSignal;
        lobeWeight += influence * lobe.strength;
      }

      const normalizedLobes = lobeWeight > 0 ? lobeField / Math.max(0.35, lobeWeight) : 0;
      const burstBias = clamp(burstLevel, -1, 1) * 0.22;
      const bandBias = (bandLevel - 0.18) * 0.28;
      const field = broadNoise + normalizedLobes * 0.86 + burstBias + bandBias;
      return clamp(field * (0.68 + speech * 0.62), -1, 1);
    }

    updateShellFlow(time) {
      const current = this.current;
      const positions = this.streamPositions;
      const colors = this.streamColors;
      const base = this.displayColor;
      const flowSpeed = 0.06 + current.orbitSpeed * 1.8;
      const shellDisorder = current.disorder * 0.7 + current.shake * 0.9;

      for (let i = 0; i < STREAM_PARTICLE_COUNT; i += 1) {
        const m = this.streamMeta[i];
        const index = i * 3;
        const phase = m.phase + time * flowSpeed * m.speed;
        const y = Math.sin(m.tilt + Math.sin(phase * 0.5 + m.wave) * (0.05 + shellDisorder)) * 0.62;
        const ring = Math.sqrt(Math.max(0.01, 1 - y * y));
        const radius = m.radius + Math.sin(phase * 2.4 + m.wave) * (0.006 + shellDisorder * 0.1);
        const streamLean = Math.sin(time * 0.2 + m.bandOffset * 3.0) * 0.08;

        positions[index] = Math.cos(phase + streamLean) * ring * radius;
        positions[index + 1] = y * radius;
        positions[index + 2] = Math.sin(phase + streamLean) * ring * radius * 0.66;

        const edgePulse = 0.55 + Math.sin(phase * 3.0 + time * 1.4) * 0.24;
        const brightness = clamp(current.brightness * (0.52 + edgePulse) + current.densityBias * m.spark * 0.26, 0.08, 1.28);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.shellFlow.rotation.y = -time * (0.02 + current.orbitSpeed * 0.18);
      this.shellFlow.rotation.z = Math.sin(time * 0.17) * (0.035 + current.disorder * 0.22);
      this.streamMaterial.size = clamp(0.016 + current.glow * 0.03, 0.016, 0.046);
      this.streamMaterial.opacity = clamp((0.3 + current.brightness * 0.45 + current.densityBias * 0.16) * current.opacityScale, 0.18, 0.95);
      this.streamGeometry.attributes.position.needsUpdate = true;
      this.streamGeometry.attributes.color.needsUpdate = true;
    }

    updateOuterHalo(time) {
      const current = this.current;
      const positions = this.haloPositions;
      const colors = this.haloColors;
      const base = this.displayColor;
      const flowSpeed = 0.018 + current.haloSpeed * 0.24;
      const spread = 0.12 + current.haloSpread * 0.32;
      const wave = current.haloWave;
      const haloBurstPower = QUIET_SIGNALS.burstPower;

      for (let i = 0; i < OUTER_HALO_PARTICLE_COUNT; i += 1) {
        const m = this.haloMeta[i];
        const index = i * 3;
        const phase = m.phase + time * flowSpeed * m.speed;
        const ripple = Math.sin(phase * 2.8 + time * (0.8 + current.haloSpeed * 4.2) + m.wave)
          * wave
          * (0.4 + m.depth * 0.9);
        const localBurst = Math.pow(
          0.5 + Math.sin(phase * 7.0 + time * (2.6 + current.haloSpeed * 7.5) + m.wave) * 0.5,
          7.2
        ) * haloBurstPower * m.spark;
        const radius = m.radius
          * (1 + Math.sin(time * 0.18 + m.wave) * 0.012)
          + ripple
          + localBurst * 0.2;
        const vertical = m.lane * spread
          + Math.sin(phase * 2.2 + time * (0.42 + current.haloSpeed * 1.8) + m.wave) * wave
          + localBurst * m.burstSign * 0.14;
        const depthFlatten = 0.06 + m.depth * 0.18;

        positions[index] = Math.cos(phase) * radius;
        positions[index + 1] = vertical;
        positions[index + 2] = Math.sin(phase) * radius * depthFlatten;

        const front = smoothstep(-1, 1, Math.sin(phase));
        const streamPulse = 0.76 + Math.sin(time * (0.75 + m.speed * 0.36) + m.phase) * 0.16;
        const ringEdge = 0.52 + m.band * 0.2 + front * 0.34;
        const brightness = clamp(
          current.haloBrightness * ringEdge * streamPulse
            + m.spark * 0.08,
          0.08,
          1.75
        );
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.outerHaloGroup.rotation.x = 0;
      this.outerHaloGroup.rotation.y = 0;
      this.outerHaloGroup.rotation.z = 0;
      this.haloMaterial.size = clamp(current.haloSize + current.glow * 0.009, 0.018, 0.055);
      this.haloMaterial.opacity = clamp((0.26 + current.haloBrightness * 0.34) * current.opacityScale, 0.28, 0.95);
      this.haloGeometry.attributes.position.needsUpdate = true;
      this.haloGeometry.attributes.color.needsUpdate = true;
    }

    updateParticles(time) {
      const current = this.current;
      const positions = this.particlePositions;
      const colors = this.particleColors;
      const base = this.displayColor;
      const radiusPull = current.radiusPull;
      const orbitSpeed = current.orbitSpeed;
      const disorder = current.disorder;
      const densityBias = current.densityBias;

      for (let i = 0; i < ORBIT_PARTICLE_COUNT; i += 1) {
        const m = this.particleMeta[i];
        const index = i * 3;
        const phase = m.phase + time * orbitSpeed * m.speed;
        const outerBias = 1 + densityBias * m.outer * 0.24;
        const radiusWave = Math.sin(phase * 2.1 + time * m.wobble) * disorder;
        const radius = m.radius * radiusPull * outerBias + radiusWave;
        const verticalWave = Math.cos(phase * 1.7 + time * (0.4 + m.wobble)) * disorder * (0.55 + m.outer);
        const flatten = 0.44 + m.depth;

        positions[index] = Math.cos(phase) * radius;
        positions[index + 1] = m.y * (0.72 + disorder * 1.6) + verticalWave;
        positions[index + 2] = Math.sin(phase) * radius * flatten;

        const pulse = 0.68 + Math.sin(time * (0.7 + m.spark) + m.phase) * 0.12;
        const brightness = clamp((current.brightness + m.spark * 0.18 + densityBias * m.outer * 0.12) * pulse, 0.12, 1.18);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.particles.rotation.y = time * orbitSpeed * 0.12;
      this.particles.rotation.x = Math.sin(time * 0.11) * (0.04 + disorder * 0.8);
      this.particleMaterial.size = current.particleSize;
      this.particleMaterial.opacity = clamp((0.36 + current.brightness * 0.5 - current.shake * 0.4) * current.opacityScale, 0.24, 0.95);
      this.particleGeometry.attributes.position.needsUpdate = true;
      this.particleGeometry.attributes.color.needsUpdate = true;
    }

    dispose() {
      this.disposed = true;
      window.cancelAnimationFrame(this.frameId);
      window.removeEventListener("resize", this.resize);
      if (this.resizeObserver) this.resizeObserver.disconnect();
      this.coreGeometry.dispose();
      this.coreMaterial.dispose();
      this.streamGeometry.dispose();
      this.streamMaterial.dispose();
      this.glowTexture.dispose();
      this.glowMaterial.dispose();
      this.haloGeometry.dispose();
      this.haloMaterial.dispose();
      this.particleGeometry.dispose();
      this.particleMaterial.dispose();
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode) {
        this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
      }
    }
  }

  function setStatus(root, status) {
    root.classList.remove("webgl-loading", "webgl-ready", "webgl-failed");
    root.classList.add(status);
  }

  async function boot() {
    const root = document.getElementById("particleSurface");
    const host = document.getElementById("particleCanvasHost");
    const cueRoot = document.getElementById("particleCue");
    const mainLine = document.getElementById("particleMainLine");
    const resultLine = document.getElementById("particleResultLine");
    const optionsLine = document.getElementById("particleOptionsLine");
    const subLine = document.getElementById("particleSubLine");
    const wakeButton = document.getElementById("particleWakeButton");
    if (!root || !host || !cueRoot || !mainLine || !resultLine || !optionsLine || !subLine || !wakeButton) return;

    let renderer = null;
    let pollId = null;
    let disposed = false;
    let lastSpeakingAt = Number.NEGATIVE_INFINITY;
    const particleCue = createParticleCue({
      root: cueRoot,
      mainLine,
      resultLine,
      optionsLine,
      subLine,
    });
    const wakeButtonController = createWakeButtonController({
      root,
      button: wakeButton,
    });

    function heldSpeaking(rawSpeaking) {
      const now = performance.now();
      if (rawSpeaking) lastSpeakingAt = now;
      return rawSpeaking || now - lastSpeakingAt <= SPEAKING_HOLD_MS;
    }

    async function pollDisplayState() {
      try {
        const state = await fetchJSON("/api/v1/display-state");
        const speaking = heldSpeaking(isSystemSpeaking(state));
        root.dataset.speaking = speaking ? "true" : "false";
        if (renderer) renderer.setSpeaking(speaking);
        particleCue.render(state);
        wakeButtonController.render(state);
      } catch {
        const speaking = heldSpeaking(false);
        root.dataset.speaking = speaking ? "true" : "false";
        if (renderer) renderer.setSpeaking(speaking);
        wakeButtonController.render({ mode: "idle", display_text: "" });
      }
    }

    function startPolling() {
      if (pollId !== null) return;
      pollDisplayState();
      pollId = window.setInterval(pollDisplayState, POLL_MS);
    }

    function stopPolling() {
      if (pollId === null) return;
      window.clearInterval(pollId);
      pollId = null;
    }

    function shutdown() {
      disposed = true;
      stopPolling();
      if (renderer) {
        renderer.dispose();
        renderer = null;
      }
      wakeButtonController.dispose();
    }

    try {
      const THREE = await import(THREE_MODULE_PATH);
      if (disposed) return;
      renderer = new GreenParticleRenderer(host, THREE);
      renderer.start();
      setStatus(root, "webgl-ready");
    } catch {
      setStatus(root, "webgl-failed");
    }
    startPolling();

    window.addEventListener("pagehide", shutdown, { once: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
