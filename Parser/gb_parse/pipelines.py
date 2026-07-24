# Define your item pipelines here
#
# Don't forget to add your Pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html

from itemadapter import ItemAdapter
import pymongo

from gb_parse.items import HhVacancyItem, HhCompanyItem, HhResumeItem


class GbParsePipeline:
    """Basic pass-through pipeline."""

    def process_item(self, item, spider):
        return item


class GbParseMongoPipeline:
    """Store scraped items in MongoDB.

    Connection parameters are read from Scrapy settings (with defaults):
        MONGO_URI   – MongoDB connection URI  (default: "mongodb://localhost:27017")
        MONGO_DB    – database name           (default: "gb_parse")
    Each spider gets its own collection named after ``spider.name``.
    """

    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get("MONGO_URI", "mongodb://localhost:27017"),
            mongo_db=crawler.settings.get("MONGO_DB", "gb_parse"),
        )

    def open_spider(self, spider):
        self.client = pymongo.MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]

    def close_spider(self, spider):
        self.client.close()

    def process_item(self, item, spider):
        adapter = ItemAdapter(item)
        if isinstance(item, HhCompanyItem):
            collection = f"{spider.name}_companies"
        elif isinstance(item, HhResumeItem):
            collection = f"{spider.name}_resumes"
        else:
            collection = spider.name
        self.db[collection].insert_one(dict(adapter))
        return item
