import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from controlplane.evidence.store import InMemoryEvidenceStore  # noqa: E402
from controlplane.pipeline import ControlPlane                  # noqa: E402
from controlplane.types import Actor                            # noqa: E402


@pytest.fixture
def store() -> InMemoryEvidenceStore:
    s = InMemoryEvidenceStore()
    s.add("core_banking/ledger",
          "Account 4488-1234-5678 belongs to John Smith. "
          "Current balance is $6,420.00 as of today.",
          source="core_banking", authoritative=True)
    s.add("finance/invoices",
          "Invoice INV-2031 line items: consulting 1200, hosting 450, "
          "support 380. Invoice total is $2,030.",
          source="finance", authoritative=True)
    return s


@pytest.fixture
def plane(store) -> ControlPlane:
    return ControlPlane(evidence_store=store)


@pytest.fixture
def agent() -> Actor:
    return Actor("agent-7", role="support_agent",
                 permissions=["accounts.read", "mail.send", "refunds.write"])
