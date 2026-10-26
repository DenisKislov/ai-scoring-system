"""Exclude contact and demographic attributes from both score components.

Raw source documents remain available to an authorised user; only professional
text is passed to extraction/normalisation/scoring. No inferred sensitive traits.
"""
import re

_PERSONAL_LINE = re.compile(
    r"^\s*(?:фио|ф\.?\s*и\.?\s*о\.?|фамилия|имя|отчество|кандидат|"
    r"возраст|дата рождения|год рождения|пол|адрес(?: проживания)?|гражданство|"
    r"национальность|город(?: проживания)?|место проживания|семейное положение|"
    r"телефон|мобильный|контакты|e-?mail|электронная почта)\s*[:：].*$", re.I | re.M)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zа-я]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\w)(?:\+7|8)[\s(.-]*\d{3}[)\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)")
_NAME = re.compile(r"^[А-ЯЁ][а-яё]+(?:[- ][А-ЯЁ][а-яё]+){1,3}$")


def professional_text(text: str) -> str:
    if not text:
        return ""
    lines = text.splitlines()
    if lines and _NAME.fullmatch(lines[0].strip()):
        lines[0] = ""
    text = _PERSONAL_LINE.sub("", "\n".join(lines))
    text = _PHONE.sub("", _EMAIL.sub("", text))
    return text.strip()
