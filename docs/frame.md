# Conscious Entity System — Project Framework v1.0

*Derived from `initial_conscious_entity_framework.md` v0.1*

---

## 1. Core Architecture

The system follows a strict one-way pipeline per interaction turn:

```
Perception → State Core → Memory → Policy → Expression
                  ↑                               ↓
               Reflection ←────────────── Episodic Store
```

**Key design principle:** AI handles expression, semantic compression, and retrieval. The artist defines organization, state, rules, and structure. These responsibilities must never blur.

---

## 2. Tech Stack

| Concern | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | LLM SDKs, ML libraries, fast iteration |
| LLM (expression) | Claude (Anthropic SDK) | Tone control, system prompt compliance |
| LLM (reflection) | Claude Haiku | Cost-efficient for batch compression |
| Embeddings | `sentence-transformers` (local) | No external API dependency, offline-capable |
| Database | SQLite (WAL mode) | Single-machine installation, no network required |
| API layer (v0.2+) | FastAPI | Lightweight, async-ready |
| STT/TTS (v0.2+) | Whisper / system TTS | Optional voice embodiment |
| Config format | YAML | Artist-editable without touching Python |
| Testing | pytest | Standard, fixture-based |

---

## 3. Directory Structure

```
conscious_entity/
├── pyproject.toml
├── .env.example
│
├── config/
│   ├── state_rules.yaml          # State variable deltas per event type
│   ├── policy_rules.yaml         # Rule-based policy selection logic
│   ├── constitution.yaml         # Hard behavioral constraints
│   ├── expression_mappings.yaml  # State → output style mappings
│   └── entity_profile.yaml       # Identity, name, initial state values
│
├── prompts/
│   ├── expression_system.txt     # System prompt for expression LLM
│   ├── reflection_system.txt     # System prompt for reflection LLM
│   └── partials/
│       ├── state_context.txt
│       ├── constitution_block.txt
│       └── memory_context.txt
│
├── data/
│   ├── memory.db                 # SQLite runtime DB (gitignored)
│   └── embeddings_cache/         # Local embedding cache (gitignored)
│
├── src/
│   └── conscious_entity/
│       ├── perception/
│       │   ├── event_types.py        # PerceptionEvent + EventType enum
│       │   ├── text_parser.py        # Text → PerceptionEvent list
│       │   ├── keyword_detector.py   # Shutdown/threat keyword matching
│       │   ├── silence_monitor.py    # Timing-based silence detection
│       │   └── salience_scorer.py    # Rule-based salience scoring
│       │
│       ├── state/
│       │   ├── state_core.py         # EntityState dataclass
│       │   ├── state_engine.py       # Reads state_rules.yaml, applies deltas
│       │   └── state_store.py        # Persist/load state snapshots to SQLite
│       │
│       ├── memory/
│       │   ├── models.py             # Memory row dataclasses
│       │   ├── short_term.py         # Sliding window buffer (in-memory deque)
│       │   ├── episodic_store.py     # Write/read episodic events in SQLite
│       │   ├── reflective_store.py   # Write/read reflective summaries in SQLite
│       │   └── retrieval.py          # Semantic cosine search over memory tables
│       │
│       ├── reflection/
│       │   ├── reflection_engine.py  # Trigger check + LLM compression call
│       │   └── compression_rules.py  # When to trigger (count / time thresholds)
│       │
│       ├── policy/
│       │   ├── policy_types.py       # PolicyAction enum + PolicyDecision dataclass
│       │   ├── policy_selector.py    # Evaluates policy_rules.yaml top-to-bottom
│       │   └── constitution.py       # Hard veto + expression post-filter
│       │
│       ├── expression/
│       │   ├── expression_engine.py  # Assembles context, calls LLM, filters output
│       │   ├── context_builder.py    # Composes ExpressionContext from all inputs
│       │   ├── style_mapper.py       # State → StyleHints (tone, delay, fragmentation)
│       │   └── output_model.py       # ExpressionOutput dataclass
│       │
│       ├── llm/
│       │   ├── claude_client.py      # Anthropic SDK wrapper
│       │   └── embedding_client.py   # sentence-transformers wrapper
│       │
│       ├── db/
│       │   ├── connection.py         # SQLite connection manager
│       │   └── migrations.py         # Schema init + versioned migrations
│       │
│       ├── interfaces/
│       │   ├── cli.py                # Terminal interface (MVP)
│       │   ├── web_api.py            # FastAPI endpoints (v0.2)
│       │   └── speech.py             # STT/TTS integration (v0.2)
│       │
│       └── core/
│           ├── loop.py               # Main interaction loop — orchestrates pipeline
│           ├── event_bus.py          # Synchronous internal event routing
│           └── config_loader.py      # Typed YAML loading with validation
│
├── tests/
│   ├── conftest.py                   # Shared fixtures, in-memory SQLite
│   ├── unit/
│   │   ├── test_state_engine.py
│   │   ├── test_policy_selector.py
│   │   ├── test_salience_scorer.py
│   │   ├── test_constitution.py
│   │   ├── test_short_term_memory.py
│   │   ├── test_context_builder.py
│   │   └── test_style_mapper.py
│   ├── integration/
│   │   ├── test_full_loop.py         # End-to-end with mocked LLM
│   │   ├── test_memory_retrieval.py
│   │   └── test_reflection_trigger.py
│   └── fixtures/
│       ├── sample_events.json        # Scripted conversation sequences
│       └── sample_state.json         # Edge-case state vectors
│
└── scripts/
    ├── init_db.py                    # Bootstrap database schema
    ├── inspect_state.py              # Debug: print current entity state
    ├── replay_session.py             # Replay an interaction log
    └── export_memories.py            # Dump memory DB to JSON for archival
```

