import json
import unittest

from src.common import response as resp
from test import fixtures as fx


class ResponseTests(unittest.TestCase):
    def test_envelope_prefix_comments_and_multiple_chunks(self) -> None:
        """To decode nested anti-XSSI envelopes and concatenated response chunks without evaluation."""

        body = json.dumps({"d": ")]}'\n[1] /* separator */ [2]"})
        self.assertEqual(resp.decode_payloads(body), [[1], [2]])

    def test_malformed_bodies(self) -> None:
        """To reject empty bodies, unterminated comments, and unsupported JSON shapes."""

        for body in ("", "not JSON", "/* unfinished", '{"error": "blocked"}', '"string"'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                resp.decode_payloads(body)

    def test_profile_normalization_and_missing_fields(self) -> None:
        """To normalize a captured profile and handle missing optional fields without inventing values."""

        place = resp.normalize_place(fx.place_record())
        self.assertEqual(place["place_id"], "place-1")
        self.assertEqual(place["categories"], ["Italian restaurant"])
        self.assertEqual(place["phone"], "+1 555 0100")
        self.assertEqual(place["latitude"], 40.7)
        missing = resp.normalize_place([])
        self.assertIsNone(missing["rating"])
        self.assertEqual(missing["categories"], [])
        self.assertIsNone(resp.number_value(True))
        self.assertIsNone(resp.number_value(float("nan")))

    def test_place_entries_do_not_share_mutable_defaults(self) -> None:
        """To initialize independent review and raw lists without modifying the supplied profile."""

        place = {"name": "Example", "rank": 99}
        first, second = resp.build_place_entry(place, 1), resp.build_place_entry(place, 2)
        first["reviews"].append({"review_id": "r1"})
        self.assertEqual(second["reviews"], [])
        self.assertNotIn("rank", first["place"])
        self.assertEqual(place["rank"], 99)


if __name__ == "__main__":
    unittest.main()
