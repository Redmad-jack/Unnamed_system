from __future__ import annotations

import asyncio
import base64
import inspect
import json
from pathlib import Path

from fastapi.testclient import TestClient

from have_some_ai.interfaces import api as have_some_ai_api
from have_some_ai.conversation import ConversationOrchestrator
from have_some_ai.doubao.asr_protocol import ASRTranscriptEvent
from have_some_ai.doubao.tts_protocol import (
    TTSEvent,
    TTS_SESSION_CANCELED,
    TTS_SESSION_FINISHED,
    TTS_SESSION_STARTED,
    TTS_RESPONSE,
)
from have_some_ai.interfaces.api import app
from have_some_ai.voice import ClaudeRubricInterpreter, RubricInterpretation


class _FakeHTTPResponse:
    def __init__(self, payload=None, status_code: int = 200, content: bytes = b""):
        self._payload = payload
        self.status_code = status_code
        self.content = content

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHTTPClient:
    posts = []
    transcription_payload = {"text": "我选 A", "language": "zh"}

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def post(self, url, headers=None, json=None, data=None, files=None):
        self.__class__.posts.append({
            "url": url,
            "headers": headers,
            "json": json,
            "data": data,
            "files": files,
        })
        if "audio/speech" in url:
            return _FakeHTTPResponse(content=b"fake-mp3")
        if "audio/transcriptions" in url:
            return _FakeHTTPResponse(self.__class__.transcription_payload)
        return _FakeHTTPResponse({
            "id": "sess_123",
            "client_secret": {"value": "ephemeral-token"},
            "url": url,
            "headers": headers,
            "request_json": json,
        })