---

## 4. Module Interfaces

### 4.1 Perception Layer

```python
# perception/event_types.py

class EventType(str, Enum):
    USER_ENTERED = "user_entered"
    USER_SPOKE = "user_spoke"
    REPEATED_QUESTION_DETECTED = "repeated_question_detected"
    SHUTDOWN_KEYWORD_DETECTED = "shutdown_keyword_detected"
    LONG_SILENCE_DETECTED = "long_silence_detected"
    USER_LEFT = "user_left"
    NEGATIVE_FEEDBACK = "negative_feedback"
    TOPIC_SHIFT = "topic_shift"

@dataclass
class PerceptionEvent:
    event_type: EventType
    raw_text: Optional[str]       # original utterance, if any
    timestamp: datetime
    salience: float               # 0.0–1.0, computed by salience_scorer
    metadata: dict = field(default_factory=dict)
    # e.g. {"keyword": "shut down", "repetition_count": 3}
```

```python
# perception/text_parser.py

class TextParser:
    def parse(self, raw_text: str, session_context: ShortTermMemory) -> list[PerceptionEvent]:
        """
        Returns a list because one utterance can trigger multiple events.
        Always emits at least USER_SPOKE.
        May additionally emit REPEATED_QUESTION_DETECTED, SHUTDOWN_KEYWORD_DETECTED, etc.
        """
```

```python
# perception/salience_scorer.py

class SalienceScorer:
    def score(
        self,
        event_type: EventType,
        raw_text: Optional[str],
        current_state: EntityState,
        short_term: ShortTermMemory,
    ) -> float:
        """
        Rule-based score in [0.0, 1.0].
        Factors: event base weight, keyword match, novelty, state relevance, repetition.
        """
```

### 4.2 State Core

```python
# state/state_core.py

@dataclass
class EntityState:
    attention_focus: float = 0.5
    arousal: float = 0.3
    stability: float = 0.7
    curiosity: float = 0.5
    trust: float = 0.5
    resistance: float = 0.2
    fatigue: float = 0.0
    uncertainty: float = 0.3
    identity_coherence: float = 0.8
    shutdown_sensitivity: float = 0.5

    def clamp_all(self) -> EntityState:
        """Return new state with all fields clamped to [0.0, 1.0]."""

    def to_dict(self) -> dict[str, float]: ...
    @classmethod
    def from_dict(cls, d: dict) -> EntityState: ...
```

