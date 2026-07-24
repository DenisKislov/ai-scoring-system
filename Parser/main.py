"""Entry-point script — run from the project root:  python main.py"""

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings

from gb_parse.spiders.hh import HhSpider


def main():
    crawler_settings = Settings()
    crawler_settings.setmodule("gb_parse.settings", priority="project")
    crawler_proc = CrawlerProcess(settings=crawler_settings)
    crawler_proc.crawl(HhSpider)
    crawler_proc.start()


if __name__ == "__main__":
    main()