def test_display_page_returns_html(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.get("/display")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="stage"' in response.text
    assert 'id="promptCueCard"' in response.text


def test_particle_display_page_returns_html(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.get("/particle-display")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'id="particleSurface"' in response.text
    assert 'id="particleCanvasHost"' in response.text
    assert 'id="particleCue"' in response.text
    assert 'id="particleMainLine"' in response.text
    assert 'id="particleOptionsLine"' in response.text
    assert 'id="particleResultLine"' in response.text
    assert 'id="particleSubLine"' in response.text
    assert 'class="fallback-halo"' in response.text
    assert "/particle-display-assets/particle-display.css" in response.text
    assert "/particle-display-assets/particle-display.js" in response.text


def test_display_asset_serves_avatar_film_texture(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.get("/display-assets/avatar-film-texture.png")
        overlay = client.get("/display-assets/avatar-film-overlay.png")
        prompt_decoration = client.get("/display-assets/amhand.png")
        missing = client.get("/display-assets/missing.png")

    assert response.status_code == 200
    assert "image/png" in response.headers["content-type"]
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert overlay.status_code == 200
    assert "image/png" in overlay.headers["content-type"]
    assert overlay.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert prompt_decoration.status_code == 200
    assert "image/png" in prompt_decoration.headers["content-type"]
    assert prompt_decoration.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert missing.status_code == 404


def test_particle_display_assets_are_local_and_whitelisted(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        css = client.get("/particle-display-assets/particle-display.css")
        js = client.get("/particle-display-assets/particle-display.js")
        three = client.get("/particle-display-assets/vendor/three.module.js")
        missing = client.get("/particle-display-assets/vendor/react.production.min.js")

    assert css.status_code == 200
    assert "particle-shell" in css.text
    assert js.status_code == 200
    assert "GreenParticleRenderer" in js.text
    assert "CanvasTexture" in js.text
    assert "createOuterHalo" in js.text
    assert "updateOuterHalo" in js.text
    assert three.status_code == 200
    assert "WebGLRenderer" in three.text
    assert missing.status_code == 404


def test_display_state_initial_idle(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.get("/api/v1/display-state")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "idle"
    assert payload["display_text"] == ""
    assert payload["food_name"] is None
    assert payload["food_subtitle"] is None
    assert payload["robot_active"] is False
    assert payload["avatar_greeting"] is False
    assert payload["avatar_system_speaking"] is False
    assert payload["avatar_audience_speaking"] is False
    assert isinstance(payload["updated_at"], str)


def test_display_state_post_updates_memory_state(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/display-state",
            json={
                "mode": "robot_speaking",
                "display_text": "你好。",
                "robot_active": True,
                "avatar_greeting": True,
                "avatar_system_speaking": True,
                "avatar_audience_speaking": False,
            },
        )
        after = client.get("/api/v1/display-state")

    payload = response.json()
    assert response.status_code == 200
    assert payload["mode"] == "robot_speaking"
    assert payload["display_text"] == "你好。"
    assert payload["robot_active"] is True
    assert payload["avatar_greeting"] is True
    assert payload["avatar_system_speaking"] is True
    assert payload["avatar_audience_speaking"] is False
    assert after.json() == payload


def test_display_state_rejects_invalid_mode_without_polluting_state(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        before = client.get("/api/v1/display-state").json()
        response = client.post("/api/v1/display-state", json={"mode": "working"})
        after = client.get("/api/v1/display-state").json()

    assert response.status_code == 400
    assert after == before


def test_display_state_requires_boolean_robot_active(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/display-state",
            json={"robot_active": "true"},
        )

    assert response.status_code == 422


def test_display_state_truncates_long_display_text(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/display-state",
            json={"display_text": "a" * 900},
        )

    assert response.status_code == 200
    assert response.json()["display_text"] == "a" * 800


def test_display_state_post_does_not_write_business_database(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        before = client.get("/api/v1/export").json()
        response = client.post(
            "/api/v1/display-state",
            json={
                "mode": "result",
                "display_text": "请取餐。",
                "food_name": "Ai Miao Soup",
                "food_subtitle": "今天的结果。",
                "robot_active": False,
            },
        )
        after = client.get("/api/v1/export").json()

    assert response.status_code == 200
    assert after == before


def test_display_html_does_not_include_control_or_voice_entrypoints():
    source = Path("src/have_some_ai/interfaces/static/display.html").read_text()

    forbidden = [
        "getUserMedia",
        "navigator.mediaDevices",
        "conversation-stream",
        "WebSocket",
        "PATCH",
        "staff-queue",
        "queueStatus",
        "/api/v1/participants",
        "conversation-turn",
        "/answers",
        "/assign",
        "/observations",
        "/speech",
        "voice-audio",
        "conversation-audio",
        "ASR",
        "TTS",
        "麦克风",
        "录音中",
        "debug",
        "database",
        "queue",
        "participant id",
        "participant label",
        "工作人员",
        "管理员",
        "<button",
    ]
    for item in forbidden:
        assert item not in source


def test_particle_display_only_uses_read_only_display_state():
    paths = [
        Path("src/have_some_ai/interfaces/static/particle-display.html"),
        Path("src/have_some_ai/interfaces/static/particle-display.css"),
        Path("src/have_some_ai/interfaces/static/particle-display.js"),
    ]
    source = "\n".join(path.read_text() for path in paths)

    assert 'fetchJSON("/api/v1/display-state")' in source
    for item in [
        "getUserMedia",
        "navigator.mediaDevices",
        "conversation-stream",
        "WebSocket",
        "PATCH",
        "POST",
        "PUT",
        "DELETE",
        "staff-queue",
        "/api/v1/participants",
        "conversation-turn",
        "/answers",
        "/assign",
        "/observations",
        "/speech",
        "voice-audio",
        "conversation-audio",
        "dashboard",
        "debug",
        "prompt",
        "memory",
        "database",
        "queue",
        "<button",
    ]:
        assert item not in source


def test_particle_display_maps_speaking_state_without_emotion_palette():
    source = Path("src/have_some_ai/interfaces/static/particle-display.js").read_text()

    assert "function isSystemSpeaking" in source
    assert "avatar_system_speaking" in source
    assert "robot_speaking" in source
    assert "robot_active" in source
    assert "SPEAKING_SIGNALS" in source
    assert "QUIET_SIGNALS" in source
    assert "const SPEAKING_MIN_RADIUS_SCALE = 2 / 3" in source
    assert "const SPEAKING_MAX_RADIUS_SCALE = 5 / 3" in source
    assert "const CORE_SPEECH_TIME_SCALE = 0.5" in source
    assert "function randomUnitVector" in source
    assert "createDeformationLobes" in source
    assert "largeDeformationField" in source
    assert "function createParticleCue" in source
    assert "function splitDisplayText" in source
    assert 'mode !== "question" || lines.length < 2' in source
    assert 'normalizedMode === "result"' in source
    assert 'display_text: displayText = ""' in source
    assert 'food_name: foodName = ""' in source
    assert 'food_subtitle: foodSubtitle = ""' in source
    for quiet_locked_signal in [
        "brightness",
        "orbitSpeed",
        "shake",
        "disorder",
        "radiusPull",
        "densityBias",
        "breathe",
        "breatheSpeed",
        "particleSize",
        "glow",
        "opacityScale",
        "haloSpeed",
        "haloBrightness",
        "haloSpread",
        "haloWave",
        "haloSize",
    ]:
        assert f"{quiet_locked_signal}: QUIET_SIGNALS.{quiet_locked_signal}" in source
    assert "this.displayColor.lerp(this.quietColor, 0.6)" in source
    assert "this.glowMaterial.opacity = clamp(current.glow * 0.95" in source
    assert "this.outerHaloGroup.rotation.x = 0;" in source
    assert "this.outerHaloGroup.rotation.y = 0;" in source
    assert "this.outerHaloGroup.rotation.z = 0;" in source
    assert "current.speaking * localBurst" not in source
    assert "current.speaking * 0.22" not in source
    assert "current.speaking * 0.026" not in source
    assert "const POLL_MS = 250" in source
    assert "const SPEAKING_HOLD_MS = 1200" in source
    assert "haloSpeed" in source
    assert "createOuterHalo" in source
    assert "updateOuterHalo" in source
    for stranger_emotion in [
        "desperate",
        "angry",
        "confused",
        "ashamed",
        "curious",
        "caring",
        "positive_opening",
        "fatigue_level",
        "EMOTION_COLORS",
    ]:
        assert stranger_emotion not in source


def test_particle_display_text_overlay_matches_display_text_scale_without_frame():
    particle_html = Path("src/have_some_ai/interfaces/static/particle-display.html").read_text()
    particle_css = Path("src/have_some_ai/interfaces/static/particle-display.css").read_text()

    assert 'class="particle-text-plane"' in particle_html
    assert 'class="particle-cue"' in particle_html
    assert "bottom: clamp(54px, 8.2vh, 108px)" in particle_css
    assert "width: min(900px, calc(100vw - 56px))" in particle_css
    assert "width: min(820px, 100%)" in particle_css
    assert "font-size: clamp(15.4px, 1.68vw, 26.6px)" in particle_css
    assert "font-size: clamp(10.5px, 0.896vw, 14.7px)" in particle_css
    assert "font-size: clamp(19.6px, 2.24vw, 36.4px)" in particle_css
    assert "color: #fff" in particle_css
    assert "text-shadow: none" in particle_css

    framed_terms = [
        "border:",
        "border-radius",
        "backdrop-filter",
        "-webkit-backdrop-filter",
        "box-shadow",
        "background:",
    ]
    cue_block = particle_css[
        particle_css.index(".particle-cue {"):particle_css.index(".particle-cue[hidden]")
    ]
    for term in framed_terms:
        assert term not in cue_block


def test_display_state_post_does_not_call_business_or_voice_services():
    source = inspect.getsource(have_some_ai_api.update_display_state)

    forbidden = [
        "_service(",
        "_conversation(",
        "_file_stt(",
        "_tts(",
        "conn.execute",
        "sqlite",
        "ConversationOrchestrator",
        "MealService",
        "assign_food",
        "conversation_stream",
        "staff_queue",
        "Doubao",
        "OpenAI",
    ]
    for item in forbidden:
        assert item not in source


def test_display_html_uses_prompt_cue_card_component():
    source = Path("src/have_some_ai/interfaces/static/display.html").read_text()

    assert "function PromptCueCard" in source
    assert 'class="prompt-cue-card"' in source
    assert 'id="promptCueDecoration"' in source
    assert "/display-assets/amhand.png" in source
    assert "showDecoration: true" in source
    assert "decorationVariant: 'corner'" in source
    assert 'data-decoration-variant="corner"' in source
    assert 'class="options-line"' in source
    assert ".prompt-cue-card[hidden]" in source
    assert "root.hidden = true" in source
    assert "root.hidden = false" in source
    assert "document.createElement('p')" in source
    assert "prompt-cue-card-enter" in source


def test_display_asset_whitelist_includes_prompt_decoration():
    source = inspect.getsource(have_some_ai_api.display_asset)

    assert '"amhand.png"' in source


def test_control_page_display_state_sync_uses_single_helper():
    source = Path("src/have_some_ai/interfaces/static/index.html").read_text()

    assert "async function updateDisplayState(payload)" in source
    assert source.count("fetch('/api/v1/display-state'") == 1
    assert "display state sync failed" in source
    assert "function createDisplayAvatarStateAdapter" in source
    assert "function withDisplayAvatarState" in source
    assert "function resolveDisplayAvatarState" in source
    assert "isGreetingLanguageSelect" in source
    assert "isGreeting: options.isGreeting" in source
    assert "isSystemSpeaking" in source
    assert "isAudienceSpeaking" in source
    assert "DISPLAY_AVATAR_DEBUG" in source
    assert "avatarDebug" in source
    assert "syncDisplayRobotSpeaking" in source
    assert "syncDisplayResult" in source
    assert "function displayChoiceText" in source
    assert "function syncDisplayTtsStart" in source
    assert "function syncDisplayCurrentTtsSpeaking" in source
    assert "function shouldShowQuestionDuringTts" in source
    assert "deferReplyDisplay: useDoubaoStream" in source
    assert "if (deferReplyDisplay && doubaoMicMutedForTts)" in source
    assert "DISPLAY_SPEECH_FALLBACK_MS" in source
    assert "function scheduleDisplayAfterSpeech" in source
    assert "function scheduleDisplayAudienceResume" in source
    assert "const queuedDisplayMs = Math.max(900, doubaoQueuedPlaybackMs() + 300)" in source
    assert "scheduleDisplayAfterSpeech(queuedDisplayMs)" in source
    assert "scheduleDisplayAudienceResume(queuedDisplayMs + 50)" in source
    assert "DISPLAY_FORMAL_ANSWER_GREETING_MS" in source
    assert "function isAcceptedFormalAnswerResult" in source
    assert "function syncDisplayFormalAnswerGreeting" in source
    assert "function shouldKeepDisplayFormalAnswerGreeting" in source
    assert "result?.interpretation?.status === 'accepted'" in source
    assert "Boolean(result?.interpretation?.choice)" in source
    assert "formal_answer_greeting_${result.answered_count}" in source
    assert "syncDisplayFormalAnswerGreeting(result);" in source
    assert "const keepFormalAnswerGreeting = shouldKeepDisplayFormalAnswerGreeting();" in source
    assert "syncDisplayQuestion(true, { isGreeting: keepFormalAnswerGreeting })" in source
    assert "setDisplayAudienceSpeaking(true)" in source
    assert "avatar_greeting" in source
    assert "avatar_system_speaking" in source
    assert "avatar_audience_speaking" in source
    assert ".join('\\n')" in source
    assert "const DISPLAY_WAKE_TEXT = '按按钮叫醒我\\nPress the button to wake me'" in source
    assert "function syncDisplayStandby()" in source
    assert "function scheduleDisplayStandby" in source
    assert "syncDisplayStandby();" in source
    assert "syncDisplayIdle();" in source
    assert "scheduleDisplayStandby();" in source


def test_control_page_hardware_button_reuses_new_participant_flow():
    source = Path("src/have_some_ai/interfaces/static/index.html").read_text()
    sketch = Path(
        "hardware/arduino/have_some_ai_new_button/have_some_ai_new_button.ino"
    ).read_text()

    assert 'id="newParticipantBtn"' in source
    assert 'id="hardwareButtonConnectBtn"' in source
    assert 'id="hardwareButtonState"' in source
    assert "navigator.serial.requestPort()" in source
    assert "const HARDWARE_BUTTON = {" in source
    assert "newCommand: 'NEW'" in source
    assert "function handleHardwareButtonLine" in source
    assert "function triggerHardwareNewParticipant" in source
    assert "await newParticipant();" in source
    assert source.count("fetch('/api/v1/display-state'") == 1

    assert "const int BUTTON_PIN = 2;" in sketch
    assert "Serial.begin(BAUD_RATE);" in sketch
    assert 'Serial.println("NEW");' in sketch
    assert 'Serial.print("READY HAVE_SOME_AI_NEW_BUTTON' in sketch


def test_display_html_has_avatar_animation_state_controller():
    source = Path("src/have_some_ai/interfaces/static/display.html").read_text()
    avatar_stage = source[
        source.index('id="avatarStage"') : source.index('<section class="text-plane"')
    ]

    assert "AVATAR_STATES" in source
    assert "idle_breathing" in source
    assert "greeting_wave" in source
    assert "system_speaking" in source
    assert "audience_speaking" in source
    assert 'class="silhouette-stage avatar-state-idle-breathing"' in source
    assert 'data-state="idle_breathing"' in source
    assert "function createSilhouetteStage" in source
    assert "createAvatarAnimationController" in source
    assert "--film-opacity" in source
    assert "--film-blur" in source
    assert "--film-noise-opacity" in source
    assert "--film-texture-opacity" in source
    assert "--film-texture-overlay-opacity" in source
    assert "--texture-tremble-x" in source
    assert "backdrop-filter" in source
    assert "@supports not" in source
    for part in [
        "avatar-head",
        "avatar-torso",
        "avatar-left-upper-arm",
        "avatar-left-forearm",
        "avatar-left-hand",
        "avatar-right-upper-arm",
        "avatar-right-forearm",
        "avatar-right-hand",
        "membrane-texture",
        "membrane-texture-overlay",
        "membrane-stress",
    ]:
        assert part in avatar_stage
    assert "avatar-greeting-hand-wave" in source
    assert "avatar-greeting-film-wave" in source
    assert "avatar-system-fake-walk" in source
    assert 'data-state="system_speaking"] .presence' in source
    for system_walk_hook in [
        "--walk-x",
        "--walk-face",
        "--presence-motion-y",
        "avatar-system-left-upper-arm-walk",
        "avatar-system-right-upper-arm-walk",
        "avatar-system-left-leg-step",
        "avatar-system-right-leg-step",
    ]:
        assert system_walk_hook in source
    assert "avatar-presence-breathe" in source
    assert "avatar-torso-breathe" in source
    assert "avatar-head-breathe" in source
    assert "--presence-breath-duration" in source
    assert "animationend" in source
    assert "greetingReplay" in source
    for removed_animation_hook in [
        "avatar-mouth-shadow",
        "avatar-mouth-opening",
        "membrane-dent-left",
        "membrane-dent-right",
        "membrane-strain-lines-left",
        "membrane-strain-lines-right",
        "avatar-tear-left-hand",
        "avatar-tear-right-hand",
        "--mouth-open",
        "--film-press",
        "--left-dent-pressure",
        "function startMouthMotion",
        "function stopMouthMotion",
        "function startFilmPressure",
        "function stopFilmPressure",
        "function setFilmPressureFrame",
        "window.setInterval(setMouthFrame",
        "clearInterval(mouthTimer)",
        "clearTimeout(pressureTimer)",
    ]:
        assert removed_animation_hook not in source
    assert "@property --silhouette-scale" in source
    assert "contain: layout paint" in source
    assert "will-change: transform, opacity" in source
    assert "top 320ms cubic-bezier" in source
    assert "top 280ms cubic-bezier" in source
    assert "root.classList.remove(...classes)" in source
    assert source.index("if (includeGreeting && greetingActive)") < source.index("if (inputs.systemSpeaking)")
    assert "event.animationName !== 'avatar-greeting-hand-wave'" in source
    assert "!event.target.classList.contains('avatar-right-hand')" in source
    assert "function startRefreshLoop" in source
    assert "function stopRefreshLoop" in source
    assert "function pauseAvatarRuntime" in source
    assert "visibilitychange" in source
    assert "pagehide" in source
    assert "pageshow" in source
    assert "avatarController.destroy()" in source
    assert "lastGreetingInput = false" in source
    assert "lastGreetingKey = null" in source
    assert "0% { transform: translate3d(2.8%, 3.8%, 0) rotate(-16deg); }" in source
    assert "function createAvatarDevelopmentPanel" in source
    assert "function isAvatarDevelopmentPanelAllowed" in source
    assert "function setManualAvatarState" in source
    assert "avatarPanel" in source
    assert "allowedHosts" in source
    assert "document.createElement('button')" in source
    assert "latestAvatarBusinessInputs" in source
    assert "latestAvatarAppliedInputs" in source
    assert avatar_stage.index("silhouette-glow") < avatar_stage.index("silhouette-body")
    assert avatar_stage.index("silhouette-body") < avatar_stage.index("membrane-main")
    assert avatar_stage.index("membrane-main") < avatar_stage.index("membrane-texture")
    assert avatar_stage.index("membrane-texture") < avatar_stage.index("membrane-texture-overlay")
    assert avatar_stage.index("membrane-texture-overlay") < avatar_stage.index("membrane-surface")
    assert avatar_stage.index("membrane-surface") < avatar_stage.index("membrane-stress")


def test_voice_config_keeps_file_stt_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "aihubmix")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "file")

    with TestClient(app) as client:
        response = client.get("/api/v1/voice-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "aihubmix"
    assert payload["stt_mode"] == "file"
    assert payload["file_stt_available"] is True
    assert "realtime_available" not in payload
    assert "conversation_realtime_available" not in payload
    assert "realtime_transport" not in payload


def test_voice_config_exposes_doubao_stream_pcm_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "shared-key")

    with TestClient(app) as client:
        response = client.get("/api/v1/voice-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "doubao"
    assert payload["stt_mode"] == "asr_tts_stream"
    assert payload["conversation_stream_available"] is True
    assert "conversation_realtime_available" not in payload
    assert "realtime_transport" not in payload
    assert payload["input_audio_format"] == "pcm_s16le"
    assert payload["input_sample_rate"] == 16000
    assert payload["output_audio_format"] == "pcm_s16le"
    assert payload["output_sample_rate"] == 24000
    assert payload["provider_capabilities"]["structured_answer"] is False
    assert payload["provider_capabilities"]["credentials_configured"] is True
    assert payload["provider_capabilities"]["asr_credentials_configured"] is True
    assert payload["provider_capabilities"]["tts_credentials_configured"] is True
    assert payload["provider_capabilities"]["tts_resource_id"] == "seed-icl-2.0"
    assert payload["provider_capabilities"]["speaker"] == "S_ud9II0522"


def test_voice_config_marks_doubao_credentials_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "")
    monkeypatch.setenv("DOUBAO_ASR_API_KEY", "")
    monkeypatch.setenv("DOUBAO_TTS_API_KEY", "")

    with TestClient(app) as client:
        response = client.get("/api/v1/voice-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_stream_available"] is True
    assert payload["provider_capabilities"]["credentials_configured"] is False
    assert payload["provider_capabilities"]["asr_credentials_configured"] is False
    assert payload["provider_capabilities"]["tts_credentials_configured"] is False


def test_voice_config_accepts_separate_doubao_asr_tts_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
    monkeypatch.setenv("DOUBAO_ASR_API_KEY", "asr-key")
    monkeypatch.setenv("DOUBAO_TTS_API_KEY", "tts-key")

    with TestClient(app) as client:
        response = client.get("/api/v1/voice-config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_capabilities"]["credentials_configured"] is True
    assert payload["provider_capabilities"]["asr_credentials_configured"] is True
    assert payload["provider_capabilities"]["tts_credentials_configured"] is True


def test_file_stt_posts_aihubmix_transcription_with_language(monkeypatch):
    from have_some_ai import openai_file_stt

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "好的", "language": "zh"}
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODEL", "whisper-large-v3")
    monkeypatch.setenv("HAVE_SOME_AI_STT_LANGUAGE", "zh")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)

    result = openai_file_stt.OpenAIFileTranscription().transcribe(
        b"fake-audio",
        mime_type="audio/webm;codecs=opus",
        duration_ms=1200,
    )

    post = _FakeHTTPClient.posts[-1]
    assert result.text == "好的"
    assert post["url"] == "https://aihubmix.com/v1/audio/transcriptions"
    assert post["data"]["model"] == "whisper-large-v3"
    assert post["data"]["language"] == "zh"
    assert post["files"]["file"][0] == "answer.webm"
    assert post["files"]["file"][2] == "audio/webm"


def test_file_stt_omits_language_when_env_empty(monkeypatch):
    from have_some_ai import openai_file_stt

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.delenv("HAVE_SOME_AI_STT_LANGUAGE", raising=False)
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)

    openai_file_stt.OpenAIFileTranscription().transcribe(
        b"fake-audio",
        mime_type="audio/mp4",
    )

    assert "language" not in _FakeHTTPClient.posts[-1]["data"]


def test_audio_mime_type_to_filename_mapping():
    from have_some_ai.openai_file_stt import filename_for_mime_type

    assert filename_for_mime_type("audio/webm") == "answer.webm"
    assert filename_for_mime_type("audio/webm;codecs=opus") == "answer.webm"
    assert filename_for_mime_type("audio/mp4") == "answer.mp4"
    assert filename_for_mime_type("audio/mpeg") == "answer.mp3"
    assert filename_for_mime_type("audio/wav") == "answer.wav"


def test_question_speech_requires_voice_key(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/speech"
        )

    assert response.status_code == 400
    assert "HAVE_SOME_AI_VOICE_API_KEY" in response.json()["detail"]


def test_question_speech_returns_audio(monkeypatch, tmp_path):
    from have_some_ai import openai_tts

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/speech"
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"fake-mp3"
    assert _FakeHTTPClient.posts[-1]["url"] == "https://voice-provider.example/v1/audio/speech"
    assert _FakeHTTPClient.posts[-1]["json"]["model"] == "gpt-4o-mini-tts"
    assert "先回答我两个问题" in _FakeHTTPClient.posts[-1]["json"]["input"]
    assert "You can answer A, B, or C" not in _FakeHTTPClient.posts[-1]["json"]["input"]


def test_thank_you_speech_returns_audio(monkeypatch, tmp_path):
    from have_some_ai import openai_tts

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)

    with TestClient(app) as client:
        response = client.post("/api/v1/speech/thanks")

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"fake-mp3"
    assert _FakeHTTPClient.posts[-1]["url"] == "https://voice-provider.example/v1/audio/speech"
    assert _FakeHTTPClient.posts[-1]["json"]["input"] == "Thank you. 谢谢。"


def test_question_speech_rejects_not_drawn_question(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(f"/api/v1/participants/{participant['id']}/questionnaire/start")
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/not_drawn/speech"
        )

    assert response.status_code == 400
    assert "not drawn" in response.json()["detail"]


def test_voice_audio_rejects_unsupported_mime_type(monkeypatch, tmp_path):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/voice-audio",
            json={
                "audio_base64": base64.b64encode(b"fake").decode("ascii"),
                "mime_type": "audio/ogg",
                "duration_ms": 1000,
                "attempt_id": "attempt-unsupported",
            },
        )

    assert response.status_code == 400
    assert "Unsupported audio MIME type" in response.json()["detail"]