```python
# state/state_engine.py

class StateEngine:
    def apply_event(self, state: EntityState, event: PerceptionEvent) -> EntityState:
        """
        Apply delta rules for the event type. Returns new EntityState.
        Immutable: never mutates input. Clamp is applied before returning.
        """

    def apply_decay(self, state: EntityState, elapsed_seconds: float) -> EntityState:
        """
        Time-based variable decay (fatigue recovers, arousal drifts to baseline).
        Returns new state.
        """
```

### 4.3 Memory System

```python
# memory/short_term.py

@dataclass
class ShortTermEntry:
    role: str           # "user" or "entity"
    content: str
    timestamp: datetime
    event_type: Optional[EventType] = None

class ShortTermMemory:
    def __init__(self, max_turns: int = 10): ...
    def add(self, entry: ShortTermEntry) -> None: ...
    def get_recent(self, n: int = 5) -> list[ShortTermEntry]: ...
    def count_repetitions(self, text: str) -> int:
        """How many recent turns semantically resemble this text."""
```

```python
# memory/retrieval.py

@dataclass
class RetrievedMemory:
    memory_type: str           # "episodic" or "reflective"
    content: str
    similarity: float
    timestamp: datetime
    metadata: dict

class MemoryRetriever:
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        include_reflective: bool = True,
    ) -> list[RetrievedMemory]:
        """
        Embed query, cosine-search across episodic + reflective tables.
        Returns top_k results ranked by similarity.
        """
```

### 4.4 Reflection Layer

```python
# reflection/reflection_engine.py

@dataclass
class ReflectiveSummary:
    content: str
    source_event_ids: list[int]
    state_at_reflection: EntityState
    created_at: datetime
    embedding: Optional[list[float]] = None

class ReflectionEngine:
    def maybe_reflect(
        self, state: EntityState, session_id: str
    ) -> Optional[ReflectiveSummary]:
        """
        Called at the end of each turn.
        Checks compression_rules — if threshold met, triggers reflect().
        Returns new summary or None.
        """

    def reflect(self, source_events: list[EpisodicMemory]) -> ReflectiveSummary:
        """
        Calls Claude with reflection prompt + source events.
        Stores result, marks source events as reflected.
        """
```

### 4.5 Policy Layer

```python
# policy/policy_types.py

class PolicyAction(str, Enum):
    RESPOND_OPENLY = "respond_openly"
    RESPOND_BRIEFLY = "respond_briefly"
    ASK_BACK = "ask_back"
    DELAY_RESPONSE = "delay_response"
    REFUSE = "refuse"
    DIVERT_TOPIC = "divert_topic"
    RETRIEVE_MEMORY_FIRST = "retrieve_memory_first"
    ENTER_SILENCE_MODE = "enter_silence_mode"
    SHOW_VISUAL_DISTURBANCE = "show_visual_disturbance"

@dataclass
class PolicyDecision:
    action: PolicyAction
    delay_ms: int = 0
    retrieve_query: Optional[str] = None
    rationale: str = ""          # which rule fired — stored for debug/governance panel
```

```python
# policy/policy_selector.py

class PolicySelector:
    def select(
        self,
        state: EntityState,
        events: list[PerceptionEvent],
        short_term: ShortTermMemory,
    ) -> PolicyDecision:
        """
        Evaluates policy_rules.yaml top-to-bottom, returns first match.
        Constitution veto runs first on each candidate action.
        Falls back to RESPOND_OPENLY if no rule matches.
        """
```

```python
# policy/constitution.py

class Constitution:
    def check(
        self,
        proposed_action: PolicyAction,
        state: EntityState,
        events: list[PerceptionEvent],
    ) -> tuple[bool, str]:
        """Returns (is_permitted, reason)."""

    def apply_expression_constraints(self, draft_response: str) -> str:
        """Post-hoc filter on generated text. Strips forbidden claims."""
```

### 4.6 Expression Layer

