"""Pure parser checks that do not require a Home Assistant installation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest


MODELS_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "makerworld_library"
    / "models.py"
)
SPEC = importlib.util.spec_from_file_location("makerworld_models", MODELS_PATH)
models = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = models
SPEC.loader.exec_module(models)


class ParserTests(unittest.TestCase):
    def test_collection_and_p2s_profile_are_normalized(self) -> None:
        summary = {
            "id": 123,
            "title": "Example",
            "slug": "example",
            "cover": "https://example.invalid/cover.png",
        }
        detail = {
            **summary,
            "modelId": "USexample",
            "instances": [
                {
                    "id": 456,
                    "profileId": 789,
                    "title": "0.2 mm",
                    "needAms": False,
                    "instanceFilaments": [{"type": "PLA"}],
                    "extention": {
                        "modelInfo": {
                            "compatibility": {"devProductName": "A1"},
                            "plates": [{"prediction": 100}],
                        },
                        "otherCompatibilityModelInfo": [
                            {
                                "devProductName": "P2S",
                                "profileId": 999,
                                "prediction": 90,
                            }
                        ],
                    },
                }
            ],
        }
        model = models.parse_model(summary, detail)
        self.assertEqual(model.design_id, 123)
        self.assertEqual(model.materials, ("PLA",))
        self.assertTrue(model.p2s_compatible)
        self.assertEqual(model.profiles[0].p2s_profile_id, 999)
        self.assertEqual(model.profiles[0].plate_count, 1)

    def test_summary_fallback_is_marked_partial(self) -> None:
        model = models.parse_model({"id": 12, "title": "Fallback"}, None)
        self.assertFalse(model.metadata_complete)
        self.assertEqual(model.profiles, ())


if __name__ == "__main__":
    unittest.main()
