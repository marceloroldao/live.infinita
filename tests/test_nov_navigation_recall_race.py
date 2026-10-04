import json
import unittest
from unittest.mock import patch, MagicMock
import nov_navigation_recall_export as recall

class RecallRaceTests(unittest.TestCase):
    def fetch(self, responses):
        opener=MagicMock()
        returned=[]
        for data in responses:
            response=MagicMock()
            response.status=200
            response.read.return_value=json.dumps(data).encode()
            response.__enter__.return_value=response
            returned.append(response)
        opener.open.side_effect=returned
        with patch.dict("os.environ", {"MEMORIA_API_KEY":"isolated-test-key-"+"a"*32}), patch.object(recall,"build_opener",return_value=opener):
            result=recall.fetch_recent()
        return result,opener
    def test_bounded_headroom_accepts_concurrent_appends(self):
        result,opener=self.fetch([{"semantic_projection":False,"items":[{}]*67}])
        self.assertEqual(len(result["items"]),67)
        self.assertIn("limit=64",opener.open.call_args.args[0].full_url)
        self.assertEqual(opener.open.call_count,1)
    def test_oversized_window_retried_once_without_truncation(self):
        result,opener=self.fetch([{"semantic_projection":False,"items":[{}]*101},{"semantic_projection":False,"items":[{}]*64}])
        self.assertEqual(len(result["items"]),64)
        self.assertEqual(opener.open.call_count,2)
    def test_persistent_overflow_rejected(self):
        with self.assertRaisesRegex(recall.NavigationSyncError,"window_raced_after_retry"):
            self.fetch([{"semantic_projection":False,"items":[{}]*101}]*2)
    def test_invalid_contract_not_relaxed(self):
        for data in ({"semantic_projection":True,"items":[]},{"semantic_projection":False,"items":{}},[]):
            with self.subTest(data=data),self.assertRaisesRegex(recall.NavigationSyncError,"contract_invalid"):
                self.fetch([data])
    def test_maximum_accepted_window_is_still_100(self):
        result,_=self.fetch([{"semantic_projection":False,"items":[{}]*100}])
        self.assertEqual(len(result["items"]),100)