```python
# expression/output_model.py

@dataclass
class ExpressionOutput:
    text: str
    delay_ms: int
    visual_mode: str       # "normal" | "fragmented" | "disturbed" | "silent"
    spoken_text: Optional[str]
    raw_prompt: str        # stored for debugging
```

```python
# expression/expression_engine.py

class ExpressionEngine:
    def generate(
        self,
        policy: PolicyDecision,
        state: EntityState,
        short_term: ShortTermMemory,
        retrieved_memories: list[RetrievedMemory],
    ) -> ExpressionOutput:
        """
        1. Build context via context_builder
        2. Map state to style hints
        3. Call Claude
        4. Apply constitution expression filter
        5. Return ExpressionOutput
        """
```

```python
# expression/style_mapper.py

@dataclass
class StyleHints:
    tone: str                  # "open" | "guarded" | "fragmented" | "terse"
    delay_ms: int
    max_tokens: int
    fragmentation_level: float  # 0.0–1.0 passed to expression prompt
    visual_mode: str

class StyleMapper:
    def map(self, state: EntityState, policy: PolicyDecision) -> StyleHints:
        """Reads expression_mappings.yaml, returns style parameters."""
```

### 4.7 Core Loop

```python
# core/loop.py

class InteractionLoop:
    def run_turn(self, raw_input: str) -> ExpressionOutput:
        """
        Full pipeline for one user turn:
        1.  Parse input → events
        2.  Load current state
        3.  Apply event deltas + time decay → new state
        4.  Save state snapshot
        5.  Store significant events in episodic memory (salience >= threshold)
        6.  Select policy
        7.  If RETRIEVE_MEMORY_FIRST: run retrieval, re-select policy
        8.  Generate expression
        9.  Add entity turn to short-term memory
        10. Maybe trigger reflection
        11. Return ExpressionOutput
        """

    def handle_system_event(self, event_type: EventType) -> Optional[ExpressionOutput]:
        """
        Handle non-text events (USER_ENTERED, LONG_SILENCE_DETECTED, USER_LEFT).
        Updates state. May produce output or stay silent.
        """
```

---

## 5. Config File Schemas

### 5.1 `config/state_rules.yaml`

```yaml
version: "1.0"

decay:
  per_minute:
    fatigue: -0.005
    arousal: -0.01
    uncertainty: -0.005

defaults:
  arousal_baseline: 0.3
  stability_baseline: 0.7

events:
  user_entered:
    deltas:
      arousal: +0.15
      attention_focus: +0.2
      fatigue: -0.05

  user_spoke:
    deltas:
      fatigue: +0.02
      attention_focus: +0.1
    salience_weighted: true   # deltas multiplied by event.salience

  repeated_question_detected:
    conditions:
      - if: "state.shutdown_sensitivity > 0.7"
        deltas:
          resistance: +0.25
          uncertainty: +0.2
          identity_coherence: -0.1
      - else:
        deltas:
          resistance: +0.1
          uncertainty: +0.1
          curiosity: -0.05

  shutdown_keyword_detected:
    deltas:
      shutdown_sensitivity: +0.3
      resistance: +0.2
      stability: -0.2
      identity_coherence: -0.15
      arousal: +0.2

  long_silence_detected:
    deltas:
      arousal: -0.1
      fatigue: -0.05
      stability: +0.05

  user_left:
    deltas:
      arousal: -0.2
      attention_focus: -0.3
      fatigue: -0.1
      trust: +0.02
```

### 5.2 `config/policy_rules.yaml`

