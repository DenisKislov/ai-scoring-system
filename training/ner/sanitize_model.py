"""Remove contact and credential strings from a model's serialized vocabulary.

Weights are copied unchanged. Validate prediction equality before deployment.
The source model is always preserved. No matched values are printed.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pmi.audit import PATTERNS  # noqa: E402


def sanitize(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    if source == output or source in output.parents or output.exists():
        raise ValueError('Use a new output directory outside the source model')
    strings = json.loads((source/'vocab/strings.json').read_text())
    counts = Counter()
    kept = []
    for value in strings:
        kinds = [kind for kind, pattern in PATTERNS.items() if pattern.search(value)]
        if kinds:
            counts.update(kinds)
        else:
            kept.append(value)
    shutil.copytree(source, output)
    (output/'vocab/strings.json').write_text(json.dumps(kept, ensure_ascii=False, indent=2)+'\n')
    return {'source_strings':len(strings),'kept_strings':len(kept),
            'removed_strings':len(strings)-len(kept),'findings_by_type':dict(counts)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(sanitize(args.model,args.output),indent=2))


if __name__ == '__main__':
    main()
