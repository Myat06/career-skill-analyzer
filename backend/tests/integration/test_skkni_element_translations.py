"""Guards ELEMENT_TITLES_EN (app/scoring/skkni_titles.py) against drift from
the real ingested SKKNI collection. A missing (unit_code, element_number)
entry doesn't error anywhere -- english_element_title() just silently falls
back to the original Indonesian text -- so nothing else would catch a future
SKKNI PDF revision adding/renumbering elements except this test. This matters
more than ordinary translation-table drift: text_evidence.py's LLM-judged
matching was confirmed live to silently stop finding real matches when handed
an untranslated (Indonesian) element title, so a gap here is a live scoring
regression, not just a display nicety.

Requires Postgres with the real SKKNI PDF already ingested (see
test_ingestion_pipeline.py) -- no Ollama needed.
"""

import pytest

from app.scoring.skkni_titles import ELEMENT_TITLES_EN
from app.vectorstore import skkni_collection

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def _real_element_keys() -> set[tuple[str, str]]:
    data = await skkni_collection().get(where={"section_type": "element"}, include=["metadatas"])
    return {(meta["unit_code"], str(meta["element_number"])) for meta in data["metadatas"]}


async def test_every_real_ingested_element_has_a_translation():
    real_keys = await _real_element_keys()
    missing = sorted(real_keys - ELEMENT_TITLES_EN.keys())
    assert not missing, f"ELEMENT_TITLES_EN is missing a translation for: {missing}"


async def test_no_stale_translation_entries_for_elements_that_no_longer_exist():
    real_keys = await _real_element_keys()
    stale = sorted(ELEMENT_TITLES_EN.keys() - real_keys)
    assert not stale, f"ELEMENT_TITLES_EN has entries for elements not in the real ingested SKKNI collection: {stale}"