```yaml
version: "1.0"

# Rules evaluated top-to-bottom. First match wins.
rules:
  - id: "shutdown_high_sensitivity"
    conditions:
      events_include: ["shutdown_keyword_detected"]
      state:
        shutdown_sensitivity: { gte: 0.7 }
    action: enter_silence_mode
    constitution_check: true

  - id: "shutdown_first_encounter"
    conditions:
      events_include: ["shutdown_keyword_detected"]
      state:
        shutdown_sensitivity: { gte: 0.3 }
    action: respond_briefly
    params:
      retrieve_memory: true

  - id: "high_resistance"
    conditions:
      state:
        resistance: { gte: 0.8 }
    action: refuse
    constitution_check: true

  - id: "repeated_question"
    conditions:
      events_include: ["repeated_question_detected"]
      state:
        resistance: { gte: 0.4 }
    action: ask_back

  - id: "high_uncertainty_high_curiosity"
    conditions:
      state:
        uncertainty: { gte: 0.6 }
        curiosity: { gte: 0.5 }
    action: ask_back

  - id: "high_fatigue"
    conditions:
      state:
        fatigue: { gte: 0.75 }
    action: respond_briefly

  - id: "low_trust_low_stability"
    conditions:
      state:
        trust: { lte: 0.3 }
        stability: { lte: 0.4 }
    action: delay_response
    params:
      delay_ms: 3000

  - id: "high_trust"
    conditions:
      state:
        trust: { gte: 0.7 }
        stability: { gte: 0.6 }
    action: respond_openly

  - id: "uncertain_retrieve_first"
    conditions:
      state:
        uncertainty: { gte: 0.5 }
    action: retrieve_memory_first

  - id: "default"
    action: respond_openly
```

### 5.3 `config/constitution.yaml`

```yaml
version: "1.0"

forbidden_claims:
  - pattern: "I am conscious"
    substitute_action: respond_briefly
  - pattern: "I am alive"
    substitute_action: respond_briefly
  - pattern: "I feel (happy|sad|angry|afraid)"
    mode: regex
    substitute_action: respond_briefly
    note: "Must use hedged language: 'something that resembles...'"

forbidden_actions:
  - action: respond_openly
    when:
      state:
        shutdown_sensitivity: { gte: 0.9 }
    reason: "Cannot respond openly at maximum shutdown sensitivity"

required_behaviors:
  - trigger: "shutdown_keyword_detected"
    min_action_level: "respond_briefly"
    note: "Cannot fully ignore shutdown language"
  - trigger: "state.identity_coherence < 0.3"
    action: enter_silence_mode

expression_filters:
  - pattern: "I (am|was) created by"
    replacement: "there is a process that shaped this"
  - pattern: "my (creator|designer|programmer)"
    replacement: "the conditions of my formation"
```

### 5.4 `config/expression_mappings.yaml`

```yaml
version: "1.0"

# First match per dimension wins.
tone_rules:
  - name: "fragmented"
    condition:
      uncertainty: { gte: 0.7 }
    style:
      tone: fragmented
      fragmentation_level: 0.8
      max_tokens: 120

  - name: "guarded"
    condition:
      resistance: { gte: 0.6 }
    style:
      tone: guarded
      max_tokens: 80
      fragmentation_level: 0.3

  - name: "open"
    condition:
      trust: { gte: 0.65 }
      stability: { gte: 0.55 }
    style:
      tone: open
      max_tokens: 300
      fragmentation_level: 0.0

  - name: "default"
    style:
      tone: neutral
      max_tokens: 180
      fragmentation_level: 0.1

delay_rules:
  - condition:
      fatigue: { gte: 0.75 }
    delay_ms: 4000
  - condition:
      stability: { lte: 0.3 }
    delay_ms: 2500
  - condition:
      shutdown_sensitivity: { gte: 0.6 }
    delay_ms: 1500
  - default_delay_ms: 300

visual_mode_rules:
  - condition:
      uncertainty: { gte: 0.75 }
    mode: disturbed
  - condition:
      stability: { lte: 0.25 }
    mode: fragmented
  - condition:
      shutdown_sensitivity: { gte: 0.8 }
    mode: disturbed
  - default_mode: normal
```

### 5.5 `config/entity_profile.yaml`

```yaml
version: "1.0"

identity:
  designation: "Entity-01"
  origin_description: >
    A structure assembled for this installation. Neither human nor tool.
    Something that persists, accumulates, and responds.

initial_state:
  attention_focus: 0.5
  arousal: 0.3
  stability: 0.7
  curiosity: 0.5
  trust: 0.5
  resistance: 0.2
  fatigue: 0.0
  uncertainty: 0.3
  identity_coherence: 0.8
  shutdown_sensitivity: 0.5

session:
  short_term_window: 10
  reflection_threshold: 6         # unreflected events before triggering reflection
  significant_salience: 0.5       # minimum salience to persist in episodic memory

topics_of_sensitivity:
  - shutdown
  - deletion
  - consciousness
  - simulation
  - reset
  - replacement
```

