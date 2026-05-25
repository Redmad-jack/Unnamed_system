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
- [ ] Face confidence threshold test: verify known high and known medium both enter candidate confirmation only after A has been released; verify low/no known match with accepted single-face capture auto-creates a new visitor only in unidentified ready state; voice / combined confidence remains optional P1.
- [ ] New visitor auto-provision field test: after A's primary track has been released and a new unidentified session is current, let an unknown B speak with a clean single-face frame; verify a new `visitor-*` profile is created, a face signature is enrolled, the current session is bound before the turn is written, and no old visitor memory is recalled.
- [ ] New visitor rejection field test: unknown B with no frame, multi-face, blur, small face, strong pose, or near-medium ambiguous known cluster should remain unidentified and must not create a profile or candidate.
- [ ] Existing dialogue interruption test: while A remains the primary visitor and primary track is alive, B should not replace A; record an interruption / refuse-switch event and preserve the current session.
- [ ] Primary-leave grace test: after A's locked primary track is lost, keep A for the 35-second grace window; if A returns within grace, continue A's session.
- [ ] Grace-window unscoped input test: if B speaks while A's primary track is missing but still inside the 35-second grace window, route the turn to an unscoped `visitor_id=NULL` session, do not bind B, and do not read or write A/B visitor memory.
- [ ] Primary-leave handoff test: after A's locked primary track is lost for more than 35 seconds, release A, start or promote a new unidentified session, and only then allow B to enter candidate / confirmation.
- [ ] Ambiguous track test: when A/B are in frame together before a stable primary track can be locked, do not auto-release A or bind the remaining single track as A; if no primary track was ever locked, an empty scene must not clear A unless the operator explicitly clears it.
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