def test_voice_answer_api_uses_mocked_claude_and_assigns_when_complete(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    results = [
        RubricInterpretation("A", 0.9, "清楚肯定。", "Clearly yes.", "zh", {}),
        RubricInterpretation("A", 0.9, "清楚肯定。", "Clearly yes.", "en", {}),
    ]

    def fake_interpret(self, **_kwargs):
        return results.pop(0)

    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draws = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"]
        final_response = None
        for draw in draws:
            final_response = client.post(
                f"/api/v1/participants/{participant['id']}/voice-answers",
                json={
                    "question_id": draw["question_id"],
                    "transcript": "yes 好的",
                    "detected_language": "mixed",
                },
            )

        detail = client.get(f"/api/v1/participants/{participant['id']}").json()
        exported = client.get("/api/v1/export").json()

    assert final_response is not None
    assert final_response.status_code == 200
    assert "assignment" in final_response.json()
    assert len(detail["voice_interpretations"]) == 2
    assert len(exported["meal_voice_answer_interpretations"]) == 2


def test_voice_audio_duplicate_attempt_does_not_repeat_stt_or_claude(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我选 A", "language": "zh"}
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    claude_calls = {"count": 0}

    def fake_interpret(self, **_kwargs):
        claude_calls["count"] += 1
        return RubricInterpretation("A", 0.9, "清楚选择 A。", "Clear A.", "zh", {})

    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    payload = {
        "audio_base64": base64.b64encode(b"fake").decode("ascii"),
        "mime_type": "audio/webm;codecs=opus",
        "duration_ms": 1200,
        "attempt_id": "same-attempt",
    }
    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        path = f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/voice-audio"
        first = client.post(path, json=payload).json()
        second = client.post(path, json=payload).json()
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    transcription_posts = [
        post for post in _FakeHTTPClient.posts if "audio/transcriptions" in post["url"]
    ]
    assert first["interpretation_id"] == second["interpretation_id"]
    assert len(transcription_posts) == 1
    assert claude_calls["count"] == 1
    assert len(detail["voice_interpretations"]) == 1
    assert len(detail["answers"]) == 1


def test_voice_audio_unclear_does_not_store_answer(monkeypatch, tmp_path):
    from have_some_ai import openai_file_stt

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "", "language": "zh"}
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)

    def fail_if_called(self, **_kwargs):
        raise AssertionError("Claude should not be called for empty STT text")

    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fail_if_called)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/voice-audio",
            json={
                "audio_base64": base64.b64encode(b"fake").decode("ascii"),
                "mime_type": "audio/webm",
                "duration_ms": 8000,
                "attempt_id": "empty-attempt",
            },
        )
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    assert response.status_code == 200
    assert response.json()["status"] == "unclear"
    assert response.json()["needs_retry"] is True
    assert detail["answers"] == []
    assert detail["voice_interpretations"][0]["status"] == "unclear"


