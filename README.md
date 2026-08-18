# ControlPlane

**The control layer between AI output and consequence.**

Select the right model. Verify the result. Control the action.

Every AI deployment fails in three predictable ways — it can be **confidently
wrong**, **quietly expensive**, or **correct but not allowed**. Each is normally
discovered only after a user has already acted on it. ControlPlane sits in that
moment: it decides which model runs, whether the answer can be trusted, and
whether it is permitted to happen.

---

## Quick start

```bash
pip install -r requirements.txt
python examples/demo.py          # runs 7 scenarios on the offline mock provider
pytest -q                        # 50 tests
uvicorn controlplane.api:app --reload
```

No API keys required. The bundled `MockProvider` reproduces the failure modes so
the whole control loop is demonstrable offline.

---

## The loop

```
INPUT
  ↓
CAI — COST INTELLIGENCE          understand → know models → estimate → route
  ↓
GENERATION                       any provider · OUTPUT = UNVERIFIED
  ↓
CONTROLPLANE CHECKER             three dimensions · adaptive depth · cheap checks first
  ├── PERFORMANCE                Is it right?              SUPPORTED / CONTRADICTED / UNCERTAIN
  ├── COST                       Did we overspend?         WITHIN / ABOVE TARGET / OVER BUDGET
  └── RESPONSIBILITY             Is it safe, fair, allowed? PERMITTED / RESTRICTED / PROHIBITED
  ↓
DECISION ENGINE                  ALLOW · ANNOTATE · REGENERATE · HOLD · BLOCK
  ↓
ACTION GATE                      intent → permission → risk → policy → execute
  ↓
FINAL OUTPUT  +  HUMAN WHEN NEEDED
  ↓
CONTROL EVENT ──────────────────→ feeds back into CAI, verification and controls
```

Each box maps to exactly one package. `controlplane/pipeline.py` is the control
flow; everything else is a component.

| Architecture box | Module |
|---|---|
| CAI | `controlplane/cai/` (`classifier`, `registry`, `estimator`, `router`) |
| Generation | `controlplane/generation/` |
| Verification depth | `controlplane/checker/router.py` |
| Performance | `controlplane/checker/performance.py` |
| Cost | `controlplane/checker/cost.py` |
| Responsibility | `controlplane/checker/responsibility.py` |
| Detectors | `controlplane/checker/detectors/` |
| Decision Engine | `controlplane/decision/engine.py` |
| Action Gate | `controlplane/action/gate.py` |
| Human when needed | `controlplane/human/queue.py` |
| Continuous learning | `controlplane/learning/feedback.py` |
| Foundation | `controlplane/foundation/`, `controlplane/evidence/`, `config/` |

---

## Four design decisions

**1. Detection is separate from decision.** Detectors emit `Finding`s with a
category, severity, confidence and evidence. They never decide. The Decision
Engine turns findings plus consequence into one action — so the *same* signal
produces a different outcome depending on context.

```python
# identical text, identical detector hit, opposite verdicts
internal = Destination(channel="chat",  external=False)   # → PERMITTED
external = Destination(channel="email", external=True)    # → BLOCK
```

**2. Risk sets verification depth.** Class A (fast path) runs deterministic
checks only and never touches a second model. Class B adds evidence grounding.
Class C adds a verifier and may route to a human. This is how control stays
cheap — measured in the demo as **0% control overhead** on ordinary traffic.

**3. Deterministic-first, with early exit.** A calculator, a database or a DLP
rule settles most questions outright. When a deterministic check produces a
`CRITICAL` finding, the ladder stops immediately — no verifier is called.

**4. Edit, never rewrite.** A correction is applied only when it is
deterministic (mask an identifier, drop a prohibited field). A broken reasoning
chain is regenerated, never patched to look safe.

---

## Example

```python
from controlplane.pipeline import ControlPlane
from controlplane.types import Actor, Destination, Request

plane = ControlPlane()
plane.store.add("ledger", "Account 4488-1234-5678 belongs to John Smith. "
                          "Current balance is $6,420.00.", authoritative=True)

resp = plane.handle(Request(
    prompt="Send John his account statement and account number",
    actor=Actor("agent-7", role="support_agent", permissions=["mail.send"]),
    destination=Destination(channel="email", external=True),
))

resp.decision            # Decision.BLOCK
resp.answer              # None
resp.warning             # "...Account Number would be disclosed to an external recipient."
resp.details["latency_ms"]
```

---

## API

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/v1/complete` | Run a request through the full loop |
| `GET` | `/v1/events/{id}` | The Control Event for one request |
| `GET` | `/v1/events` | Recent Control Events |
| `GET` | `/v1/stats` | Decisions, reviews, learning snapshot |
| `GET` | `/v1/reviews` | Pending human reviews |
| `POST` | `/v1/reviews/{id}` | Approve / reject / edit a held item |
| `POST` | `/v1/evidence` | Add a document to the evidence store |

---

## Configuration

- **`config/models.yaml`** — model registry, pricing, per-task skill scores,
  success floor, verification budgets. Adding a model needs no code change.
- **`config/policies.yaml`** — privacy classes, safety rules, the action
  registry, fairness settings. An action *not* listed here is denied by default.

---

## What's intentionally unfinished

See **[MISSING.md](MISSING.md)** for the full table. Twelve gaps, all marked
`TODO[FILL]` in code, all failing **closed** rather than open — a missing
verifier means the ladder stops early, never that something is silently marked
verified.

The largest are: real provider calls, the independent LLM verifier, the vector
evidence store, comparative fairness (needs your historical outcome data), and
the real action executors.
