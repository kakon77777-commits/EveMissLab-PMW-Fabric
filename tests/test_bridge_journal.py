from __future__ import annotations

import tempfile
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.journal import SQLiteJournal
from eml_bridge.message import new_message
from eml_bridge.models import DeliveryState


class JournalTests(unittest.TestCase):
    def test_idempotent_same_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = SQLiteJournal(Path(tmp) / "j.sqlite3")
            m = new_message(sender="agent://evemisslab/a", recipient="agent://evemisslab/b", text="x")
            self.assertEqual(journal.journal_message(m), m["message_id"])
            self.assertEqual(journal.journal_message(m), m["message_id"])
            journal.close()

    def test_illegal_transition_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = SQLiteJournal(Path(tmp) / "j.sqlite3")
            m = new_message(sender="agent://evemisslab/a", recipient="agent://evemisslab/b", text="x")
            journal.journal_message(m)
            journal.ensure_delivery(m["message_id"], "agent://evemisslab/b")
            with self.assertRaises(ValueError):
                journal.transition_delivery(m["message_id"], "agent://evemisslab/b", DeliveryState.ACKNOWLEDGED)
            journal.close()


if __name__ == "__main__":
    unittest.main()
