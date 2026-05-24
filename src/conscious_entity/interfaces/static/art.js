(function () {
  "use strict";

  const { useEffect, useRef, useState } = React;
  const h = React.createElement;

  const THREE_MODULE_PATH = "/static/vendor/three.module.js";
  const POLL_MS = 1300;
  const TREND_POLL_MS = 900;
  const ORBIT_PARTICLE_COUNT = 1500;
  const CORE_PARTICLE_COUNT = 4200;
  const STREAM_PARTICLE_COUNT = 1800;
  const SPEECH_BAND_COUNT = 512;
  const CORE_RADIUS = 0.74;
  const MIN_BURST_INTERVAL = 0.055;
  const MAX_BURST_INTERVAL = 0.42;
  const TREND_COLOR_MAX_BLEND = 0.28;
  const TREND_SAMPLE_DECAY = 0.68;
  const TREND_DELTA_FLOOR = 0.006;
  const INQUIRY_DISPLAY_WEIGHT = 0.65;

  const DEFAULT_STATE = Object.freeze({
    desperation_pressure: 0.1,
    confusion: 0.4,
    anger: 0.2,
    fatigue_level: 0,
    exposure_pressure: 0.15,
    inquiry: 0.45,
    care_response: 0.2,
    positive_opening: 0.3,
    memory_gravity: 0.2,
  });

  const EMOTION_COLORS = Object.freeze({
    desperate: 0x9f1b58,
    angry: 0xff0000,
    confused: 0x8b5cf6,
    tired: 0x9ca3af,
    ashamed: 0x6f4a2f,
    exposure: 0x6f4a2f,
    curious: 0x35d87a,
    caring: 0x2dd4bf,
    open: 0x60a5fa,
    normal: 0xe6e1d8,
  });

  const TREND_SOURCES = Object.freeze([
    { key: "desperation_pressure", mode: "desperate", gain: 2.7 },
    { key: "anger", mode: "angry", gain: 3.0 },
    { key: "confusion", mode: "confused", gain: 2.35 },
    { key: "fatigue_level", mode: "tired", gain: 1.45 },
    { key: "exposure_pressure", mode: "ashamed", gain: 2.05 },
    { key: "inquiry", mode: "curious", gain: 1.9 },
    { key: "care_response", mode: "caring", gain: 1.65 },
    { key: "positive_opening", mode: "open", gain: 1.55 },
  ]);

  const VISUAL_MODE_CANDIDATES = Object.freeze([
    { mode: "desperate", key: "desperation_pressure" },
    { mode: "angry", key: "anger" },
    { mode: "tired", key: "fatigue_level" },
    { mode: "ashamed", key: "exposure_pressure" },
    { mode: "confused", key: "confusion" },
    { mode: "curious", key: "inquiry" },
    { mode: "caring", key: "care_response" },
    { mode: "open", key: "positive_opening" },
  ]);

  function clamp01(value) {
    const n = Number(value);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  function lerp(left, right, amount) {
    return left + (right - left) * amount;
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
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
    gradient.addColorStop(0, "rgba(255,255,255,0.50)");
    gradient.addColorStop(0.22, "rgba(255,255,255,0.22)");
    gradient.addColorStop(0.54, "rgba(255,255,255,0.075)");
    gradient.addColorStop(0.78, "rgba(255,255,255,0.018)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, size, size);
    const texture = new THREE.CanvasTexture(canvas);
    texture.needsUpdate = true;
    return texture;
  }

  async function fetchJSON(url) {
    const response = await fetch(url);
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function normalizeState(row) {
    const next = {};
    Object.keys(DEFAULT_STATE).forEach((key) => {
      next[key] = clamp01(row && key in row ? row[key] : DEFAULT_STATE[key]);
    });
    return next;
  }

  function displayStateValue(state, key) {
    const value = clamp01(state && key in state ? state[key] : 0);
    if (key === "inquiry") return value * INQUIRY_DISPLAY_WEIGHT;
    return value;
  }

  function buildDisplayState(state) {
    return {
      ...state,
      inquiry: displayStateValue(state, "inquiry"),
    };
  }

  function deriveVisualMode(state) {
    let selectedMode = "normal";
    let selectedValue = 0;
    for (const { mode, key } of VISUAL_MODE_CANDIDATES) {
      const value = displayStateValue(state, key);
      if (value > selectedValue) {
        selectedMode = mode;
        selectedValue = value;
      }
    }
    return selectedMode;
  }

  function normalizeVisualMode(mode) {
    const key = String(mode || "normal").toLowerCase();
    if (key.includes("desperate")) return "desperate";
    if (key.includes("angry")) return "angry";
    if (key.includes("confused") || key.includes("fragment")) return "confused";
    if (key.includes("tired") || key.includes("silent")) return "tired";
    if (key.includes("ashamed") || key.includes("exposure") || key.includes("withdraw")) return "ashamed";
    if (key.includes("curious")) return "curious";
    if (key.includes("caring")) return "caring";
    if (key.includes("open")) return "open";
    return "normal";
  }

  function buildSignals(state, visualMode) {
    const displayState = buildDisplayState(state);
    const mode = normalizeVisualMode(visualMode || deriveVisualMode(state));
    const pressure = Math.max(displayState.desperation_pressure, displayState.anger, displayState.exposure_pressure);
    const calmPull = (displayState.care_response + displayState.positive_opening) * 0.5;
    const fatigue = displayState.fatigue_level;
    return {
      mode,
      color: EMOTION_COLORS[mode] || EMOTION_COLORS.normal,
      desperation: displayState.desperation_pressure,
      anger: displayState.anger,
      confusion: displayState.confusion,
      fatigue,
      inquiry: displayState.inquiry,
      care: displayState.care_response,
      positive: displayState.positive_opening,
      brightness: clamp(0.66 + calmPull * 0.16 - fatigue * 0.28, 0.34, 1),
      orbitSpeed: clamp(0.18 + displayState.inquiry * 0.52 + pressure * 0.22 - fatigue * 0.18, 0.08, 0.9),
      shake: clamp(0.006 + displayState.desperation_pressure * 0.048 + displayState.anger * 0.04 + displayState.confusion * 0.015, 0, 0.105),
      disorder: clamp(0.018 + displayState.confusion * 0.19 + pressure * 0.08 - calmPull * 0.05, 0, 0.28),
      radiusPull: clamp(1.06 + displayState.exposure_pressure * 0.1 + displayState.desperation_pressure * 0.12 - calmPull * 0.18 - displayState.inquiry * 0.06, 0.82, 1.28),
      densityBias: clamp(displayState.memory_gravity, 0, 1),
      breathe: clamp(0.017 + displayState.inquiry * 0.02 + pressure * 0.026 - fatigue * 0.012, 0.008, 0.07),
      breatheSpeed: clamp(0.42 + pressure * 0.58 - fatigue * 0.18, 0.2, 1.08),
      particleSize: clamp(0.018 + displayState.inquiry * 0.009 + displayState.memory_gravity * 0.009, 0.014, 0.038),
      glow: clamp(0.1 + pressure * 0.14 + calmPull * 0.08 - fatigue * 0.05, 0.06, 0.32),
      speechEnergy: clamp(0.34 + displayState.inquiry * 0.14 + pressure * 0.22 + displayState.confusion * 0.1 - fatigue * 0.14, 0.18, 0.82),
      speechRate: clamp(0.72 + displayState.inquiry * 0.42 + pressure * 0.34 + displayState.confusion * 0.16 - fatigue * 0.24, 0.42, 1.55),
      spikeHeight: clamp(0.08 + pressure * 0.18 + displayState.anger * 0.08 + displayState.confusion * 0.07 - calmPull * 0.05 - fatigue * 0.035, 0.055, 0.36),
    };
  }

  class EmotionRenderer {
    constructor(host, THREE) {
      this.host = host;
      this.THREE = THREE;
      this.frameId = 0;
      this.disposed = false;
      this.current = buildSignals(normalizeState(null), "normal");
      this.target = { ...this.current };
      this.currentColor = new THREE.Color(this.current.color);
      this.targetColor = new THREE.Color(this.target.color);
      this.displayColor = new THREE.Color(this.current.color);
      this.trendColor = new THREE.Color(this.current.color);
      this.trendBiases = Object.create(null);
      this.previousTrendState = null;
      this.targetTrendMode = "normal";
      this.targetTrendAmount = 0;
      this.currentTrendAmount = 0;
      this.resize = this.resize.bind(this);
      this.animate = this.animate.bind(this);

      this.scene = new THREE.Scene();
      this.camera = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
      this.camera.position.set(0, 0.02, 5.2);

      this.renderer = new THREE.WebGLRenderer({
        antialias: true,
        alpha: true,
        powerPreference: "high-performance",
      });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      this.renderer.setClearColor(0x030304, 0);
      this.host.appendChild(this.renderer.domElement);

      this.clock = new THREE.Clock();
      this.root = new THREE.Group();
      this.scene.add(this.root);

      this.scene.add(new THREE.AmbientLight(0xffffff, 0.28));
      const keyLight = new THREE.PointLight(0xe6e1d8, 2.4, 9);
      keyLight.position.set(-2.8, 2.1, 3.2);
      this.scene.add(keyLight);
      const rimLight = new THREE.PointLight(0x60a5fa, 1.2, 8);
      rimLight.position.set(2.6, -1.6, 2.4);
      this.scene.add(rimLight);

      this.createOrb();
      this.createParticles();
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
        colors[index] = 0.84;
        colors[index + 1] = 0.82;
        colors[index + 2] = 0.76;
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
        size: 0.022,
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
        color: 0xe6e1d8,
        transparent: true,
        opacity: 0.12,
        depthWrite: false,
        depthTest: false,
        blending: THREE.AdditiveBlending,
      });
      const glow = new THREE.Sprite(this.glowMaterial);
      glow.renderOrder = -2;
      this.root.add(glow);
      this.glow = glow;
    }

    updateSpeechSpectrum(time) {
      const current = this.current;
      const values = this.speechSpectrum;
      const bursts = this.speechBursts;
      const pressure = Math.max(current.desperation, current.anger);
      const calmPull = (current.care + current.positive) * 0.5;
      const rate = current.speechRate;
      const delta = clamp(time - this.lastSpectrumTime || 0.016, 0.008, 0.08);
      this.lastSpectrumTime = time;
      const phrase = 0.58 + Math.pow(0.5 + Math.sin(time * rate * 1.35 + 0.7) * 0.5, 2.2) * 0.42;
      const lowGate = Math.pow(0.5 + Math.sin(time * rate * 5.4 + Math.sin(time * 1.7) * 1.1) * 0.5, 2.6);
      const midGate = Math.pow(0.5 + Math.sin(time * rate * 8.3 + 1.9) * 0.5, 3.8);
      const highGate = Math.pow(0.5 + Math.sin(time * rate * 12.8 + Math.sin(time * 3.1) * 0.7) * 0.5, 5.2);
      const baseline = 0.048 + current.speechEnergy * 0.052;
      const decay = Math.exp(-delta * (7.2 - current.confusion * 1.8 - pressure * 1.4));

      for (let i = 0; i < bursts.length; i += 1) {
        bursts[i] *= decay;
        if (Math.abs(bursts[i]) < 0.01) bursts[i] = 0;
      }

      while (time >= this.nextBurstAt) {
        const burstCount = 1 + Math.floor(randomBetween(0, 2.8 + pressure * 4.2 + current.confusion * 3.4));
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
          const width = 1 + Math.floor(randomBetween(0, 2.2 + current.confusion * 4.5));
          const inward = Math.random() < (0.24 + current.confusion * 0.18 + current.fatigue * 0.08);
          const sign = inward ? -1 : 1;
          const intensity = randomBetween(0.42, 1.25) * (0.88 + pressure * 0.72 + current.confusion * 0.36);

          for (let offset = -width; offset <= width; offset += 1) {
            const bandIndex = centerIndex + offset;
            if (bandIndex < 0 || bandIndex >= bursts.length) continue;
            const falloff = Math.pow(1 - Math.abs(offset) / (width + 1), 2.6);
            bursts[bandIndex] = clamp(bursts[bandIndex] + sign * intensity * falloff, -1.25, 1.45);
          }
        }

        const nextInterval = randomBetween(MIN_BURST_INTERVAL, MAX_BURST_INTERVAL)
          / clamp(0.72 + rate * 0.34 + pressure * 0.32 + current.confusion * 0.22, 0.7, 1.9);
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
          * Math.pow(0.5 + Math.sin(time * rate * (15.5 + pressure * 5.0) + band * 49.0 + Math.sin(time * 3.7 + band * 12.0)) * 0.5, 3.8);
        const grain = Math.sin(i * 12.9898 + time * rate * (17.0 + band * 28.0) + Math.sin(time * 2.0 + band * 11.0));
        const irregular = grain * (0.04 + current.confusion * 0.16 + pressure * 0.06);
        const calmDamping = calmPull * 0.12 + current.fatigue * 0.16;
        const amplitude = baseline
          + current.speechEnergy * phrase * (
            equatorBand * lowPulse * 0.32
            + midBand * midPulse * 0.14
            + poleBand * highPulse * 0.32
          )
          + irregular
          - calmDamping;
        values[i] = clamp(amplitude, 0.026, 0.68);
      }

      return values;
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
        colors[i * 3] = 0.8;
        colors[i * 3 + 1] = 0.78;
        colors[i * 3 + 2] = 0.72;
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
        opacity: 0.82,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      this.particles = new THREE.Points(this.particleGeometry, this.particleMaterial);
      this.scene.add(this.particles);
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
        colors[i * 3] = 0.92;
        colors[i * 3 + 1] = 0.88;
        colors[i * 3 + 2] = 0.78;
      }

      this.streamMeta = meta;
      this.streamPositions = positions;
      this.streamColors = colors;
      this.streamGeometry = new THREE.BufferGeometry();
      this.streamGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      this.streamGeometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
      this.streamMaterial = new THREE.PointsMaterial({
        size: 0.019,
        vertexColors: true,
        transparent: true,
        opacity: 0.72,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      this.shellFlow = new THREE.Points(this.streamGeometry, this.streamMaterial);
      this.root.add(this.shellFlow);
    }

    setTarget(payload) {
      const state = normalizeState(payload && payload.state);
      this.target = buildSignals(state, payload && payload.visualMode);
      this.targetColor.setHex(this.target.color);
    }

    setTrendSample(payload) {
      const state = normalizeState(payload && payload.state ? payload.state : payload);
      if (!this.previousTrendState) {
        this.previousTrendState = { ...state };
        return;
      }

      TREND_SOURCES.forEach(({ key, mode, gain }) => {
        const previous = displayStateValue(this.previousTrendState, key);
        const current = displayStateValue(state, key);
        const delta = current - previous;
        const decayed = (this.trendBiases[mode] || 0) * TREND_SAMPLE_DECAY;
        this.trendBiases[mode] = decayed;
        if (delta > TREND_DELTA_FLOOR) {
          this.trendBiases[mode] = clamp(
            decayed + (delta - TREND_DELTA_FLOOR) * gain,
            0,
            TREND_COLOR_MAX_BLEND
          );
        }
      });

      this.previousTrendState = { ...state };
      let nextMode = "normal";
      let nextAmount = 0;
      TREND_SOURCES.forEach(({ mode }) => {
        const amount = this.trendBiases[mode] || 0;
        if (amount > nextAmount) {
          nextMode = mode;
          nextAmount = amount;
        }
      });

      const baseMode = this.target.mode || "normal";
      if (nextMode === baseMode || nextAmount < 0.015) {
        this.targetTrendMode = "normal";
        this.targetTrendAmount = 0;
        return;
      }

      this.targetTrendMode = nextMode;
      this.targetTrendAmount = clamp(nextAmount, 0, TREND_COLOR_MAX_BLEND);
      this.trendColor.setHex(EMOTION_COLORS[nextMode] || EMOTION_COLORS.normal);
    }

    start() {
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
        if (typeof this.current[key] === "number") {
          this.current[key] = lerp(this.current[key], this.target[key], smooth);
        }
      });
      this.currentColor.lerp(this.targetColor, smooth);
      this.currentTrendAmount = lerp(this.currentTrendAmount, this.targetTrendAmount, smooth);
      this.displayColor.copy(this.currentColor).lerp(this.trendColor, this.currentTrendAmount);

      this.updateOrb(time);
      this.updateParticles(time);
      this.renderer.render(this.scene, this.camera);
      this.frameId = window.requestAnimationFrame(this.animate);
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
      this.root.rotation.y = Math.sin(time * 0.18) * 0.12;
      this.root.rotation.x = Math.cos(time * 0.14) * 0.05;

      this.glowMaterial.color.copy(this.displayColor);
      this.glowMaterial.opacity = clamp(current.glow * 1.35, 0.06, 0.42);
      const glowScale = 3.3 + current.glow * 2.2 + current.shake * 3.2;
      this.glow.scale.set(glowScale, glowScale, 1);
      this.updateCoreSphere(time);
      this.updateShellFlow(time);
    }

    updateCoreSphere(time) {
      const current = this.current;
      const positions = this.corePositions;
      const colors = this.coreColors;
      const base = this.displayColor;
      const pressure = Math.max(current.desperation, current.anger);
      const calmPull = (current.care + current.positive) * 0.5;
      const spectrum = this.updateSpeechSpectrum(time);
      const bursts = this.speechBursts;
      const syllable = Math.pow(0.5 + Math.sin(time * current.speechRate * 6.0) * 0.5, 2.4);

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
        const burstScale = burstSign * burstNeedle * (0.2 + pressure * 0.16 + current.confusion * 0.14)
          * (0.74 + equatorWeight * 0.48 + poleWeight * 1.38);
        const equatorThrob = equatorWeight * current.speechEnergy * (0.012 + syllable * 0.022);
        const polarNeedle = poleWeight * needle * (0.035 + pressure * 0.07 + current.confusion * 0.045);
        const speechSpike = needle * (current.spikeHeight + 0.015) * (0.38 + equatorWeight * 0.32 + poleWeight * 0.74);
        const alwaysRough = (0.012 + m.speck * 0.023)
          * (0.56 + current.speechEnergy)
          * (0.5 + Math.sin(time * (14.0 + m.speed * 7.0) + m.phase * 3.1) * 0.5);
        const surfaceTremor = Math.sin(time * (24 + current.confusion * 18) + m.phase * 3.7)
          * current.shake
          * (0.72 + m.speck + poleWeight * 0.7);
        const instability = Math.sin(time * (3.2 + m.speed) + m.phase + m.speechBand * 11.0)
          * current.disorder
          * (0.012 + poleWeight * 0.04 + equatorWeight * 0.025);
        const shrink = calmPull * 0.045 + current.fatigue * 0.038;
        const radiusScale = clamp(1
          + speechSpike
          + equatorThrob
          + polarNeedle
          + burstScale
          + alwaysRough
          + surfaceTremor
          + instability
          - shrink, 0.52, 1.78);
        const radius = CORE_RADIUS * radiusScale;

        positions[index] = m.nx * radius;
        positions[index + 1] = m.ny * radius;
        positions[index + 2] = m.nz * radius;

        const rim = clamp(0.28 + m.equator * 0.16 + m.pole * 0.2 + needle * 0.38 + burstAbs * 0.78 + pressure * 0.1 - current.fatigue * 0.18, 0.12, 1.55);
        const flicker = 0.76
          + bandLevel * 0.42
          + burstAbs * 0.52
          + Math.sin(time * (7.0 + m.speed * 5.0) + m.phase * 2.2) * (0.04 + current.disorder * 0.16);
        const inwardDim = burstLevel < 0 ? 1 - clamp(burstAbs * 0.36, 0, 0.5) : 1;
        const brightness = clamp((current.brightness * rim * flicker + m.speck * 0.06) * inwardDim, 0.06, 1.62);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.coreSphere.rotation.y = time * (0.05 + current.orbitSpeed * 0.04);
      this.coreSphere.rotation.x = Math.sin(time * 0.23) * (0.035 + current.disorder * 0.12 + current.speechEnergy * 0.025);
      this.coreMaterial.size = clamp(0.015 + current.glow * 0.018 + current.speechEnergy * 0.009 + current.inquiry * 0.003, 0.015, 0.034);
      this.coreMaterial.opacity = clamp(0.54 + current.brightness * 0.34 + current.speechEnergy * 0.12 - current.fatigue * 0.2, 0.34, 0.96);
      this.coreGeometry.attributes.position.needsUpdate = true;
      this.coreGeometry.attributes.color.needsUpdate = true;
    }

    updateShellFlow(time) {
      const current = this.current;
      const positions = this.streamPositions;
      const colors = this.streamColors;
      const base = this.displayColor;
      const flowSpeed = 0.58 + current.orbitSpeed * 1.15 + current.inquiry * 0.22 - current.fatigue * 0.18;
      const shellDisorder = current.disorder * 0.7 + current.shake * 0.9;

      for (let i = 0; i < STREAM_PARTICLE_COUNT; i += 1) {
        const m = this.streamMeta[i];
        const index = i * 3;
        const phase = m.phase + time * flowSpeed * m.speed;
        const y = Math.sin(m.tilt + Math.sin(phase * 0.5 + m.wave) * (0.08 + shellDisorder)) * 0.62;
        const ring = Math.sqrt(Math.max(0.01, 1 - y * y));
        const radius = m.radius + Math.sin(phase * 2.4 + m.wave) * (0.012 + shellDisorder * 0.1);
        const streamLean = Math.sin(time * 0.2 + m.bandOffset * 3.0) * 0.22;

        positions[index] = Math.cos(phase + streamLean) * ring * radius;
        positions[index + 1] = y * radius;
        positions[index + 2] = Math.sin(phase + streamLean) * ring * radius * (0.64 + current.confusion * 0.08);

        const edgePulse = 0.55 + Math.sin(phase * 3.0 + time * 1.4) * 0.24;
        const brightness = clamp(current.brightness * (0.55 + edgePulse) + current.densityBias * m.spark * 0.28, 0.12, 1.35);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.shellFlow.rotation.y = -time * (0.08 + current.orbitSpeed * 0.12);
      this.shellFlow.rotation.z = Math.sin(time * 0.17) * (0.08 + current.disorder * 0.22);
      this.streamMaterial.size = clamp(0.013 + current.glow * 0.025 + current.inquiry * 0.006, 0.012, 0.038);
      this.streamMaterial.opacity = clamp(0.36 + current.brightness * 0.38 + current.densityBias * 0.18 - current.fatigue * 0.14, 0.22, 0.9);
      this.streamGeometry.attributes.position.needsUpdate = true;
      this.streamGeometry.attributes.color.needsUpdate = true;
    }

    updateParticles(time) {
      const current = this.current;
      const positions = this.particlePositions;
      const colors = this.particleColors;
      const base = this.currentColor;
      const radiusPull = current.radiusPull;
      const orbitSpeed = current.orbitSpeed;
      const disorder = current.disorder;
      const densityBias = current.densityBias;

      for (let i = 0; i < ORBIT_PARTICLE_COUNT; i += 1) {
        const m = this.particleMeta[i];
        const index = i * 3;
        const phase = m.phase + time * orbitSpeed * m.speed;
        const memoryOuter = 1 + densityBias * m.outer * 0.28;
        const radiusWave = Math.sin(phase * 2.1 + time * m.wobble) * disorder;
        const radius = m.radius * radiusPull * memoryOuter + radiusWave;
        const verticalWave = Math.cos(phase * 1.7 + time * (0.4 + m.wobble)) * disorder * (0.55 + m.outer);
        const flatten = 0.44 + m.depth + current.confusion * 0.1;

        positions[index] = Math.cos(phase) * radius;
        positions[index + 1] = m.y * (0.72 + disorder * 1.6) + verticalWave;
        positions[index + 2] = Math.sin(phase) * radius * flatten;

        const pulse = 0.68 + Math.sin(time * (0.7 + m.spark) + m.phase) * 0.12;
        const brightness = clamp((current.brightness + m.spark * 0.22 + densityBias * m.outer * 0.14) * pulse, 0.18, 1.25);
        colors[index] = clamp(base.r * brightness, 0, 1);
        colors[index + 1] = clamp(base.g * brightness, 0, 1);
        colors[index + 2] = clamp(base.b * brightness, 0, 1);
      }

      this.particles.rotation.y = time * orbitSpeed * 0.1;
      this.particles.rotation.x = Math.sin(time * 0.11) * (0.1 + disorder * 0.8);
      this.particleMaterial.size = current.particleSize;
      this.particleMaterial.opacity = clamp(0.48 + current.brightness * 0.42 - current.shake * 0.8, 0.28, 0.9);
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
      this.particleGeometry.dispose();
      this.particleMaterial.dispose();
      this.renderer.dispose();
      if (this.renderer.domElement.parentNode) {
        this.renderer.domElement.parentNode.removeChild(this.renderer.domElement);
      }
    }
  }

  async function readSurfacePayload() {
    const state = await fetchJSON("/api/v1/state").catch(() => null);
    const normalized = normalizeState(state);
    return {
      state: normalized,
      visualMode: state ? deriveVisualMode(normalized) : "normal",
    };
  }

  function AmbientFallback() {
    return h("div", { className: "ambient-field", "aria-hidden": "true" },
      h("div", { className: "fallback-orb" }),
      h("div", { className: "fallback-ring" }),
      h("div", { className: "fallback-ring" }),
      h("div", { className: "fallback-noise" }),
    );
  }

  function ArtSurface() {
    const hostRef = useRef(null);
    const rendererRef = useRef(null);
    const [status, setStatus] = useState("webgl-loading");

    useEffect(() => {
      let cancelled = false;

      import(THREE_MODULE_PATH)
        .then((THREE) => {
          if (cancelled || !hostRef.current) return;
          const renderer = new EmotionRenderer(hostRef.current, THREE);
          rendererRef.current = renderer;
          renderer.start();
          setStatus("webgl-ready");
          readSurfacePayload()
            .then((payload) => renderer.setTarget(payload))
            .catch(() => {});
        })
        .catch(() => {
          if (!cancelled) setStatus("webgl-failed");
        });

      return () => {
        cancelled = true;
        if (rendererRef.current) {
          rendererRef.current.dispose();
          rendererRef.current = null;
        }
      };
    }, []);

    useEffect(() => {
      let cancelled = false;

      async function poll() {
        const renderer = rendererRef.current;
        if (!renderer) return;
        try {
          const payload = await readSurfacePayload();
          if (!cancelled) renderer.setTarget(payload);
        } catch {
          if (!cancelled) renderer.setTarget({ state: DEFAULT_STATE, visualMode: "normal" });
        }
      }

      poll();
      const id = window.setInterval(poll, POLL_MS);
      return () => {
        cancelled = true;
        window.clearInterval(id);
      };
    }, []);

    useEffect(() => {
      let cancelled = false;

      async function pollTrend() {
        const renderer = rendererRef.current;
        if (!renderer) return;
        try {
          const state = normalizeState(await fetchJSON("/api/v1/state"));
          if (!cancelled) renderer.setTrendSample(state);
        } catch {
          // Keep the current trend color; the main surface poll still has its fallback.
        }
      }

      pollTrend();
      const id = window.setInterval(pollTrend, TREND_POLL_MS);
      return () => {
        cancelled = true;
        window.clearInterval(id);
      };
    }, []);

    return h("section", { className: `art-shell ${status}` },
      h(AmbientFallback),
      h("div", { ref: hostRef, className: "art-canvas-host", "aria-hidden": "true" }),
    );
  }

  ReactDOM.createRoot(document.getElementById("art-root")).render(h(ArtSurface));
})();
