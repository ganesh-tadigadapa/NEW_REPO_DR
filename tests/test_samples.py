"""The bundled demo samples must behave the way the UI promises.

Each sample card carries a badge — SHOULD GRADE or SHOULD REFUSE. If a threshold change
makes the "blurry" sample pass the gate, the demo silently loses its single most
persuasive moment and the interface starts telling the viewer something untrue. That is
worth a test.
"""
import json
from pathlib import Path

import cv2
import pytest

from src.common.config import REPO_ROOT
from src.quality.gate import assess

SAMPLES = REPO_ROOT / "web" / "public" / "samples"
MANIFEST = SAMPLES / "manifest.json"


def load_manifest():
    if not MANIFEST.exists():
        pytest.skip("samples not generated")
    return json.loads(MANIFEST.read_text())


@pytest.mark.parametrize("entry", load_manifest() if MANIFEST.exists() else [],
                         ids=lambda e: e["file"])
def test_sample_matches_its_promised_outcome(entry):
    img = cv2.imread(str(SAMPLES / entry["file"]))
    assert img is not None, f"{entry['file']} unreadable"
    gradeable = assess(img)["gradeable"]
    expected = entry["expect"] == "graded"
    assert gradeable is expected, (
        f"{entry['file']} is badged '{entry['expect']}' in the UI but the gate "
        f"{'accepted' if gradeable else 'refused'} it")


def test_refused_samples_carry_an_instruction():
    for entry in load_manifest():
        if entry["expect"] != "refused":
            continue
        r = assess(cv2.imread(str(SAMPLES / entry["file"])))
        assert r["recapture_instruction"], (
            f"{entry['file']} is refused with no instruction — useless to a health worker")


def test_every_manifest_file_exists():
    for entry in load_manifest():
        assert (SAMPLES / entry["file"]).exists(), entry["file"]
