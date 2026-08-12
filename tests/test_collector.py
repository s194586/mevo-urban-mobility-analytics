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
            {"name": "station_information", "url": "https://example.test/station-information.json"},
            {"name": "vehicle_types", "url": "https://example.test/vehicle-types.json"},
        ]}}}

    def test_default_collect_snapshot_fetches_only_dynamic_feeds(self):
        opener = Mock(side_effect=[
            response(self.discovery),
            response({"data": {"stations": []}}),
            response({"data": {"bikes": []}}),
        ])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertEqual(set(result.feeds), {"station_status", "free_bike_status"})
        self.assertEqual(opener.call_count, 3)

    def test_reference_feeds_and_records(self):
        opener = Mock(side_effect=[
            response(self.discovery),
            response({"data": {"stations": [{"station_id": "1"}]}}),
            response({"data": {"vehicle_types": [{"vehicle_type_id": "bike"}]}}),
        ])
        result = collect_snapshot(
            MevoApi(opener=opener, retries=0),
            feed_names=("station_information", "vehicle_types"),
        )
        self.assertEqual(result.feeds["station_information"].records, [{"station_id": "1"}])
        self.assertEqual(result.feeds["vehicle_types"].records, [{"vehicle_type_id": "bike"}])

    def test_reference_feed_validation_uses_expected_record_keys(self):
        opener = Mock(side_effect=[
            response(self.discovery),
            response({"data": {"bikes": []}}),
        ])
        result = collect_snapshot(
            MevoApi(opener=opener, retries=0),
            feed_names=("station_information",),
        )
        self.assertEqual(result.errors, {
            "station_information": "station_information response has no data.stations collection",
        })

        opener = Mock(side_effect=[
            response(self.discovery),
            response({"data": {"stations": []}}),
        ])
        result = collect_snapshot(
            MevoApi(opener=opener, retries=0),
            feed_names=("vehicle_types",),
        )
        self.assertEqual(result.errors, {
            "vehicle_types": "vehicle_types response has no data.vehicle_types collection",
        })

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
        error = HTTPError("https://example.test", 404, "not found", {}, None)
        opener = Mock(side_effect=error)
        with self.assertRaises(ApiError):
            MevoApi(opener=opener, retries=2, backoff=0).get_json("https://example.test")
        self.assertEqual(opener.call_count, 1)

    def test_http_5xx_retries_then_succeeds(self):
        error = HTTPError("https://example.test", 503, "unavailable", {}, None)
        opener = Mock(side_effect=[error, response({"data": {}})])
        result = MevoApi(opener=opener, retries=1, backoff=0).get_json("https://example.test")
        self.assertEqual(result.payload, {"data": {}})
        self.assertEqual(opener.call_count, 2)

    def test_common_collected_at_and_partial_failure(self):
        opener = Mock(side_effect=[
            response(self.discovery),
            response({"last_updated": 10, "data": {"stations": [{"station_id": "1"}]}}),
            ApiError("temporary failure"),
        ])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertEqual(set(result.feeds), {"station_status"})
        self.assertIn("free_bike_status", result.errors)
        self.assertTrue(result.partial_failure)
        self.assertFalse(result.total_failure)
        self.assertEqual(result.feeds["station_status"].collected_at, result.collected_at)
        self.assertIsNotNone(result.collected_at.tzinfo)

    def test_empty_collections_are_valid(self):
        opener = Mock(side_effect=[response(self.discovery), response({"data": {"stations": [{}]}}), response({"data": {"bikes": []}})])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertIn("free_bike_status", result.feeds)
        self.assertEqual(result.feeds["free_bike_status"].records, [])

        opener = Mock(side_effect=[response(self.discovery), response({"data": {"stations": []}}), response({"data": {"bikes": [{}]}})])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertEqual(set(result.feeds), {"station_status", "free_bike_status"})
        self.assertEqual(result.feeds["station_status"].records, [])

    def test_total_failure_for_two_api_errors(self):
        opener = Mock(side_effect=[response(self.discovery), ApiError("stations failed"), ApiError("bikes failed")])
        result = collect_snapshot(MevoApi(opener=opener, retries=0))
        self.assertTrue(result.total_failure)
        self.assertFalse(result.partial_failure)
        self.assertEqual(len(result.errors), 2)

    def test_unexpected_programming_error_is_not_swallowed(self):
        opener = Mock(side_effect=[response(self.discovery), RuntimeError("bug")])
        with self.assertRaises(RuntimeError):
            collect_snapshot(MevoApi(opener=opener, retries=0))


if __name__ == "__main__":
    unittest.main()
