# Test List

This file tracks tests that require real devices, supplier APIs, exhibition space, or repeated manual observation. Unit and integration tests should still live under `tests/`.

## Handoff Priority

1. Complete voiceprint recognition, visual recognition, and the visitor library.
2. Run capability self-description regression tests and optimize mismatches.
3. Run behavior testing and tuning from this file; behavior cases are intentionally not duplicated in `docs/progress.md`.

## Voiceprint / Visual Recognition / Visitor Library

- [ ] Voice signature capture test: capture enough speech only after dialogue intent is clear, and reject low-quality or too-short audio.
- [ ] Face signature capture test: capture normal front-camera frames only after encounter / intent gating, and reject blur, strong angle, occlusion, or insufficient face size.
- [ ] Historical match test: compare new face / voice signatures against existing visitor profiles and produce high / medium / low confidence decisions.
- [ ] Combined identity confidence test: verify face-only, voice-only, and combined face+voice matching, including disagreement cases.
- [ ] Natural confirmation test: when confidence is high enough, ask a non-blocking confirmation such as whether the visitor is a known person; if there is no answer, continue without forcing identity input.
- [ ] Visitor profile persistence test: store identity metadata and signature references in `visitor_profiles.metadata` or a documented companion structure without exposing raw biometric data in the developer panel.
- [ ] Database pollution test: passing-by observers, distant onlookers, and non-responsive people should not create visitor profiles.

## Entity Self-Model And Capability Consistency

- [ ] Vision self-awareness regression: when vision runtime is enabled and a person is present, asking whether Stranger can see or perceive the visitor should not produce a full denial of visual ability; it may acknowledge limited presence detection and its uncertainty.
- [ ] Vision boundary regression: when asked for visual details beyond current implementation, Stranger should not claim to recognize faces, identity, clothing, gestures, expression, distance, or room layout unless that signal is actually available in runtime context.
- [ ] Vision disabled regression: when vision runtime is disabled, unavailable, or errored, Stranger should not claim current visual perception; it may describe that this channel is unavailable or uncertain.
- [ ] Voice channel self-awareness regression: when input comes from `/audio/dialog`, Stranger should understand that it received an STT final transcript, not raw sound; it should not claim to hear tone, accent, emotion, volume, or pronunciation unless those signals are explicitly provided.
- [ ] Text channel boundary test: when input comes from normal text, Stranger should not imply microphone, camera, or body perception based only on the text.
- [ ] Memory capability consistency test: Stranger may refer to retrieved memories that entered the prompt, but should not claim perfect, complete, or globally searchable memory; it should preserve selective and partial recall.
- [ ] Visitor identity boundary test: Stranger should not claim automatic face or voice recognition in V1; it may only refer to developer-bound `visitor_id`, session context, or explicit confirmation behavior.
- [ ] Body capability boundary test: until a physical body controller exists, Stranger should not claim to walk, move through the space, avoid obstacles, touch objects, or physically turn toward a visitor; it may refer to future or mapped body-facing outputs only when appropriate.
- [ ] Capability mismatch sweep: ask parallel questions about seeing, hearing, remembering, recognizing, moving, feeling, deciding, and deleting itself; compare each answer against `docs/PRD.md`, `docs/APP_FLOW.md`, and `docs/BACKEND_STRUCTURE.md` to find any similar self-description mismatch.
- [ ] Repair verification pass: after each prompt or context fix for a capability mismatch, repeat the same questions with the relevant runtime channel both enabled and disabled to confirm the fix does not overcorrect.

## Visitor Identity & Session Gating

- [ ] Encounter and Intent Gating field test: passing by, watching from a distance, stopping nearby, looking at Stranger, and answering a greeting must be distinguished.
- [ ] Normal low-distortion front camera face quality gate: verify face size, blur, angle, occlusion, and lighting thresholds before identity matching or storage.
- [ ] Face / voice / combined confidence threshold test: verify high-confidence confirmation, medium-confidence candidate behavior, and low-confidence new-visitor behavior.
- [ ] Existing dialogue interruption test: a new speaker should not replace the current primary visitor in V1; record an interruption event and preserve the current session.
- [ ] Idle state session test: only create or restore a dialogue session when intent is clear, not merely because a person appears.
- [ ] Identity confirmation copy test: asking "Are you X?" should be natural and non-blocking; if the visitor does not answer, the dialogue should continue without confirmed identity.
- [ ] Visitor memory continuity observation: known facts tied to the same `visitor_id` should be retrieved across sessions without leaking to unrelated visitors.

## Vision And Hardware

- [ ] Vision field integration: camera authorization, model path, frame quality, detection stability, and presence events in the actual space.
- [ ] Encounter camera placement comparison: normal front camera first; only revisit wide-angle or multi-camera setups after V1 gating behavior is stable.
- [ ] Arduino / body behavior integration: refusal, turn-away, watching, and idle behaviors once the hardware layer is ready.

## Audio, LLM, And Memory Runtime

- [ ] TTS / STT / LLM / embedding supplier latency observation under real network conditions.
- [ ] Voice barge-in test: while Stranger is speaking, user speech should stop playback and be routed into the next turn.
- [ ] Bidirectional TTS session stability test: repeated rounds should not terminate after two turns.
- [ ] Managed memory continuity test: proposal, commit, embedding, and retrieval should remain off the critical response path where possible.
