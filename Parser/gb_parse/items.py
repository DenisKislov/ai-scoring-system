# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class HhVacancyItem(scrapy.Item):
    """Item for a single HH.ru job vacancy."""

    url = scrapy.Field()
    title = scrapy.Field()
    salary = scrapy.Field()
    description = scrapy.Field()
    skills = scrapy.Field()
    author_url = scrapy.Field()
    author_name = scrapy.Field()
    tags = scrapy.Field()


class HhCompanyItem(scrapy.Item):
    """Item for a company page on HH.ru."""

    url = scrapy.Field()
    title = scrapy.Field()
    description = scrapy.Field()
    site = scrapy.Field()
    external_id = scrapy.Field()


class HhResumeItem(scrapy.Item):
    """Item for a single HH.ru applicant resume.

    Note: HH.ru hides part of the resume (e.g. the applicant's name and the
    concrete skill tags) behind an employer login.  Without authentication the
    spider still collects the public fields defined below.
    """

    url = scrapy.Field()
    title = scrapy.Field()
    salary = scrapy.Field()
    specialization = scrapy.Field()
    age = scrapy.Field()
    gender = scrapy.Field()
    address = scrapy.Field()
    experience = scrapy.Field()
    skills = scrapy.Field()
    languages = scrapy.Field()
    relocation = scrapy.Field()
    tags = scrapy.Field()
