import requests

from utils import AWSRegions

class AWSServicePriceFetcher:
    def __init__(self, service_name):
        self.service_price_url = f'https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/{service_name}/USD/current/{service_name}.json'

        self.region_info = AWSRegions.fetch_regions()
        self.raw_data = requests.get(self.service_price_url).json()

    def get_prices_by_region(self, region_code):
        target_region_name = [region['name'] for region in self.region_info if region['code'] == region_code][0]
        return self.raw_data['regions'][target_region_name]
