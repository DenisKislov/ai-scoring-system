"""Backward-compatible entry-point inside the package.

Prefer running ``python main.py`` from the project root instead.
"""

import sys
import os

# Ensure the project root is on sys.path so ``gb_parse`` is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings

from gb_parse.spiders.hh import HhSpider


if __name__ == "__main__":
    crawler_settings = Settings()
    crawler_settings.setmodule("gb_parse.settings", priority="project")
    crawler_proc = CrawlerProcess(settings=crawler_settings)
    crawler_proc.crawl(HhSpider)
    crawler_proc.start()