def test_voice_audio_repairs_malformed_claude_json_and_saves_answer(
    monkeypatch,
    tmp_path,
    caplog,
):
    from have_some_ai import openai_file_stt, questionnaire, voice

    class FakeClaudeClient:
        calls = []
        responses = [
            (
                '{"status":"accepted","option_id":"A"\n'
                '"confidence":0.9,"reason":"The user said yes."}'
            ),
            (
                '{"status":"accepted","option_id":"A","confidence":0.9,'
                '"reason":"The user said yes.","detected_language":"zh",'
                '"spoken_choice":"freeform"}'
            ),
        ]

        def complete(self, **kwargs):
            self.__class__.calls.append(kwargs)
            return self.__class__.responses.pop(0)

    def draw_known_questions(self):
        return [
            self.get_question("m1_thank_ai"),
            self.get_question("m2_door"),
        ]

    audio_payload = base64.b64encode(b"fake-audio").decode("ascii")
    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "嗯...有过吧", "language": "zh"}
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(voice, "ClaudeClient", FakeClaudeClient)
    monkeypatch.setattr(questionnaire.QuestionBank, "draw_questions", draw_known_questions)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draw = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"][0]
        response = client.post(
            f"/api/v1/participants/{participant['id']}/questions/{draw['question_id']}/voice-audio",
            json={
                "audio_base64": audio_payload,
                "mime_type": "audio/webm",
                "duration_ms": 1900,
                "attempt_id": "repair-json-attempt",
            },
        )
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    assert draw["question_id"] == "m1_thank_ai"
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    assert response.json()["option_id"] == "A"
    assert response.json()["needs_retry"] is False
    assert detail["answers"][0]["option_id"] == "A"
    assert detail["voice_interpretations"][0]["status"] == "accepted"
    assert detail["voice_interpretations"][0]["raw_llm_json"]["_json_repaired"] is True
    assert len(FakeClaudeClient.calls) == 2
    assert audio_payload not in caplog.text
    assert "test-key" not in caplog.text


