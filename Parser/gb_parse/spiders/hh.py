import json
import os

import scrapy

from gb_parse.items import HhVacancyItem, HhCompanyItem, HhResumeItem
from gb_parse.loaders import HHVacancyLoader, HHCompanyLoader, HHResumeLoader

# Path to the external crawl config: <project_root>/config/config.json
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "config", "config.json")

# Fallbacks used when the config file is missing or unreadable, so the spider
# still runs out of the box.
_DEFAULT_CONFIG = {
    "vacancy_parsing": True,
    "company_parsing": True,
    "resume_parsing": True,
    "start_urls": [
        "https://hh.ru/search/resume?text=%D0%9F%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%81%D1%82+python&area=4&search_period=0&order_by=relevance"
    ],
}


def _load_config():
    """Load ``config/config.json``, falling back to defaults on any error."""
    config = dict(_DEFAULT_CONFIG)
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as handle:
            config.update(json.load(handle))
    except (FileNotFoundError, json.JSONDecodeError):
        # No valid config file — keep the built-in defaults.
        pass
    return config


class HhSpider(scrapy.Spider):
    name = "hh"
    allowed_domains = ["hh.ru"]
    # Used only as a fallback when ``config/config.json`` has no start_urls.
    # The search type is detected from the URL: ``/search/resume`` crawls
    # resumes, anything else (e.g. ``/search/vacancy``) crawls vacancies.
    start_urls = [
        "https://hh.ru/search/resume?text=%D0%9F%D1%80%D0%BE%D0%B3%D1%80%D0%B0%D0%BC%D0%BC%D0%B8%D1%81%D1%82+python&area=4&search_period=0&order_by=relevance"
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # External config drives which entity types are parsed and the list of
        # URLs the spider starts from.
        self.config = _load_config()
        if self.config.get("start_urls"):
            self.start_urls = self.config["start_urls"]

    # XPath selectors for data fields on a vacancy detail page
    _xpath_data_query = {
        "title": '//h1[@data-qa="vacancy-title"]/text()',
        "salary": '//div[@data-qa="vacancy-salary"]//text()',
        "description": '//div[@data-qa="vacancy-description"]//text()',
        "skills": '//*[@data-qa="skills-element"]//text()',
        "author_url": '//a[@data-qa="vacancy-company-name"]/@href',
        "author_name": '//a[@data-qa="vacancy-company-name"]//text()',
    }

    # XPath selectors for navigation elements on the search results page
    _xpath_selectors = {
        "pagination": '//a[@data-qa="pager-page"]/@href',
        "vacancy": '//a[contains(@href,"hh.ru/vacancy/")]/@href',
        "resume": '//a[@data-qa="serp-item__title"][contains(@href,"/resume/")]/@href',
    }

    # XPath selectors for company detail pages
    _xpath_company_query = {
        "title": '//*[@data-qa="company-header-title-name"]//text()',
        "description": '//div[@data-qa="employer-page-company-info"]//text()',
        "site": '//a[@data-qa="sidebar-company-site"]/@href',
        "external_id": '//*[@data-qa="company-header-title-name"]/@data-company-id',
    }

    # XPath selectors for data fields on a resume detail page
    _xpath_resume_query = {
        "title": '//*[@data-qa="resume-block-title-position"]//text()',
        "salary": '//*[@data-qa="resume-block-salary"]//text()',
        "specialization": '//*[@data-qa="resume-block-position-specialization"]//text()',
        "age": '//*[@data-qa="resume-personal-age"]//text()',
        "gender": '//*[@data-qa="resume-personal-gender"]//text()',
        "address": '//*[@data-qa="resume-personal-address"]//text()',
        "experience": '//*[@data-qa="resume-block-experience"]//text()',
        "skills": '//span[@data-qa="bloko-tag__text"]/text()',
        "languages": (
            '//*[@data-qa="resume-block-languages"]'
            '//*[@data-qa="resume-block-language-item"]//text()'
        ),
        "relocation": '//*[@data-qa="relocation_relocation_possible"]//text()',
    }

    def parse(self, response, **kwargs):
        """Parse a search results page — follow pagination and detail links.

        Dispatches on the search type: ``/search/resume`` → resume cards,
        everything else → vacancy cards. Each type can be turned off in
        ``config/config.json`` (``resume_parsing`` / ``vacancy_parsing``).
        """
        if "/search/resume" in response.url:
            if not self.config.get("resume_parsing", True):
                return
            list_key, detail_callback = "resume", self.resume_parse
        else:
            if not self.config.get("vacancy_parsing", True):
                return
            list_key, detail_callback = "vacancy", self.vacancy_parse

        yield from self._get_follow_xpath(
            response, self._xpath_selectors["pagination"], self.parse
        )
        yield from self._get_follow_xpath(
            response, self._xpath_selectors[list_key], detail_callback
        )

    def vacancy_parse(self, response):
        """Parse a single vacancy detail page."""
        loader = HHVacancyLoader(response=response)
        loader.add_value("url", response.url)
        for key, xpath in self._xpath_data_query.items():
            loader.add_xpath(key, xpath)

        # Follow the company page for additional data
        author_url = response.xpath(
            '//a[@data-qa="vacancy-company-name"]/@href'
        ).get()
        if author_url and self.config.get("company_parsing", True):
            yield response.follow(
                author_url,
                callback=self.company_parse,
                cb_kwargs={"vacancy_loader": loader},
            )
        else:
            yield loader.load_item()

    def company_parse(self, response, vacancy_loader=None):
        """Parse a company page and enrich the vacancy item with company data."""
        if vacancy_loader is not None:
            company_name = response.xpath(
                self._xpath_company_query["title"]
            ).get()
            if company_name:
                vacancy_loader.add_value("author_name", company_name.strip())
            yield vacancy_loader.load_item()

        # Also yield a separate company item (unless disabled in the config)
        if not self.config.get("company_parsing", True):
            return

        company_loader = HHCompanyLoader(response=response)
        company_loader.add_value("url", response.url)
        for key, xpath in self._xpath_company_query.items():
            company_loader.add_xpath(key, xpath)
        yield company_loader.load_item()

    def resume_parse(self, response):
        """Parse a single resume detail page.

        Some resumes are private or removed and redirect away, leaving the
        title empty — we skip those to avoid storing blank rows.
        """
        loader = HHResumeLoader(response=response)
        loader.add_value("url", response.url)
        for key, xpath in self._xpath_resume_query.items():
            loader.add_xpath(key, xpath)
        if loader.get_output_value("title"):
            yield loader.load_item()

    # ---- helpers ----

    def _get_follow_xpath(self, response, xpath, callback):
        """Follow every URL matched by *xpath* with *callback*."""
        for url in response.xpath(xpath):
            yield response.follow(url, callback=callback)
