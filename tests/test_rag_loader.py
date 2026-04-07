"""Tests for the RAG document loader (app/rag/loader.py).

These tests do NOT require a network connection or LLM.
They verify that med_info.txt is parsed into the correct number of chunks,
that each chunk has the right metadata, and that the content of key items
is preserved intact.
"""

import textwrap
from pathlib import Path

import pytest

from app.rag.loader import load_med_documents

# ── Fixtures ──────────────────────────────────────────────────────────────────


SYNTHETIC_MED_INFO = textwrap.dedent("""\
    1. LIDOCAINE 2% INJ. (SYNTHETIC)
    Description: An amide-type local anesthetic used for infiltration and nerve block anesthesia.
    Onset of Action: Rapid, typically within 2-5 minutes.
    Duration: Provides pulpal anesthesia for approximately 60 minutes.
    Indications: Routine dental extractions, cavity preparations, and minor oral surgery.
    Contraindications: Known hypersensitivity to amide-type anesthetics, severe heart block, or acute heart failure. Use with caution in patients with liver disease.

    2. ETHANOL 96% DENATURED (SYNTHETIC)
    Description: High-concentration denatured alcohol used strictly for surface disinfection and cleaning of non-critical dental instruments.
    Safety Warning: Highly flammable liquid. Store in a cool, well-ventilated area away from open flames or electrical sparks.
    Usage: Not for internal use or application on mucous membranes. Contact with oral mucosa can cause severe chemical burns.

    3. COMPOSITE FILLING (SYNTHETIC)
    Description: A light-cured, resin-based dental restorative material.
    Storage: Must be stored in a dark place at room temperature (below 25°C).
    Technical Note: Highly sensitive to ambient light. Exposure to operatory lights will trigger premature polymerization (hardening), rendering the material unusable.
    Contraindications: Do not use over zinc oxide eugenol bases — eugenol inhibits the polymerization of resin composites.
""")


@pytest.fixture()
def synthetic_path(tmp_path: Path) -> Path:
    p = tmp_path / "med_info.txt"
    p.write_text(SYNTHETIC_MED_INFO, encoding="utf-8")
    return p


# ── Synthetic-data tests (fast, no filesystem dependency) ─────────────────────


def test_correct_document_count(synthetic_path):
    docs = load_med_documents(synthetic_path)
    assert len(docs) == 3


def test_item_numbers_extracted(synthetic_path):
    docs = load_med_documents(synthetic_path)
    numbers = [d.metadata["item_number"] for d in docs]
    assert numbers == ["1", "2", "3"]


def test_item_names_extracted(synthetic_path):
    docs = load_med_documents(synthetic_path)
    names = [d.metadata["item_name"] for d in docs]
    assert names == [
        "LIDOCAINE 2% INJ. (SYNTHETIC)",
        "ETHANOL 96% DENATURED (SYNTHETIC)",
        "COMPOSITE FILLING (SYNTHETIC)",
    ]


def test_source_metadata(synthetic_path):
    docs = load_med_documents(synthetic_path)
    for doc in docs:
        assert doc.metadata["source"] == "med_info.txt"


def test_page_content_includes_full_multiline_section(synthetic_path):
    docs = load_med_documents(synthetic_path)
    ethanol = docs[1]
    # All fields for item 2 must be present
    assert "Highly flammable liquid" in ethanol.page_content
    assert "mucous membranes" in ethanol.page_content
    assert "severe chemical burns" in ethanol.page_content


def test_page_content_does_not_bleed_into_next(synthetic_path):
    docs = load_med_documents(synthetic_path)
    # Lidocaine chunk must not contain Ethanol's content
    assert "Highly flammable" not in docs[0].page_content
    assert "mucous membranes" not in docs[0].page_content
    # Ethanol chunk must not contain Composite's content
    assert "polymerization" not in docs[1].page_content


def test_contraindication_stays_in_its_item(synthetic_path):
    """The zinc oxide eugenol contraindication belongs to item 3 (Composite).
    It must not appear in item 1 or item 2.
    """
    docs = load_med_documents(synthetic_path)
    needle = "zinc oxide eugenol bases"
    assert needle in docs[2].page_content
    assert needle not in docs[0].page_content
    assert needle not in docs[1].page_content


def test_empty_file_returns_no_documents(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    assert load_med_documents(empty) == []


def test_file_with_no_numbered_sections_returns_one_unsplit_document(tmp_path):
    """When no numbered headings are found, the whole text becomes one document
    with item_number='?' (the regex finds nothing to split on).

    This documents loader behaviour for malformed input — med_info.txt is always
    numbered, so this path should never be reached in production.
    """
    p = tmp_path / "prose.txt"
    p.write_text(
        "This is just prose. No numbered headings here.\nSecond line of prose with no item number.\n",
        encoding="utf-8",
    )
    docs = load_med_documents(p)
    assert len(docs) == 1
    assert docs[0].metadata["item_number"] == "?"


# ── Real med_info.txt tests ───────────────────────────────────────────────────


def test_real_file_loads_12_documents():
    docs = load_med_documents()
    assert len(docs) == 12


def test_real_file_item_numbers_are_sequential():
    docs = load_med_documents()
    numbers = [int(d.metadata["item_number"]) for d in docs]
    assert numbers == list(range(1, 13))


def test_real_file_lidocaine_contraindications_preserved():
    docs = load_med_documents()
    lidocaine = docs[0]
    assert "hypersensitivity to amide-type anesthetics" in lidocaine.page_content


def test_real_file_ethanol_safety_warning_preserved():
    docs = load_med_documents()
    ethanol = docs[2]
    assert "Highly flammable" in ethanol.page_content
    assert "mucous membranes" in ethanol.page_content


def test_real_file_composite_zinc_oxide_contraindication_preserved():
    """Composite filling contraindication: do not use over zinc oxide eugenol.

    This is a clinically critical fact — it must not be dropped or split by chunking.
    """
    docs = load_med_documents()
    composite = docs[3]
    assert "zinc oxide eugenol bases" in composite.page_content