def test_voice_audio_three_answers_create_only_one_pending_queue_item(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我选 A", "language": "zh"}
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://aihubmix.com/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)

    def fake_interpret(self, **_kwargs):
        return RubricInterpretation("A", 0.9, "清楚选择 A。", "Clear A.", "zh", {})

    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        draws = client.post(
            f"/api/v1/participants/{participant['id']}/questionnaire/start"
        ).json()["questions"]
        final_payload = None
        final_path = None
        for index, draw in enumerate(draws):
            payload = {
                "audio_base64": base64.b64encode(f"fake-{index}".encode()).decode("ascii"),
                "mime_type": "audio/webm",
                "duration_ms": 1200,
                "attempt_id": f"attempt-{index}",
            }
            path = (
                f"/api/v1/participants/{participant['id']}"
                f"/questions/{draw['question_id']}/voice-audio"
            )
            final_payload = payload
            final_path = path
            client.post(path, json=payload)

        assert final_path is not None and final_payload is not None
        duplicate = client.post(final_path, json=final_payload).json()
        queue = client.get("/api/v1/staff-queue").json()
        exported = client.get("/api/v1/export").json()

    assert "assignment" in duplicate
    assert len(queue) == 1
    assert queue[0]["status"] == "pending"
    assert len(exported["meal_assignments"]) == 1
    assert len(exported["meal_staff_queue"]) == 1


def test_conversation_audio_calls_file_stt_tts_and_orchestrator(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt, openai_tts

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "老板你好", "language": "zh"}
    calls = []
    original_conversation_turn = ConversationOrchestrator.conversation_turn

    def spy_conversation_turn(self, participant_id, transcript, **kwargs):
        calls.append({
            "participant_id": participant_id,
            "transcript": transcript,
            "kwargs": kwargs,
        })
        return original_conversation_turn(self, participant_id, transcript, **kwargs)

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "aihubmix")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "file")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(ConversationOrchestrator, "conversation_turn", spy_conversation_turn)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-audio",
            json=_conversation_audio_payload("hello"),
        )

    payload = response.json()
    urls = [post["url"] for post in _FakeHTTPClient.posts]
    assert response.status_code == 200
    assert payload["transcript"] == "老板你好"
    assert payload["stage"] == "food_gate"
    assert payload["response_language"] == "zh"
    assert payload["reply_audio_base64"] == base64.b64encode(b"fake-mp3").decode("ascii")
    assert any("audio/transcriptions" in url for url in urls)
    assert any("audio/speech" in url for url in urls)
    assert calls[0]["transcript"] == "老板你好"
    assert calls[0]["kwargs"]["stt_metadata"]["source"] == "conversation_audio"


