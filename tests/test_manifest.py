from __future__ import annotations

import unittest

from agent_font_patcher.manifest import ManifestError, codepoint_to_int, load_manifest, parse_manifest


class ManifestTest(unittest.TestCase):
    def test_packaged_manifest_loads(self) -> None:
        manifest = load_manifest()

        self.assertEqual(manifest.project, "agent-font-patcher")
        self.assertEqual(manifest.manifest_version, "agent-icons-v8")
        self.assertEqual(manifest.range_start, "U+100000")
        self.assertEqual(manifest.range_end, "U+1000FF")
        self.assertIsNotNone(manifest.icon_by_id("codex"))
        self.assertIsNotNone(manifest.icon_by_id("orca-ade"))
        self.assertIsNotNone(manifest.icon_by_id("qwen-code"))
        self.assertEqual(manifest.icon_by_id("autohand-code").asset_status, "available")
        self.assertEqual(manifest.icon_by_id("charm").asset_status, "available")
        self.assertEqual(manifest.icon_by_id("codebuff").asset_status, "available")
        self.assertEqual(manifest.icon_by_id("agent-active").asset_status, "available")
        self.assertEqual(manifest.icon_by_id("tool-call").asset_status, "available")

    def test_codepoint_to_int_accepts_uppercase_pua_values(self) -> None:
        self.assertEqual(codepoint_to_int("U+100000"), 0x100000)

    def test_codepoint_to_int_rejects_lowercase_values(self) -> None:
        with self.assertRaises(ManifestError):
            codepoint_to_int("u+100000")

    def test_codepoint_to_int_rejects_values_above_unicode_max(self) -> None:
        with self.assertRaisesRegex(ManifestError, "exceeds Unicode maximum"):
            codepoint_to_int("U+110000")

    def test_codepoint_to_int_rejects_surrogates(self) -> None:
        with self.assertRaisesRegex(ManifestError, "surrogate"):
            codepoint_to_int("U+D800")

    def test_duplicate_icon_ids_are_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["icons"].append({**raw["icons"][0], "codepoint": "U+100001"})

        with self.assertRaisesRegex(ManifestError, "Duplicate icon id"):
            parse_manifest(raw)

    def test_duplicate_codepoints_are_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["icons"].append({**raw["icons"][0], "id": "agent-two"})

        with self.assertRaisesRegex(ManifestError, "Duplicate codepoint"):
            parse_manifest(raw)

    def test_equivalent_codepoint_strings_are_rejected_as_duplicates(self) -> None:
        raw = _minimal_manifest()
        raw["range"]["start"] = "U+F000"
        raw["range"]["end"] = "U+F0FF"
        raw["blocks"][0]["start"] = "U+F000"
        raw["blocks"][0]["end"] = "U+F0FF"
        raw["icons"][0]["codepoint"] = "U+F000"
        raw["icons"].append({**raw["icons"][0], "id": "agent-two", "codepoint": "U+0F000"})

        with self.assertRaisesRegex(ManifestError, "Duplicate codepoint"):
            parse_manifest(raw)

    def test_icon_outside_category_block_is_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["icons"][0]["codepoint"] = "U+100040"

        with self.assertRaisesRegex(ManifestError, "outside category block"):
            parse_manifest(raw)

    def test_manifest_root_must_be_object(self) -> None:
        with self.assertRaisesRegex(ManifestError, "root must be a JSON object"):
            parse_manifest([])

    def test_manifest_range_must_be_object(self) -> None:
        raw = _minimal_manifest()
        raw["range"] = []

        with self.assertRaisesRegex(ManifestError, "range must be an object"):
            parse_manifest(raw)

    def test_manifest_blocks_must_be_list(self) -> None:
        raw = _minimal_manifest()
        raw["blocks"] = {}

        with self.assertRaisesRegex(ManifestError, "blocks must be a list"):
            parse_manifest(raw)

    def test_manifest_icons_must_be_list(self) -> None:
        raw = _minimal_manifest()
        raw["icons"] = {}

        with self.assertRaisesRegex(ManifestError, "icons must be a list"):
            parse_manifest(raw)

    def test_schema_version_must_be_supported_integer(self) -> None:
        raw = _minimal_manifest()
        raw["schema_version"] = "1"

        with self.assertRaisesRegex(ManifestError, "schema_version"):
            parse_manifest(raw)

    def test_schema_version_rejects_boolean(self) -> None:
        raw = _minimal_manifest()
        raw["schema_version"] = True

        with self.assertRaisesRegex(ManifestError, "schema_version"):
            parse_manifest(raw)

    def test_block_outside_manifest_range_is_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["blocks"][0]["end"] = "U+100100"

        with self.assertRaisesRegex(ManifestError, "outside manifest range"):
            parse_manifest(raw)

    def test_overlapping_blocks_are_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["blocks"].append(
            {
                "name": "coding_agents",
                "start": "U+100020",
                "end": "U+10007F",
                "description": "Overlapping block.",
            }
        )

        with self.assertRaisesRegex(ManifestError, "overlaps"):
            parse_manifest(raw)

    def test_duplicate_block_names_are_rejected(self) -> None:
        raw = _minimal_manifest()
        raw["blocks"].append(
            {
                "name": "providers",
                "start": "U+100040",
                "end": "U+10007F",
                "description": "Duplicate block name.",
            }
        )

        with self.assertRaisesRegex(ManifestError, "Duplicate block name"):
            parse_manifest(raw)

    def test_available_icon_requires_source_license_and_attribution(self) -> None:
        raw = _minimal_manifest()
        raw["icons"][0]["asset_status"] = "available"

        with self.assertRaisesRegex(ManifestError, "must include source"):
            parse_manifest(raw)

    def test_asset_status_must_be_string(self) -> None:
        raw = _minimal_manifest()
        raw["icons"][0]["asset_status"] = []

        with self.assertRaisesRegex(ManifestError, "asset_status must be a string"):
            parse_manifest(raw)


def _minimal_manifest() -> dict:
    return {
        "schema_version": 1,
        "manifest_version": "agent-icons-test",
        "project": "agent-font-patcher",
        "range": {
            "start": "U+100000",
            "end": "U+1000FF",
            "description": "Test range.",
        },
        "blocks": [
            {
                "name": "providers",
                "start": "U+100000",
                "end": "U+10003F",
                "description": "Provider icons.",
            }
        ],
        "icons": [
            {
                "id": "agent-one",
                "display_name": "Agent One",
                "aliases": [],
                "category": "providers",
                "codepoint": "U+100000",
                "asset_status": "reserved",
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