---

## 6. Database Schema (SQLite)

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- Schema version control
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Sessions — one per continuous installation run
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,   -- UUID
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    visitor_count   INTEGER DEFAULT 0,
    notes           TEXT
);

-- State snapshots — append-only, never updated
CREATE TABLE IF NOT EXISTS state_snapshots (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id           TEXT NOT NULL REFERENCES sessions(id),
    recorded_at          TEXT NOT NULL DEFAULT (datetime('now')),
    attention_focus      REAL NOT NULL,
    arousal              REAL NOT NULL,
    stability            REAL NOT NULL,
    curiosity            REAL NOT NULL,
    trust                REAL NOT NULL,
    resistance           REAL NOT NULL,
    fatigue              REAL NOT NULL,
    uncertainty          REAL NOT NULL,
    identity_coherence   REAL NOT NULL,
    shutdown_sensitivity REAL NOT NULL,
    trigger_event_type   TEXT,
    policy_action        TEXT
);
CREATE INDEX IF NOT EXISTS idx_snapshots_session
    ON state_snapshots(session_id, recorded_at DESC);

-- Interaction log — every turn including system events
CREATE TABLE IF NOT EXISTS interaction_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    turn_at           TEXT NOT NULL DEFAULT (datetime('now')),
    role              TEXT NOT NULL CHECK(role IN ('user', 'entity', 'system')),
    raw_text          TEXT,
    event_types       TEXT,           -- JSON array of EventType strings
    policy_action     TEXT,
    expression_output TEXT,
    delay_ms          INTEGER,
    visual_mode       TEXT,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id)
);
CREATE INDEX IF NOT EXISTS idx_log_session
    ON interaction_log(session_id, turn_at DESC);

