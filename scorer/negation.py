"""Scope explicit Russian and English negations over recognised skill spans.

Adapted from scorer/professional_expressions.py in t1-1-candidate-scoring.
See THIRD_PARTY_NOTICES.md for the original MIT notice.
"""

import re


_CLAUSE = re.compile(
    r"[;!?\n]|\.(?=\s|$)|\b(?:а(?!\s+также\b)|но|однако|but|however)\b", re.I
)
_LIST = re.compile(r",|\b(?:и|а\s+также|and|as\s+well\s+as)\b", re.I)
_CUE = re.compile(
    r"\b(?P<negative>не\s+(?:требу(?:ется|ются)|обязател(?:ен|ьн(?:о|а|ы))|"
    r"нуж(?:ен|на|но|ны)|явля(?:ется|ются)\s+обязательн(?:ым|ыми)|"
    r"зна(?:ю|ет|ем)|владе\w*|использ[оу]\w*|применя\w*|работа\w*|умею|имею|знаком\w*|освоил\w*|"
    r"разрабатыва\w*|администрирова\w*|настраива\w*|разворачивал\w*)|"
    r"необязател(?:ен|ьн(?:о|а|ы))|(?:нет|без)\s+(?:опыта|знаний|навыков)|"
    r"(?:опыта|знаний|навыков)\s+нет|(?:no|without)\s+(?:experience|knowledge|skills)|"
    r"(?:not|never)\s+(?:required|mandatory|necessary|proficient|experienced|familiar|"
    r"used|use|know|worked|developed|built|configured|administered)|"
    r"(?:do\s+not|don['’]t)\s+(?:know|use))\b|"
    r"\b(?P<without>без|without)\b",
    re.I,
)
_POSITIVE = re.compile(
    r"\b(?:знаю|владею|использ[оу]\w*|применя\w*|работаю|работал[аи]?|разрабатыва\w*|"
    r"администрирова\w*|настраива\w*|обязател(?:ен|ьн(?:о|а|ы))|требу(?:ется|ются)|"
    r"желател(?:ен|ьн(?:о|а|ы))|приветству(?:ется|ются)|"
    r"know|use|used|worked|experienced|developed|built|configured|administered|required|preferred)\b",
    re.I,
)


def has_negation_cue(text: str) -> bool:
    return bool(_CUE.search(text))


def _segments(text, separator):
    start = 0
    for match in separator.finditer(text):
        yield start, match.start()
        start = match.end()
    yield start, len(text)


def negated_spans(text: str, spans: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Classify occurrences independently, extending a cue across list items."""
    denied = set()
    ordered = sorted(spans)
    index = 0
    for left, right in _segments(text, _CLAUSE):
        inherited = None
        pending = []
        for start, end in _segments(text[left:right], _LIST):
            start, end = left + start, left + end
            items = []
            while index < len(ordered) and ordered[index][0] < end:
                span = ordered[index]
                if span[0] >= start:
                    items.append(span)
                index += 1

            part = text[start:end]
            negatives = [(start + match.start(), start + match.end(), True)
                         for match in _CUE.finditer(part)
                         if match.lastgroup != 'without' or any(
                             skill_start >= start + match.end()
                             and not text[start + match.end():skill_start].strip(' \t:"«(')
                             for skill_start, _ in items)]
            positives = [(start + match.start(), start + match.end(), False)
                         for match in _POSITIVE.finditer(part)
                         if not any(a <= start + match.start() < b for a, b, _ in negatives)]
            cues = sorted(negatives + positives)
            if not cues:
                if inherited:
                    denied.update(items)
                elif inherited is None:
                    pending.extend(items)
                continue

            first, last = cues[0], cues[-1]
            # A trailing cue applies to an unqualified list to its left.
            suffix = any(b <= first[0] for _, b in items) and not any(a >= first[1] for a, _ in items)
            local = suffix and text[items[-1][1]:first[0]].strip() == '('
            if suffix and inherited is None and first[2] and not local:
                denied.update(pending)
            for span in items:
                earlier = [cue for cue in cues if cue[1] <= span[0]]
                later = next((cue for cue in cues if cue[0] >= span[1]), None)
                if earlier:
                    negative = earlier[-1][2]
                elif later and (suffix or not later[2]):
                    negative = later[2]
                else:
                    negative = inherited
                if negative:
                    denied.add(span)
            if not local:
                inherited = last[2]
                pending.clear()
    return denied
