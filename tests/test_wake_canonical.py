from __future__ import annotations

import unittest


def canonical_api():
    try:
        from eml_wake.canonical import canonical_bytes, digest_ref, loads_strict
        from eml_wake.errors import WakeError
    except ModuleNotFoundError as exc:
        raise AssertionError("eml_wake canonical profile is not implemented") from exc
    return canonical_bytes, digest_ref, loads_strict, WakeError


class CanonicalTests(unittest.TestCase):
    def test_duplicate_key_is_rejected_before_normalization(self):
        _, _, loads_strict, WakeError = canonical_api()
        with self.assertRaises(WakeError) as caught:
            loads_strict(b'{"wake_id":"a","wake_id":"b"}')
        self.assertEqual(caught.exception.code, "duplicate_key")

    def test_float_and_nonfinite_numbers_are_rejected(self):
        _, _, loads_strict, WakeError = canonical_api()
        for raw in (b'{"cost":0.5}', b'{"cost":NaN}', b'{"cost":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(WakeError) as caught:
                loads_strict(raw)
            self.assertEqual(caught.exception.code, "unsupported_number")

    def test_nfc_canonical_bytes_and_domain_digest_are_pinned(self):
        canonical_bytes, digest_ref, _, _ = canonical_api()
        value = {"b": "e\u0301", "a": 1}
        self.assertEqual(canonical_bytes(value), '{"a":1,"b":"é"}'.encode("utf-8"))
        self.assertEqual(
            digest_ref(value),
            "sha256:eml-wake-json-nfc-codepoint-v1:"
            "7e40a906dd74c3643094ab9d50919d361b0c7a0e1e1a551553c8fc564c958003",
        )

    def test_normalized_key_collision_is_rejected(self):
        canonical_bytes, _, _, WakeError = canonical_api()
        with self.assertRaises(WakeError) as caught:
            canonical_bytes({"é": 1, "e\u0301": 2})
        self.assertEqual(caught.exception.code, "normalized_key_collision")

    def test_bom_and_trailing_bytes_are_rejected(self):
        _, _, loads_strict, WakeError = canonical_api()
        for raw in (b'\xef\xbb\xbf{}', b'{}\n{}'):
            with self.subTest(raw=raw), self.assertRaises(WakeError) as caught:
                loads_strict(raw)
            self.assertIn(caught.exception.code, {"bom_not_allowed", "invalid_json"})


if __name__ == "__main__":
    unittest.main()
