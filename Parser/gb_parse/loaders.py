import re
from urllib.parse import urljoin

from itemloaders.processors import TakeFirst, MapCompose, Join
from scrapy.loader import ItemLoader

from gb_parse.items import HhVacancyItem, HhCompanyItem, HhResumeItem

# HH.ru groups digits with typographic spaces (U+2009 THIN SPACE etc.) that
# Python's ``\s`` does NOT match, so we normalise them explicitly.
_UNICODE_WS = re.compile(r"[  -   　]")


def _norm_ws(text):
    """Replace exotic Unicode spaces with a regular ASCII space."""
    return _UNICODE_WS.sub(" ", text)


def _clean_salary_text(values):
    """Join salary text nodes and normalise whitespace.

    HH.ru salary block contains multiple <span> children with text like
    "100 000", "–", "150 000", "руб." spread across them.  We join them
    into a single readable string, collapsing duplicate spaces.
    """
    text = " ".join(v.strip() for v in values if v and v.strip())
    text = _norm_ws(text)
    # Collapse runs of whitespace into a single space
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def _clean_text(values):
    """Join text nodes (e.g. vacancy description) and collapse whitespace."""
    text = "\n".join(v.strip() for v in values if v and v.strip())
    text = _norm_ws(text)
    return text if text else None


def _clean_inline_text(values):
    """Join fragments with a single space and normalise Unicode whitespace.

    Used for resume fields that come back as several text nodes, e.g. age
    ("28", "\xa0", "лет") or total experience.
    """
    text = " ".join(v.strip() for v in values if v and v.strip())
    text = _norm_ws(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text if text else None


def _make_absolute_url(value):
    """Ensure a URL is absolute (relative paths → https://hh.ru/...)."""
    if not value:
        return None
    return urljoin("https://hh.ru/", value)


class HHVacancyLoader(ItemLoader):
    """Loader for HhVacancyItem — processes fields from a vacancy page."""

    default_item_class = HhVacancyItem

    url_out = TakeFirst()
    title_out = TakeFirst()

    salary_in = MapCompose(lambda v: v.replace("\xa0", " "))
    salary_out = _clean_salary_text

    description_in = MapCompose(str.strip)
    description_out = _clean_text

    skills_out = lambda self, values: list(values)

    author_url_in = MapCompose(_make_absolute_url)
    author_url_out = TakeFirst()

    author_name_out = TakeFirst()


class HHCompanyLoader(ItemLoader):
    """Loader for HhCompanyItem — processes fields from a company page."""

    default_item_class = HhCompanyItem

    url_out = TakeFirst()
    title_out = TakeFirst()

    description_in = MapCompose(str.strip)
    description_out = _clean_text

    site_out = TakeFirst()
    external_id_out = TakeFirst()


class HHResumeLoader(ItemLoader):
    """Loader for HhResumeItem — processes fields from a resume page."""

    default_item_class = HhResumeItem

    url_out = TakeFirst()
    title_out = TakeFirst()

    salary_in = MapCompose(lambda v: _norm_ws(v))
    salary_out = _clean_salary_text

    specialization_out = _clean_inline_text
    age_out = _clean_inline_text
    gender_out = TakeFirst()
    address_out = TakeFirst()
    experience_out = _clean_inline_text
    relocation_out = TakeFirst()

    skills_out = lambda self, values: [v.strip() for v in values if v and v.strip()]
    languages_out = lambda self, values: [v.strip() for v in values if v and v.strip()]
    tags_out = lambda self, values: [v.strip() for v in values if v and v.strip()]
