"""Generate the fixed TF-IDF reference corpus used by ``scorer.similarity``.

Why this exists: the old code fit TF-IDF **per call** on just the two compared
documents (``pair_cosine``) or on ``[vacancy] + pool`` (``batch_cosine``). That
made the cosine of a fixed (vacancy, resume) pair **change depending on who else
is in the pool** — so the headline "Score is an absolute measure" claim in the
README did not actually hold, and ``calculate_score`` disagreed with
``rank_candidates`` for the same pair.

Fix: fit the TF-IDF vectorizer **once**, at import time, on a fixed, realistic
Russian corpus of vacancy + resume texts. The IDF (rarity of each term) is then
stable, the cosine of a pair no longer depends on the pool, and both public
scoring functions agree by construction.

The corpus is generated from the same profession renderer the synthetic data
uses, normalized the same way the scorer normalizes, so its vocabulary (skills
*and* ordinary words like "опыт", "разработка", "команда") matches production
input. Output is a plain Python list so ``scorer`` has no runtime dependency on
``data``/``Faker``.

Regenerate after changing the corpus: ``python -m tools.build_reference_corpus``
"""
from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "scorer" / "reference_corpus.py"


def main() -> int:
    # Local imports keep the tool dependency-tolerant at module load.
    from data.synthetic import generate_dataset
    from scorer.normalize import normalize

    dataset = generate_dataset(n_vacancies=8, n_resumes=25, seed=42)

    docs: list[str] = []
    seen: set[str] = set()
    for entry in dataset:
        for text in (entry["vacancy"]["text"], *(c["text"] for c in entry["candidates"])):
            norm = normalize(text)
            if norm and norm not in seen:
                seen.add(norm)
                docs.append(norm)

    payload = json.dumps(docs, ensure_ascii=False, indent=2)
    _OUT.write_text(
        '"""Auto-generated TF-IDF reference corpus.\n\n'
        "Normalized (lemmatized) Russian vacancy/resume texts used to fit IDF so\n"
        "that cosine similarity is stable and pool-independent. Regenerate with\n"
        "``python -m tools.build_reference_corpus`` — do not edit by hand.\n"
        '"""\n'
        f"REFERENCE_DOCS = {payload}\n",
        encoding="utf-8",
    )
    print(f"Wrote {_OUT}  ({len(docs)} unique normalized documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
