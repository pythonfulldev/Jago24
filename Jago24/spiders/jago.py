#!/usr/bin/env python
# -*- coding: utf-8 -*-

import scrapy
import collections
import re

from Jago24.items import CategoryItem, ProductItem
from HTMLParser import HTMLParser
import traceback

is_empty = lambda x, y=None: x[0] if x else y

BuyerReviews = collections.namedtuple(
    "BuyerReviews",
    ['num_of_reviews',  # int
     'average_rating']  # float
)


class CategorySpider(scrapy.Spider):
    name = "jago_category"
    allowed_domains = ["http://www.jago24.de/"]

    start_urls = ['http://www.jago24.de/']

    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/58.0.3029.96 Safari/537.36"}

    def start_requests(self):
        yield scrapy.Request(url=self.start_urls[0], callback=self.parse_parent_categories)

    def parse_parent_categories(self, response):
        category_links = response.xpath('//ul[@id="mega-menu"]/li//ul//li/ul/li/a/@href').extract()

        for category_link in category_links:
            yield scrapy.Request(url=category_link, callback=self.parse_pages, headers=self.HEADERS, dont_filter=True)

    @staticmethod
    def parse_pages(response):
        category = CategoryItem()

        categories = response.xpath('//div[@id="breadCrumb"]/a/text()').extract()
        category['Category_Name'] = categories[-1]

        if categories[1] == 'Home':
            category_list = categories[3] + ', ' + categories[2]
        else:
            category_list = categories[2] + ', ' + categories[1]

        category['Category_Parents'] = category_list

        category['Meta_Title'] = response.xpath('//title[@itemprop="name"]/text()')[0].extract()

        category['Meta_Keywords'] = response.xpath('//meta[@name="keywords"]/@content')[0].extract()

        category['Meta_Description'] = HTMLParser().unescape(response.xpath('//meta[@property="og:description"]'
                                                                            '/@content')[0].extract())

        category['Category_URL'] = response.url

        yield category


class ProductSpider(scrapy.Spider):
    name = "jago_product"
    allowed_domains = ["http://www.jago24.de/"]

    start_urls = ['http://www.jago24.de/']

    HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/58.0.3029.96 Safari/537.36"}

    def start_requests(self):
        yield scrapy.Request(url=self.start_urls[0], callback=self.parse_category, headers=self.HEADERS)

    def parse_category(self, response):
        category_links = response.xpath('//ul[@id="mega-menu"]/li//ul//li/ul/li/a/@href').extract()

        for category_link in category_links:
            yield scrapy.Request(url=category_link, callback=self.parse_pages,
                                 headers=self.HEADERS, dont_filter=True)

    def parse_pages(self, response):
        page_links = response.xpath('//div[@id="itemsPagerPagerBottom"]'
                                    '/a[@class="pagnation"]/@href').extract()
        if page_links:
            for page_link in page_links:
                yield scrapy.Request(url=page_link, callback=self.parse_links,
                                     headers=self.HEADERS, dont_filter=True)
        else:
            yield scrapy.Request(url=response.url, callback=self.parse_links,
                                 headers=self.HEADERS, dont_filter=True)

    def parse_links(self, response):
        links = response.xpath('//ul[@id="productList"]/li[@class="productData"]'
                               '//a/@href').extract()
        for link in links:
            yield scrapy.Request(url=link, callback=self.parse_product,
                                 headers=self.HEADERS, dont_filter=True)

    def parse_product(self, response):
        product = ProductItem()

        product_name = response.xpath('//h1[@id="productTitle"]/span/text()').extract()
        product['Product_Name'] = product_name[0] if product_name else None

        category_list = ''
        categories = response.xpath('//div[@id="breadCrumb"]/a/text()').extract()
        for category_name in categories[1:]:
            if category_name == categories[1:][-1]:
                category_list += category_name
            else:
                category_list += category_name + ', '
        product['Product_Parent_categories'] = category_list

        technical_list = []
        technical_info = response.xpath('//div[@id="techdata"]'
                                        '/ul/li/text()').extract()
        for technical in technical_info:
            if not technical.strip() == '':
                technical_list.append(technical.strip())
        product['Technical_information'] = technical_list

        contents_list = []
        contents_info = response.xpath('//div[@id="lieferumfang"]'
                                       '/ul/li/text()').extract()
        for content in contents_info:
            if not content.strip() == '':
                contents_list.append(content.strip())
        product['Contents_Included'] = contents_list

        product['Product_Short_Description'] = response.xpath('//meta[@property="og:description"]'
                                                              '/@content')[0].extract().strip()

        product['Product_Long_Description'] = response.xpath('//div[@class="longdesc"]'
                                                             '/ul/li/text()').extract()

        aggregate_rating = re.search('"AggregateRating",(.*)}', response.body, re.DOTALL)
        product['Product_Aggregate_rating'] = aggregate_rating.group(1) if aggregate_rating else None

        product['Product_Reviews'] = self.parse_buyer_reviews(response)

        base_price = '€' + str(response.xpath('//span[@class="price"]//text()')[0].extract())

        variants = response.xpath('//div[@id="variants"]//ul/li[@class=" "]/a/text()').extract()

        variant_list = ''
        if variants:
            for variant in variants:
                if variant == variants[-1]:
                    variant_list += str(variant) + '-' + str(base_price)
                else:
                    variant_list += str(variant) + '-' + str(base_price) + ':'
            variant_list = base_price + '-' + variant_list
        else:
            variant_list = base_price

        product['Product_Price'] = str(variant_list)

        product['Meta_Title'] = response.xpath('//title[@itemprop="name"]/text()')[0].extract().strip()

        product['Meta_Keywords'] = response.xpath('//meta[@name="keywords"]/@content')[0].extract().strip()

        product['Meta_Description'] = response.xpath('//meta[@property="og:description"]'
                                                     '/@content')[0].extract().strip()

        product['Cover_Image_Url'] = response.xpath('//div[@class="picture"]/a/@href')[0].extract()

        product['Thumb_Images_Url'] = response.xpath('//ul[contains(@class, "thumblist")]'
                                                     '/li/a/@href').extract()

        yield product

    def parse_buyer_reviews(self, response):
        ZERO_REVIEWS_VALUE = {
            'num_of_reviews': 0,
            'average_rating': 0.0,
        }
        try:
            rew_num = response.xpath('//span[contains(@class, "reviewCount")]/text()').extract()
            rew_num = int(re.search('(\d+)', rew_num[0], re.DOTALL).group()) if rew_num else 0

            average_rating = response.xpath('//div[contains(@class, "averageRating")]'
                                            '/span[contains(@class, "ratingValue")]/text()').extract()
            average_rating = average_rating[0] if average_rating else 0
            buyer_reviews = {
                'num_of_reviews': rew_num,
                'average_rating': round(float(average_rating), 1),
            }
        except Exception as e:
            self.log("Error while parsing reviews: {}".format(traceback.format_exc()))
            return BuyerReviews(**ZERO_REVIEWS_VALUE)
        else:
            return BuyerReviews(**buyer_reviews)