def test_conversation_turn_can_return_reply_audio(monkeypatch, tmp_path):
    from have_some_ai import openai_tts

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "aihubmix")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "file")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "", "include_audio": True},
        )

    payload = response.json()
    speech_posts = [
        post for post in _FakeHTTPClient.posts if "audio/speech" in post["url"]
    ]
    assert response.status_code == 200
    assert payload["stage"] == "language_gate"
    assert payload["reply_audio_base64"] == base64.b64encode(b"fake-mp3").decode("ascii")
    assert payload["reply_audio_mime_type"] == "audio/mpeg"
    assert payload["reply_audio_provider"] == "openai_compatible"
    assert len(speech_posts) == 1
    assert "Hi. 你好～ Do you want to talk in 中文 or English?" in speech_posts[0]["json"]["input"]


def test_conversation_turn_doubao_mode_never_uses_openai_tts(monkeypatch, tmp_path):
    from have_some_ai import openai_tts

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "legacy-tts-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "", "include_audio": True},
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["stage"] == "language_gate"
    assert payload["reply_audio_base64"] is None
    assert payload["reply_audio_mime_type"] is None
    assert payload["reply_audio_provider"] == "doubao_stream"
    assert not [post for post in _FakeHTTPClient.posts if "audio/speech" in post["url"]]


def test_conversation_turn_defaults_to_text_only(monkeypatch, tmp_path):
    from have_some_ai import openai_tts

    _FakeHTTPClient.posts = []
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["reply_audio_base64"] is None
    assert payload["reply_audio_mime_type"] is None
    assert not [post for post in _FakeHTTPClient.posts if "audio/speech" in post["url"]]


def test_conversation_audio_food_gate_turn_does_not_store_formal_answer(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt, openai_tts

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我随便聊一句", "language": "zh"}
    claude_calls = {"count": 0}

    def fake_interpret(self, **_kwargs):
        claude_calls["count"] += 1
        return RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {})

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-audio",
            json=_conversation_audio_payload("food-gate"),
        )
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    assert response.status_code == 200
    assert response.json()["stage"] == "food_gate"
    assert detail["answers"] == []
    assert detail["voice_interpretations"] == []
    assert claude_calls["count"] == 0


def test_conversation_audio_formal_question_maps_and_saves_answer(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt, openai_tts

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我选 B", "language": "zh"}

    def fake_interpret(self, **_kwargs):
        return RubricInterpretation("B", 0.93, "清楚选择 B。", "Clear B.", "zh", {})

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        question = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "想吃"},
        ).json()
        response = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-audio",
            json=_conversation_audio_payload("accepted"),
        )
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    payload = response.json()
    assert payload["stage"] == "formal_question_2"
    assert payload["interpretation"] == {
        "status": "accepted",
        "choice": "B",
        "confidence": 0.93,
    }
    assert len(detail["answers"]) == 1
    assert detail["answers"][0]["question_id"] == question["current_question_id"]
    assert detail["answers"][0]["option_id"] == "B"
    assert detail["voice_interpretations"][0]["stt_metadata"]["source"] == (
        "conversation_audio"
    )


def test_conversation_audio_two_answers_generate_assignment(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt, openai_tts

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我选 A", "language": "zh"}
    results = [
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ]

    def fake_interpret(self, **_kwargs):
        return results.pop(0)

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "想吃"},
        )
        final = None
        for index in range(2):
            final = client.post(
                f"/api/v1/participants/{participant['id']}/conversation-audio",
                json=_conversation_audio_payload(f"answer-{index}"),
            ).json()
            if index < 1:
                client.post(
                    f"/api/v1/participants/{participant['id']}/conversation-turn",
                    json={"transcript": ""},
                )
        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    assert final is not None
    assert final["stage"] == "farewell"
    assert final["assignment"] is not None
    assert len(detail["answers"]) == 2
    assert detail["assignment"]["assignment_id"] == final["assignment"]["assignment_id"]


