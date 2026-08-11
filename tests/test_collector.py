import json
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock

from mevo_collector import ApiError, MevoApi, collect_snapshot


def response(body: dict, url: str = "https://example.test/feed.json") -> Mock:
    item = Mock()
    item.status = 200
    item.getcode.return_value = 200
    item.read.return_value = json.dumps(body, separators=(",", ":")).encode()
    item.__enter__ = Mock(return_value=item)
    item.__exit__ = Mock(return_value=None)
    return item


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.discovery = {"data": {"pl": {"feeds": [
            {"name": "station_status", "url": "https://example.test/stations.json"},
            {"name": "free_bike_status", "url": "https://example.test/bikes.json"},
        ]}}}

    def test_discovery_header_status_and_raw_bytes(self):
        opener = Mock(side_effect=[response(self.discovery), response({"data": {"stations": [{}]}})])
        api = MevoApi(opener=opener, retries=0)
        result = api.get_feed(api.get_discovery().payload, "station_status")
        self.assertEqual(result.raw_bytes, b'{"data":{"stations":[{}]}}')
        self.assertEqual(dict(opener.call_args_list[0].args[0].header_items())["Client-identifier"], "maciej-mevo-analytics")
        self.assertEqual(api.feed_url(self.discovery, "station_status"), "https://example.test/stations.json")

    def test_invalid_json_raises(self):
        bad = response({})
        bad.read.return_value = b"not-json"
        with self.assertRaises(ApiError):
            MevoApi(opener=Mock(return_value=bad), retries=0).get_json("https://example.test")

    def test_http_error_raises_api_error(self):
        with self.assertRaises(ApiError):
            error = HTTPError("https://example.test", 404, "not found", {}, None)
            MevoApi(opener=Mock(side_effect=error), retries=0).get_json("https://example.test")

    def test_common_collected_at_and_partial_failure(self):
        opener = Mock(side_effect=[
            response(self.discovery),
            response({"last_updated": 10, "data": {"stations": [{"station_id": "1"}]}}),
            ApiError("temporary failure"),
        ])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertEqual(set(result.feeds), {"station_status"})
        self.assertIn("free_bike_status", result.errors)
        self.assertEqual(result.feeds["station_status"].collected_at, result.collected_at)
        self.assertIsNotNone(result.collected_at.tzinfo)

    def test_free_bike_validation(self):
        opener = Mock(side_effect=[response(self.discovery), response({"data": {"bikes": []}}), response({"data": {"bikes": [{}]}})])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertIn("station_status", result.errors)
        self.assertIn("free_bike_status", result.feeds)


if __name__ == "__main__":
    unittest.main()