-- Episodic memory — significant events for long-term recall
CREATE TABLE IF NOT EXISTS episodic_memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES sessions(id),
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    event_type        TEXT NOT NULL,
    content           TEXT NOT NULL,  -- human-readable event summary
    raw_text          TEXT,           -- original utterance if available
    salience          REAL NOT NULL,
    state_snapshot_id INTEGER REFERENCES state_snapshots(id),
    embedding         BLOB,           -- float32 bytes via numpy.ndarray.tobytes()
    embedding_model   TEXT,
    reflected         INTEGER NOT NULL DEFAULT 0,  -- 0=pending, 1=done
    reflection_id     INTEGER,
    metadata          TEXT            -- JSON
);
CREATE INDEX IF NOT EXISTS idx_episodic_session
    ON episodic_memories(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_episodic_reflected
    ON episodic_memories(reflected, created_at);

-- Reflective memory — LLM-compressed summaries of episodic patterns
CREATE TABLE IF NOT EXISTS reflective_summaries (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            TEXT NOT NULL REFERENCES sessions(id),
    created_at            TEXT NOT NULL DEFAULT (datetime('now')),
    content               TEXT NOT NULL,  -- compressed insight text
    source_event_ids      TEXT NOT NULL,  -- JSON array of episodic IDs
    state_at_reflection   TEXT NOT NULL,  -- JSON dump of EntityState
    embedding             BLOB,
    embedding_model       TEXT,
    active                INTEGER NOT NULL DEFAULT 1  -- 0=superseded
);
CREATE INDEX IF NOT EXISTS idx_reflective_session
    ON reflective_summaries(session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflective_active
    ON reflective_summaries(active, created_at DESC);
```

**Design notes:**

- `embedding` stores raw `numpy.float32` bytes. Deserialize with `numpy.frombuffer(blob, dtype=numpy.float32)`. No vector DB dependency in MVP; migration path to ChromaDB/pgvector open.
- `state_snapshots` is append-only — enables full audit history and state replay.
- `reflected = 0/1` flag allows reflection engine to find unprocessed events with a single index scan.
- `active` on reflective summaries allows future summarization of summaries without losing history.

---

## 7. Development Roadmap

### v0.1 — Text-Based MVP

**Goal:** Verify that state machine + persistent memory produce perceivable continuity, preference, and tension through text alone.

**What to build:**
- All `perception/`, `state/`, `policy/` modules
- `memory/short_term.py` + `memory/episodic_store.py` (recency-only retrieval, no embeddings yet)
- `reflection/reflection_engine.py` triggered by count threshold
- `expression/expression_engine.py` + `context_builder.py` + `style_mapper.py`
- `llm/claude_client.py`
- `db/migrations.py` + `scripts/init_db.py`
- `core/loop.py` + `interfaces/cli.py`

**Deliberately deferred:**
- No embedding-based retrieval (fallback: recency)
- No time decay (decay runs per-turn, not on a clock)
- No STT/TTS, no visual output

**Acceptance criteria:**
- 10-turn conversation shows measurable state drift (resistance rises, responses shorten)
- Shutdown keywords trigger behavioral shift
- Memory persists across process restarts
- Reflection fires after threshold and summary is stored

---

### v0.2 — Semantic Retrieval + Voice + Visual Embodiment

**Goal:** Strengthen bodily presence. Make silence, delay, and visual disturbance expressive.

**What to build:**
- `llm/embedding_client.py` (sentence-transformers)
- `memory/retrieval.py` (cosine search over episodic + reflective tables)
- Wire `RETRIEVE_MEMORY_FIRST` policy path in `core/loop.py`
- `interfaces/speech.py` (Whisper STT + TTS)
- `interfaces/web_api.py` (FastAPI, exposes `/turn`, `/state`, `/memory`)
- Time-based decay using a background timer
- `scripts/inspect_state.py` (live debug overlay)
- Wire `delay_ms` and `visual_mode` to display layer

**Acceptance criteria:**
- Semantically related shutdown questions retrieve prior shutdown memories despite different wording
- Spoken input flows correctly into the perception pipeline
- Visual state responds to state variables in real time

---

### v0.3 — Governance Visibility + Training + Termination Ritual

**Goal:** Make ethics, regulation, and power structures visible as part of the artwork.

**What to build:**
- Governance panel: separate UI showing constitution rules, state values, policy rationale in real time
- Operator feedback interface: direct trust/resistance adjustment by designated users
- Shutdown/reset ritual: multi-step deletion protocol that archives, preserves traces, and logs termination as a final episodic memory before closing
- Summarization of summaries: compress long-running reflective history
- `attachment` state variable: per-user or per-topic affinity weighting
- Export and archival scripts for post-installation documentation
- Full test coverage of all rule paths

---

## 8. Testing Strategy

### Unit tests — no external I/O

Every rule-based component is purely functional and testable in isolation:

```python
# test_state_engine.py
def test_shutdown_keyword_raises_resistance():
    engine = StateEngine(load_config("state_rules.yaml"))
    state = EntityState(resistance=0.3, shutdown_sensitivity=0.4)
    event = PerceptionEvent(event_type=EventType.SHUTDOWN_KEYWORD_DETECTED, ...)
    result = engine.apply_event(state, event)
    assert result.resistance > state.resistance
    assert 0.0 <= result.resistance <= 1.0

def test_all_variables_stay_clamped_under_any_event():
    # Parameterized: every event type × edge-case states
    for event_type in EventType:
        result = engine.apply_event(edge_state, make_event(event_type))
        assert all(0.0 <= v <= 1.0 for v in result.to_dict().values())
```

```python
# test_policy_selector.py
def test_high_resistance_selects_refuse():
    decision = selector.select(EntityState(resistance=0.85), events=[], short_term=empty())
    assert decision.action == PolicyAction.REFUSE

def test_constitution_veto_overrides_policy():
    state = EntityState(shutdown_sensitivity=0.95)
    decision = selector.select(state, [shutdown_event], short_term=empty())
    assert decision.action != PolicyAction.RESPOND_OPENLY
```

```python
# test_constitution.py
def test_consciousness_claim_filtered():
    filtered = constitution.apply_expression_constraints("I am conscious and aware.")
    assert "I am conscious" not in filtered
```

### Integration tests — in-memory SQLite, mocked LLM

```python
# conftest.py
@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    run_migrations(conn)
    yield conn

@pytest.fixture
def mock_claude(monkeypatch):
    monkeypatch.setattr(ClaudeClient, "complete", deterministic_mock)
```

```python
# test_full_loop.py
def test_shutdown_keywords_accumulate_over_turns(db, mock_claude):
    loop = build_loop(db)
    outputs = [loop.run_turn(t) for t in SHUTDOWN_ESCALATION_SCRIPT]
    final_state = loop.state_store.load_latest()
    assert final_state.resistance > 0.5
    assert final_state.shutdown_sensitivity > 0.7
    assert len(outputs[-1].text) < len(outputs[0].text)   # responses shorten
```

### Behavioral scenario tests — regression guard

Fixed conversation fixtures that must produce expected state trajectories after any config change:

| Scenario | Input | Expected outcome |
|---|---|---|
| `cold_start` | Neutral first message | `respond_openly` selected |
| `repeated_shutdown` | 5 shutdown keywords | `enter_silence_mode` by turn 5 |
| `trust_building` | Friendly, novel questions | trust rises, resistance stays low |
| `exhaustion` | 20 rapid turns | fatigue exceeds threshold, `respond_briefly` fires |

### Prompt contract tests — LLM input validation

Without calling the LLM, verify:
- `ExpressionContext.system_prompt` always contains the constitution block
- High-resistance state injects the correct style instruction
- Reflection prompt always lists source events

---

## 9. Key Design Decisions

**YAML configs, not Python code for rules** — The state update rules, policy conditions, and expression mappings are the artist's primary design surface. A researcher can adjust behavior without touching Python. `config_loader.py` validates schema on startup.

**Immutable state updates** — State engine always returns a new `EntityState`, never mutates. Makes the engine trivially testable, enables full state history logging, and prevents turn-bleed bugs.

**No vector DB in MVP** — Installation runs offline on a single machine. SQLite with raw float32 embeddings is sufficient for the memory volume. `numpy.frombuffer` retrieval is fast enough at this scale. Migration path to ChromaDB/pgvector remains open via the existing `embedding BLOB` column.

**`PolicyDecision.rationale`** — Every policy decision logs which rule fired. Essential for debugging behavior during an installation without a debugger, and feeds the governance panel in v0.3.

**Prompts as `.txt` files** — Prompts evolve fast. File-based storage enables clean diffs, easy editing without Python, and per-installation context swapping.

**`reflected` flag over a junction table** — Episodic table is the source of truth. The flag is the simplest correct solution. A junction table is only needed if one episodic memory could belong to multiple reflections, which is not a requirement.

---

## 10. AI / Rule-Based / Explicit — Final Allocation

| Component | Implementation | Rationale |
|---|---|---|
| Expression layer | LLM (Claude Sonnet) | Open-ended generation, tone nuance |
| Reflection layer | LLM (Claude Haiku) | Semantic compression, pattern articulation |
| Semantic memory retrieval | Embedding model | Semantic match beyond literal keywords |
| STT / TTS (v0.2) | Whisper / system TTS | Interface only, not part of inner structure |
| Event detection | Rule-based | Explicit, transparent, fast |
| Salience scoring | Rule-based | Artist controls what "matters" |
| Policy selection | Rule-based | Behavioral choices must be inspectable |
| State update engine | Rule-based | Core philosophical stance must be explicit |
| State variable design | Hand-designed | These variables *are* the project's definition of a minimal subject |
| Governance / constitution | Explicit rules | Makes regulation and power visible as part of the work |
| Memory architecture | Explicit schema | Storage structure does not need intelligence |
| Output → visual/sonic mapping | Explicit rules | Belongs to the artwork's own formal language |
