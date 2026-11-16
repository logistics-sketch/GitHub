import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from exchange_reminders import KYIV, ReminderStore, parse_feed, dispatch, start_exchange_reminders

NOW = datetime(2026, 11, 16, 10, 0, tzinfo=KYIV)
def item(**kwargs):
    r = dict(request_number="0007100", sku="001009", appeal="Обмін",
        classification="особисті обставини після 14 днів", draft=False,
        received=None, credited=None)
    r.update(kwargs)
    return r
def feed(*items):
    return dict(complete=True, generated_at=NOW.isoformat(), items=list(items))

class Reminders(unittest.TestCase):
    def test_unknown_and_sku(self):
        text=parse_feed(feed(item()), NOW)["0007100"]
        self.assertIn("отримання не підтверджено",text)
        self.assertIn("001009",text)
    def test_received_pending_credit(self):
        text=parse_feed(feed(item(received=True,evidence="intake")),NOW)["0007100"]
        self.assertIn("завершити зарахування",text)
        self.assertNotIn("Передати товар",text)
    def test_closed_cancelled(self):
        for r in [item(received=True,credited=True,evidence="receipt+credit"),item(cancelled=True)]:
            self.assertIsNone(parse_feed(feed(r),NOW)["0007100"])
    def test_evidence_and_types(self):
        for r in [item(received=False),item(sku=1009),item(draft=True)]:
            with self.assertRaises(ValueError): parse_feed(feed(r),NOW)
    def test_incomplete_stale_duplicate(self):
        p=feed(item());p["generated_at"]="2026-11-10T10:00:00+02:00"
        for data in [dict(complete=False),p,feed(item(),item())]:
            with self.assertRaises(ValueError): parse_feed(data,NOW)
    def test_before14_and_missing_sku(self):
        self.assertEqual(parse_feed(feed(item(classification="особисті обставини (в межах 14 днів)")),NOW),{})
        self.assertIn("код не вказано",parse_feed(feed(item(sku=None)),NOW)["0007100"])
    def test_cycle_restart_month(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.sqlite3";s=ReminderStore(p)
            self.assertEqual(s.cycle(NOW),"2026-11-16")
            s=ReminderStore(p)
            self.assertIsNone(s.cycle(datetime(2026,11,17,10,tzinfo=KYIV)))
            self.assertEqual(s.cycle(datetime(2026,11,18,10,tzinfo=KYIV)),"2026-11-18")
            self.assertIsNone(s.cycle(datetime(2026,11,18,9,tzinfo=KYIV)))
            self.assertEqual(s.cycle(datetime(2026,12,2,10,tzinfo=KYIV)),"2026-12-02")
    def test_dedupe_failure_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            s=ReminderStore(Path(d)/"state.sqlite3")
            for n,u in [(1,"rubyukdi"),(2,"irynaverb"),(3,"kristy_r")]: s.register(n,u)
            calls=[]
            def send(chat,text):
                calls.append(chat)
                if chat==2: raise TimeoutError()
            r=parse_feed(feed(item()),NOW)
            self.assertEqual(dispatch(s,r,{1,2},"2026-11-16",send),1)
            self.assertEqual(calls,[1,2])
            self.assertEqual(dispatch(s,r,{1,2},"2026-11-16",send),0)
            self.assertEqual(dispatch(s,r,{1,2},"2026-11-17",send),0)
            self.assertEqual(dispatch(s,r,{1,2},"2026-11-18",send),1)
    def test_disabled_missing_configuration(self):
        self.assertIsNone(start_exchange_reminders(object(),{}))
        self.assertIsNone(start_exchange_reminders(object(),{"EXCHANGE_REMINDERS_ENABLED":"true"}))
if __name__=="__main__": unittest.main()