def test_conversation_audio_after_assignment_does_not_change_result(
    monkeypatch,
    tmp_path,
):
    from have_some_ai import openai_file_stt, openai_tts

    _FakeHTTPClient.posts = []
    _FakeHTTPClient.transcription_payload = {"text": "我要换一个", "language": "zh"}
    claude_calls = {"count": 0}
    results = [
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
        RubricInterpretation("A", 0.9, "清楚。", "Clear.", "zh", {}),
    ]

    def fake_interpret(self, **_kwargs):
        claude_calls["count"] += 1
        return results.pop(0)

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_API_KEY", "test-key")
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_BASE_URL", "https://voice-provider.example/v1")
    monkeypatch.setattr(openai_file_stt.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(openai_tts.httpx, "Client", _FakeHTTPClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "想吃"},
        )
        ready = None
        for index in range(2):
            ready = client.post(
                f"/api/v1/participants/{participant['id']}/conversation-audio",
                json=_conversation_audio_payload(f"answer-{index}"),
            ).json()
            if index < 1:
                client.post(
                    f"/api/v1/participants/{participant['id']}/conversation-turn",
                    json={"transcript": ""},
                )
        assigned = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-audio",
            json=_conversation_audio_payload("after-assigned"),
        ).json()

    assert ready is not None
    assert assigned["stage"] == "assigned"
    assert assigned["assignment"]["assignment_id"] == ready["assignment"]["assignment_id"]
    assert assigned["assignment"]["food_code"] == ready["assignment"]["food_code"]
    assert claude_calls["count"] == 2


def test_conversation_stream_uses_doubao_asr_tts_and_existing_claude_judge(
    monkeypatch,
    tmp_path,
):
    from have_some_ai.interfaces import api

    _FakeASRClient.instances = []
    _FakeTTSClient.instances = []
    claude_calls = {"count": 0}

    def fake_interpret(self, **kwargs):
        claude_calls["count"] += 1
        assert kwargs["transcript"] == "我选 B"
        return RubricInterpretation("B", 0.93, "清楚选择 B。", "Clear B.", "zh", {})

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-secret")
    monkeypatch.setattr(api, "DoubaoASRClient", _FakeASRClient)
    monkeypatch.setattr(api, "DoubaoTTSBidirectionalClient", _FakeTTSClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        question = client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "想吃"},
        ).json()

        with client.websocket_connect(
            f"/api/v1/participants/{participant['id']}/conversation-stream"
        ) as websocket:
            connected = websocket.receive_json()
            output_config = websocket.receive_json()
            websocket.send_json({"type": "session.start", "prepare_turn": False})
            started = websocket.receive_json()
            websocket.send_bytes(b"x" * 6400)
            partial = _receive_json_type(websocket, "asr.partial")
            final = _receive_json_type(websocket, "asr.final")
            conversation = _receive_json_type(websocket, "conversation")
            judge = _receive_json_type(websocket, "judge")
            muted = _receive_json_type(websocket, "mic.muted_for_tts")
            tts_started = _receive_json_event(websocket, "tts.event", TTS_SESSION_STARTED)
            tts_audio = websocket.receive_bytes()
            resumed = _receive_json_type(websocket, "mic.resumed_after_tts")
            websocket.send_json({"type": "session.cancel"})

        detail = client.get(f"/api/v1/participants/{participant['id']}").json()

    asr = _FakeASRClient.instances[0]
    tts = _FakeTTSClient.instances[0]
    combined_response = json.dumps(
        [connected, output_config, started, partial, final, conversation, judge, muted, tts_started, resumed],
        ensure_ascii=False,
    )
    assert connected["state"] == "connected"
    assert output_config == {
        "type": "audio.output_config",
        "format": "pcm_s16le",
        "sample_rate": 24000,
        "channels": 1,
    }
    assert started["state"] == "session.started"
    assert partial == {"type": "asr.partial", "text": "我"}
    assert final["text"] == "我选 B"
    assert conversation["conversation"]["stage"] == "formal_question_2"
    assert judge == {"type": "judge", "label": "B", "confidence": 0.93}
    assert muted["type"] == "mic.muted_for_tts"
    assert muted["text"] == tts.spoken_texts[0]
    assert tts_audio == b"fake-pcm-24k"
    assert resumed["type"] == "mic.resumed_after_tts"
    assert asr.audio_chunks == [b"x" * 6400]
    assert asr.finish_calls == 1
    assert tts.spoken_texts
    assert claude_calls["count"] == 1
    assert detail["answers"][0]["question_id"] == question["current_question_id"]
    assert detail["answers"][0]["option_id"] == "B"
    assert detail["voice_interpretations"][0]["stt_metadata"]["provider"] == "doubao_asr"
    assert "doubao-secret" not in combined_response


