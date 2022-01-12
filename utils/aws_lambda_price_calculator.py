# Source for prices: https://aws.amazon.com/lambda/pricing/ (as of 1/11/2022)

import math
from decimal import *

from utils import AWSServicePriceFetcher

class AWSLambdaPriceCalculator:
    NUM_FREE_REQUESTS = 1_000_000
    NUM_FREE_GB_SECONDS = 400_000
    DIVISION_CONCURRENCY_TIME = 60 * 5

    def __init__(self, region):
        self.region = region
        self.price_fetcher = AWSServicePriceFetcher('lambda')


    def get_supported_os_types(self):
        return ['linux-x86', 'linux-arm']


    def get_supported_memory_range(self):
        return [128, 10_240]


    def _get_base_prices(self):
        raw_base_prices = self.price_fetcher.get_prices_by_region(self.region)
        unit_time = Decimal('0.001') # 1 ms -> seconds
        unit_count = Decimal(1_000_000)
        provisioned_concurrency_unit_time = Decimal(60 * 5) # 5 min -> seconds

        return {
            'linux-x86': {
                'duration': {'price': Decimal(raw_base_prices['Lambda Duration']['price']) * unit_time, 'unit-time': unit_time},
                'duration-provisioned': {'price': Decimal(raw_base_prices['Lambda Duration-Provisioned']['price']) * unit_time, 'unit-time': unit_time},
                'provisioned-concurrency': {'price': Decimal(raw_base_prices['Lambda Provisioned-Concurrency']['price']), 'unit-time': provisioned_concurrency_unit_time},
                'requests': {'price': Decimal(raw_base_prices['Lambda Requests']['price'])},
            },
            'linux-arm': {} if 'Lambda Duration-ARM' not in raw_base_prices else {
                'duration': {'price': Decimal(raw_base_prices['Lambda Duration-ARM']['price']) * unit_time, 'unit-time': unit_time},
                'duration-provisioned': {'price': Decimal(raw_base_prices['Lambda Duration-Provisioned-ARM']['price']) * unit_time, 'unit-time': unit_time},
                'provisioned-concurrency': {'price': Decimal(raw_base_prices['Lambda Provisioned-Concurrency-ARM']['price']), 'unit-time': provisioned_concurrency_unit_time},
                'requests': {'price': Decimal(raw_base_prices['Lambda Requests-ARM']['price'])},
            },
            'edge': {
                'duration': {'price': Decimal(raw_base_prices['Lambda Edge-Duration']['price']) * unit_time, 'unit-time': unit_time},
                'requests': {'price': Decimal(raw_base_prices['Lambda Edge-Requests']['price'])},
            }
        }


    def _is_config_supported(self, os_type, num_gb_ram):
        is_valid_os_type = os_type in self.get_supported_os_types()
        is_valid_num_gb_ram = num_gb_ram >= self.get_supported_memory_range()[0] and num_gb_ram <= self.get_supported_memory_range()[1]
        return is_valid_os_type and is_valid_num_gb_ram


    def calculate_simple_function_cost(self, os_type, num_gb_ram, time, requests, free_usage = False):
        num_mb_ram = Decimal(int(num_gb_ram * 1024))

        if not self._is_config_supported(os_type, num_mb_ram):
            raise Exception(f'Lambda configuration not supported: (OS Type: {os_type}, GB RAM = {num_gb_ram})')

        base_prices = self._get_base_prices()
        _time = Decimal(time)
        _requests = Decimal(requests)

        _total_duration = _requests * _time
        _fused_duration = Decimal(num_gb_ram) * (_total_duration / base_prices[os_type]['duration']['unit-time'])

        # Account for free tier if specified
        if free_usage:
            adjusted_duration = max(_fused_duration - self.NUM_FREE_GB_SECONDS * 1000, 0)
            adjusted_requests = max(_requests - self.NUM_FREE_REQUESTS, 0)
        else:
            adjusted_duration = _fused_duration
            adjusted_requests = _requests

        duration_cost = adjusted_duration * base_prices[os_type]['duration']['price']
        requests_cost = adjusted_requests * base_prices[os_type]['requests']['price']

        total_cost = duration_cost + requests_cost

        return {
            'total-cost': total_cost,
            'duration-cost': duration_cost,
            'requests-cost': requests_cost,
        }


    def calculate_concurrent_function_cost(self, os_type, num_gb_ram, time, requests, provisioned_concurrency, time_with_concurrency, free_tier = False):
        num_mb_ram = Decimal(int(num_gb_ram * 1024))

        if not self._is_config_supported(os_type, num_mb_ram):
            raise Exception(f'Lambda configuration not supported: (OS Type: {os_type}, GB RAM = {num_gb_ram})')

        base_prices = self._get_base_prices()
        _time = Decimal(time)
        _requests = Decimal(requests)

        _total_duration = _requests * _time
        _fused_duration = Decimal(num_gb_ram) * (_total_duration / base_prices[os_type]['duration-provisioned']['unit-time'])
        print(base_prices[os_type]['duration-provisioned']['price'])

        # Account for free tier if specified
        if free_tier:
            adjusted_requests = max(_requests - self.NUM_FREE_REQUESTS, 0)
        else:
            adjusted_requests = _requests

        #_fused_duration = num_mb_ram * (_time / base_prices[os_type]['duration-provisioned']['unit-time'])
        duration_cost = _fused_duration * base_prices[os_type]['duration-provisioned']['price']
        requests_cost = adjusted_requests * base_prices[os_type]['requests']['price']

        billed_time_with_concurrency = Decimal(math.ceil(time_with_concurrency / self.DIVISION_CONCURRENCY_TIME) * self.DIVISION_CONCURRENCY_TIME)
        concurrency_cost = Decimal(num_gb_ram) * Decimal(provisioned_concurrency) * billed_time_with_concurrency * base_prices[os_type]['provisioned-concurrency']['price']

        total_cost = duration_cost + requests_cost + concurrency_cost

        return {
            'total-cost': total_cost,
            'duration-cost': duration_cost,
            'requests-cost': requests_cost,
            'concurrency-cost': concurrency_cost,
        }


    def _is_edge_config_supported(self, num_gb_ram):
        is_valid_num_gb_ram = num_gb_ram >= self.get_supported_memory_range()[0] and num_gb_ram <= self.get_supported_memory_range()[1]
        return is_valid_num_gb_ram


    def calculate_edge_function_cost(self, num_gb_ram, time, requests):
        num_mb_ram = Decimal(int(num_gb_ram * 1024))

        if not self._is_edge_config_supported(num_mb_ram):
            raise Exception(f'Lambda configuration not supported: (GB RAM = {num_gb_ram})')

        base_prices = self._get_base_prices()
        _time = Decimal(time)
        _requests = Decimal(requests)

        _total_duration = _requests * _time
        _fused_duration = Decimal(num_gb_ram) * (_total_duration / base_prices['edge']['duration']['unit-time'])

        duration_cost = _fused_duration * base_prices['edge']['duration']['price']
        requests_cost = _requests * base_prices['edge']['requests']['price']

        total_cost = duration_cost + requests_cost

        return {
            'total-cost': total_cost,
            'duration-cost': duration_cost,
            'requests-cost': requests_cost,
        }

if __name__ == '__main__':
    lambda_calc = AWSLambdaPriceCalculator('us-west-1')

    print(
        lambda_calc.calculate_simple_function_cost(
            os_type='linux-x86',
            num_gb_ram=1.5,
            time=120 / 1000,
            requests=3_000_000,
            free_usage=True
        )
    )
