import re
import json

import scrapy
from scrapy_selenium import SeleniumRequest


class LazaSpider(scrapy.Spider):
    name = 'laza'
    allowed_domains = ['www.lazada.com.my']

    def start_requests(self):
        brands = ['asus']

        def cookies_ready(driver):
            return {'_uab_collina', 'lzd_cid', 't_uid', 'hng',
                    'userLanguageML', 't_fv', 'lzd_sid', '_tb_token_',
                    '_bl_uid', 'cna', '_uetsid', '_uetvid', '_ga', '_gid',
                    '_fbp', 'xlly_s', 'tfstk', 'l', 'isg', 'JSESSIONID'
                    }.issubset({c['name'] for c in driver.get_cookies()})
        for brand in brands:
            yield SeleniumRequest(
                url=f'https://www.lazada.com.my/shop-laptops-gaming/{brand}/',
                callback=self.parse_first_page,
                wait_time=30,
                wait_until=cookies_ready
            )

    def parse_first_page(self, response, **kwargs):
        driver = response.request.meta['driver']
        cookies = []
        for c in driver.get_cookies():
            _c = {'name': c['name'],
                  'value': c['value'],
                  'path': c['path']}
            if c['domain'] != 'www.lazada.com.my':
                _c['domain'] = c['domain']
            cookies.append(_c)
        driver.quit()

        page_data = response.xpath("/html/head/script[contains(text(),'window.pageData=')]/text()").get()
        page_data = page_data[len(re.match('^\s*window\.pageData\s*=\s*', page_data)[0]):]
        page_data = json.loads(page_data)

        first = True
        for item in page_data['mods']['listItems']:
            yield scrapy.Request(url=f"https:{item['productUrl']}",
                                 cookies=cookies if first else None,
                                 callback=self.parse_product_page,
                                 cb_kwargs={'sku_id': item['skuId'],
                                            'price_show': item['priceShow']})
            first = False

        total_results = int(page_data['mainInfo']['totalResults'])
        page_size = int(page_data['mainInfo']['pageSize'])
        if page_size < total_results:
            url = f'{response.request.url}?ajax=true&page=2'
            yield scrapy.Request(url=url, callback=self.parse_page)

    def parse_page(self, response):
        page_data = json.loads(response.text)
        try:
            cur_page = int(page_data['mainInfo']['page'])
            items = page_data['mods']['listItems']
        except KeyError:
            self.logger.error(response.text)
            raise

        for item in items:
            yield scrapy.Request(url=f"https:{item['productUrl']}",
                                 callback=self.parse_product_page,
                                 cb_kwargs={'sku_id': item['skuId'],
                                            'price_show': item['priceShow']})

        total_results = int(page_data['mainInfo']['totalResults'])
        page_size = int(page_data['mainInfo']['pageSize'])
        if cur_page * page_size < total_results:
            url = response.request.url.rsplit('/', 1)[0] + f'/?ajax=true&page={cur_page+1}'
            yield scrapy.Request(url=url, callback=self.parse_page)

    def parse_product_page(self, response, sku_id, price_show):
        script = response.xpath("/html/body/script[16]/text()").get()
        try:
            data = re.search('(app\.run\()(.*)(\);)', script).group(2)
        except TypeError:
            self.logger.error(script)
            raise

        data = json.loads(data)
        target = data['data']['root']['fields']['specifications'][sku_id]['features']
        yield target