def test_conversation_stream_tts_only_uses_task_request_path(monkeypatch, tmp_path):
    from have_some_ai.interfaces import api

    _FakeASRClient.instances = []
    _FakeTTSClient.instances = []
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setattr(api, "DoubaoASRClient", _FakeASRClient)
    monkeypatch.setattr(api, "DoubaoTTSBidirectionalClient", _FakeTTSClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        with client.websocket_connect(
            f"/api/v1/participants/{participant['id']}/conversation-stream"
        ) as websocket:
            websocket.receive_json()
            websocket.receive_json()
            websocket.send_json({"type": "session.start", "prepare_turn": False})
            websocket.receive_json()
            websocket.send_json({"type": "tts.speak", "text": "想来点吃的吗？"})
            muted = _receive_json_type(websocket, "mic.muted_for_tts")
            websocket.receive_json()
            audio = websocket.receive_bytes()
            _receive_json_type(websocket, "mic.resumed_after_tts")
            websocket.send_json({"type": "session.cancel"})

    tts = _FakeTTSClient.instances[0]
    assert muted["text"] == "想来点吃的吗？"
    assert audio == b"fake-pcm-24k"
    assert tts.spoken_texts == ["想来点吃的吗？"]


def test_conversation_stream_barge_in_cancels_tts_session(monkeypatch, tmp_path):
    from have_some_ai.interfaces import api

    _SlowTTSClient.instances = []
    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setattr(api, "DoubaoASRClient", _FakeASRClient)
    monkeypatch.setattr(api, "DoubaoTTSBidirectionalClient", _SlowTTSClient)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        with client.websocket_connect(
            f"/api/v1/participants/{participant['id']}/conversation-stream"
        ) as websocket:
            websocket.receive_json()
            websocket.receive_json()
            websocket.send_json({"type": "session.start", "prepare_turn": False})
            websocket.receive_json()
            websocket.send_json({"type": "tts.speak", "text": "很长的一句话"})
            muted = _receive_json_type(websocket, "mic.muted_for_tts")
            websocket.send_json({"type": "barge_in"})
            canceling = _receive_json_type(websocket, "tts.canceling")
            canceled = _receive_json_event(websocket, "tts.event", TTS_SESSION_CANCELED)
            resumed = _receive_json_type(websocket, "mic.resumed_after_tts")
            websocket.send_json({"type": "session.cancel"})

    tts = _SlowTTSClient.instances[0]
    assert muted["text"] == "很长的一句话"
    assert canceling["type"] == "tts.canceling"
    assert canceled["event"] == TTS_SESSION_CANCELED
    assert resumed["type"] == "mic.resumed_after_tts"
    assert tts.cancel_calls == 1


def test_conversation_stream_tts_error_keeps_asr_mic_path_open(
    monkeypatch,
    tmp_path,
):
    from have_some_ai.interfaces import api

    _FakeASRClient.instances = []
    _FailingTTSClient.instances = []

    def fake_interpret(self, **kwargs):
        assert kwargs["transcript"] == "我选 B"
        return RubricInterpretation("B", 0.93, "清楚选择 B。", "Clear B.", "zh", {})

    monkeypatch.setenv("HAVE_SOME_AI_DB_PATH", str(tmp_path / "meal.db"))
    monkeypatch.setenv("HAVE_SOME_AI_VOICE_PROVIDER", "doubao")
    monkeypatch.setenv("HAVE_SOME_AI_STT_MODE", "asr_tts_stream")
    monkeypatch.setenv("DOUBAO_API_KEY", "doubao-key")
    monkeypatch.setattr(api, "DoubaoASRClient", _FakeASRClient)
    monkeypatch.setattr(api, "DoubaoTTSBidirectionalClient", _FailingTTSClient)
    monkeypatch.setattr(ClaudeRubricInterpreter, "interpret", fake_interpret)

    with TestClient(app) as client:
        participant = client.post("/api/v1/participants", json={}).json()
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": ""},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "中文"},
        )
        client.post(
            f"/api/v1/participants/{participant['id']}/conversation-turn",
            json={"transcript": "想吃"},
        )

        with client.websocket_connect(
            f"/api/v1/participants/{participant['id']}/conversation-stream"
        ) as websocket:
            websocket.receive_json()
            websocket.receive_json()
            websocket.send_json({"type": "session.start", "prepare_turn": False})
            websocket.receive_json()
            websocket.send_json({"type": "tts.speak", "text": "会失败的一句话"})
            muted = _receive_json_type(websocket, "mic.muted_for_tts")
            error = _receive_json_type(websocket, "tts.error")
            resumed = _receive_json_type(websocket, "mic.resumed_after_tts")
            websocket.send_bytes(b"x" * 6400)
            final = _receive_json_type(websocket, "asr.final")
            conversation = _receive_json_type(websocket, "conversation")
            websocket.send_json({"type": "session.cancel"})

    asr = _FakeASRClient.instances[0]
    assert muted["type"] == "mic.muted_for_tts"
    assert muted["text"] == "会失败的一句话"
    assert error["provider"] == "doubao_tts"
    assert "DOUBAO_TTS_API_KEY" in error["message"]
    assert resumed["type"] == "mic.resumed_after_tts"
    assert final["text"] == "我选 B"
    assert conversation["conversation"]["stage"] == "formal_question_2"
    assert asr.audio_chunks == [b"x" * 6400]


def _receive_json_type(websocket, expected_type: str) -> dict:
    for _ in range(20):
        message = websocket.receive()
        if "text" not in message:
            continue
        payload = json.loads(message["text"])
        if payload.get("type") == expected_type:
            return payload
    raise AssertionError(f"Did not receive {expected_type}")


def _receive_json_event(websocket, expected_type: str, expected_event: int) -> dict:
    for _ in range(20):
        message = websocket.receive()
        if "text" not in message:
            continue
        payload = json.loads(message["text"])
        if payload.get("type") == expected_type and payload.get("event") == expected_event:
            return payload
    raise AssertionError(f"Did not receive {expected_type} event {expected_event}")


class _FakeASRClient:
    instances: list["_FakeASRClient"] = []

    def __init__(self, *args, **kwargs):
        self.__class__.instances.append(self)
        self.request_id = "fake-asr-request"
        self.connect_id = "fake-asr-connect"
        self.provider_log_id = "fake-asr-log"
        self.audio_chunks: list[bytes] = []
        self.finish_calls = 0
        self._finished = False
        self._events: asyncio.Queue[ASRTranscriptEvent | None] = asyncio.Queue()

    async def connect(self):
        return None

    async def append_audio(self, audio: bytes):
        self.audio_chunks.append(audio)
        await self._events.put(ASRTranscriptEvent("partial", "我"))
        await self._events.put(ASRTranscriptEvent(
            "final",
            "我选 B",
            start_time=1,
            end_time=2,
            definite=True,
            key=(1, 2, "我选 B"),
            metadata={"utterance": {"text": "我选 B", "definite": True}},
        ))

    async def finish(self, audio: bytes = b""):
        if self._finished:
            return
        self._finished = True
        self.finish_calls += 1
        await self._events.put(None)

    async def close(self):
        return None

    async def events(self):
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event


class _FakeTTSClient:
    instances: list["_FakeTTSClient"] = []

    def __init__(self, *args, **kwargs):
        self.__class__.instances.append(self)
        self.spoken_texts: list[str] = []
        self.cancel_calls = 0

    async def synthesize(self, text: str):
        self.spoken_texts.append(text)
        yield TTSEvent(TTS_SESSION_STARTED, session_id="fake-tts-session")
        yield TTSEvent(TTS_RESPONSE, session_id="fake-tts-session", audio=b"fake-pcm-24k")
        yield TTSEvent(TTS_SESSION_FINISHED, session_id="fake-tts-session", payload={})

    async def cancel_current_session(self):
        self.cancel_calls += 1

    async def close(self):
        return None


class _SlowTTSClient(_FakeTTSClient):
    instances: list["_SlowTTSClient"] = []

    async def synthesize(self, text: str):
        self.spoken_texts.append(text)
        yield TTSEvent(TTS_SESSION_STARTED, session_id="slow-tts-session")
        await asyncio.sleep(0.2)
        yield TTSEvent(TTS_SESSION_CANCELED, session_id="slow-tts-session", payload={})


class _FailingTTSClient(_FakeTTSClient):
    instances: list["_FailingTTSClient"] = []

    async def synthesize(self, text: str):
        self.spoken_texts.append(text)
        if False:
            yield TTSEvent(TTS_SESSION_STARTED, session_id="unused")
        raise ValueError("Missing DOUBAO_TTS_API_KEY or DOUBAO_API_KEY")


def _conversation_audio_payload(attempt_id: str) -> dict[str, object]:
    return {
        "audio_base64": base64.b64encode(f"fake-{attempt_id}".encode()).decode("ascii"),
        "mime_type": "audio/webm;codecs=opus",
        "duration_ms": 1200,
        "attempt_id": attempt_id,
        "include_audio": True,
    }
