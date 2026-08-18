# Deliberate gaps

Everything below is intentionally unimplemented. The project **runs today**
without them (offline mock provider, in-memory evidence, deterministic
detectors). Fill these in and it becomes a production system with no
architectural changes.

Every gap is marked in code with `TODO[FILL]`.

| # | File | What's missing | Why it's left open | Effort |
|---|------|----------------|--------------------|--------|
| 1 | `.env` | Provider API keys | Secrets never belong in a repo | 1 min |
| 2 | `controlplane/generation/openai_provider.py` | `complete()` body | Needs a paid key; reference impl is in the docstring | 15 min |
| 3 | `controlplane/generation/anthropic_provider.py` | `complete()` body | As above | 15 min |
| 4 | `config/models.yaml` | Real models + prices | Pricing changes constantly; must reflect your contract | 30 min |
| 5 | `controlplane/checker/performance.py` → `LLMVerifier.verify()` | Independent verifier call | Must use a *different* model than the generator | 1 hr |
| 6 | `controlplane/evidence/store.py` → `VectorEvidenceStore` | Embedding retrieval | Depends on your vector DB choice | 2 hrs |
| 7 | `controlplane/checker/detectors/fairness.py` → `comparative_fairness()` | Cohort outcome comparison | Impossible from text alone — needs your historical decision data | 1 day |
| 8 | `controlplane/action/executors.py` | Real executors | These move real money; must be written per organisation | 1 day |
| 9 | `config/policies.yaml` → `actions`, `safety` | Your action registry + prohibited content | Organisation-specific by definition | 1 day |
| 10 | `controlplane/human/queue.py` → `set_notifier()` | Slack/PagerDuty hook | Depends on your paging stack | 1 hr |
| 11 | `controlplane/learning/feedback.py` → `retrain_router()` | Fold observed reliability into routing | Needs production volume before it means anything | 3 days |
| 12 | `controlplane/checker/detectors/pii.py` → `PATTERNS` | Region-specific IDs (Aadhaar, PAN, IBAN…) | Depends on the jurisdictions you operate in | 2 hrs |

## Fail-safe behaviour

The gaps fail **closed**, never open:

- `LLMVerifier.available = False` → the ladder simply stops at evidence. Nothing
  is silently marked verified.
- An action missing from `policies.yaml` → `BLOCK` at the intent stage.
- An action with no registered executor → `HOLD` for a human.
- An unclassified PII class → `HOLD`, not allow.
- `VectorEvidenceStore.retrieve()` raises rather than returning empty evidence,
  so a misconfiguration can never look like "nothing to check".
