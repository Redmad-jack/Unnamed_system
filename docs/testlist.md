# Test List

This file tracks tests that require real devices, supplier APIs, exhibition space, or repeated manual observation. Unit and integration tests should still live under `tests/`.

## Handoff Priority

1. Complete the face-only visitor identity closure: auto capture, candidate confirmation, visitor binding, memory permission, and database pollution checks.
2. Run capability self-description regression tests and optimize mismatches.
3. Run behavior testing and tuning from this file; behavior cases are intentionally not duplicated in `docs/progress.md`.

## Voiceprint / Visual Recognition / Visitor Library

- [ ] Voice signature capture test: optional P1 follow-up; capture enough speech only after dialogue intent is clear, and reject low-quality or too-short audio.
- [ ] Face signature capture field test: with local InsightFace / ArcFace installed, capture normal front-camera frames only after encounter / intent gating, and reject blur, strong angle, occlusion, insufficient face size, no-face, and multi-face frames.
- [ ] Historical match field test: compare new face signatures against existing visitor profiles and produce high / medium / low confidence decisions without high-confidence false binding.
- [ ] Combined identity confidence test: optional P1 follow-up; verify face-only, voice-only, and combined face+voice matching, including disagreement cases.
- [ ] Natural confirmation test: when confidence is high enough, ask a non-blocking confirmation such as whether the visitor is a known person; if there is no answer, continue without forcing identity input.
- [ ] Visitor profile persistence test: store identity metadata and signature references in `visitor_profiles.metadata` or a documented companion structure without exposing raw biometric data in the developer panel.
- [ ] Identity match API integration test: feed simulated face match result through `/api/v1/identity/match`, then confirm or reject candidate through `/api/v1/identity/confirm`.
- [ ] Database pollution test: passing-by observers, distant onlookers, and non-responsive people should not create visitor profiles.

## Visitor Identity & Session Gating

- [ ] Encounter and Intent Gating field test: passing by, watching from a distance, stopping nearby, looking at Stranger, and answering a greeting must be distinguished.
- [ ] Normal low-distortion front camera face quality gate: verify face size, blur, angle, occlusion, and lighting thresholds before identity matching or storage.
- [ ] Face confidence threshold test: verify high-confidence confirmation, medium-confidence candidate behavior, and low-confidence new-visitor behavior; voice / combined confidence remains optional P1.
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
