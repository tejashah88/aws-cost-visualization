# Source for prices: https://aws.amazon.com/fargate/pricing/ (as of 1/11/2022)

from decimal import *
import numpy as np

import requests

from utils import AWSServicePriceFetcher

class AWSFargatePriceCalculator:
    NUM_GB_FREE_STORAGE = 20

    def __init__(self, region):
        self.region = region
        self.price_fetcher = AWSServicePriceFetcher('ecs')

        # TODO: Fine more permanent URL as this is subject to unexpected change
        self.spot_price_url = 'https://dftu77xade0tc.cloudfront.net/fargate-spot-prices.json'
        self._update_spot_prices()


    def _update_spot_prices(self):
        self.spot_price_raw_data = requests.get(self.spot_price_url).json()


    def get_supported_os_types(self):
        return ['linux-x86', 'linux-arm', 'windows']


    def get_supported_vcpus(self):
        return [0.25, 0.5, 1, 2, 4]


    def get_supported_memory(self):
        nrange = lambda start, stop, step = 1: list(range(start, stop + step, step))

        return {
            0.25: [0.5, 1, 2],
            0.5: nrange(1, 4),
            1: nrange(2, 8),
            2: nrange(4, 16),
            4: nrange(8, 30),
        }


    def get_all_supported_memory(self):
        supported_memory_configs = self.get_supported_memory()
        return list(set([value for values in supported_memory_configs.values() for value in values]))


    def _get_base_prices_on_demand(self):
        raw_base_prices = self.price_fetcher.get_prices_by_region(self.region)
        unit_time = Decimal(60 * 60) # 1 hour -> seconds

        return {
            'cpu': {
                'linux-x86': {'price': Decimal(raw_base_prices['perCPU per hour']['price']), 'unit-time': unit_time},
                'linux-arm': {'price': Decimal(raw_base_prices['ARM perCPU per hour']['price']), 'unit-time': unit_time},
                'windows': {'price': Decimal(raw_base_prices['perCPU per hour Windows']['price']), 'unit-time': unit_time},
            },
            'memory': {
                'linux-x86': {'price': Decimal(raw_base_prices['perGB per hour']['price']), 'unit-time': unit_time},
                'linux-arm': {'price': Decimal(raw_base_prices['ARM perGB per hour']['price']), 'unit-time': unit_time},
                'windows': {'price': Decimal(raw_base_prices['perGB per hour Windows']['price']), 'unit-time': unit_time},
            },
            'os-license-fee': {
                'linux-x86': {'price': Decimal(0), 'unit-time': unit_time},
                'linux-arm': {'price': Decimal(0), 'unit-time': unit_time},
                'windows': {'price': Decimal(raw_base_prices['perCPU OS License Fee per hour Windows']['price']), 'unit-time': unit_time},
            },
            'storage': {
                'linux-x86': {'price': Decimal(raw_base_prices['Storage per GB-Hours']['price']), 'unit-time': unit_time},
                'linux-arm': {'price': Decimal(raw_base_prices['Storage per GB-Hours']['price']), 'unit-time': unit_time},
                'windows': {'price': Decimal(raw_base_prices['Storage per GB-Hours']['price']), 'unit-time': unit_time},
            }
        }


    def _is_on_demand_config_supported(self, os_type, num_cpu, num_gb_ram, num_gb_storage):
        is_valid_os_type = os_type in self.get_supported_os_types()
        is_valid_num_cpus = num_cpu in self.get_supported_vcpus()
        is_valid_num_gb_ram = num_gb_ram in self.get_supported_memory()[num_cpu]
        is_valid_num_gb_storage = num_gb_storage > 0
        return is_valid_os_type and is_valid_num_cpus and is_valid_num_gb_ram and is_valid_num_gb_storage


    def _calculate_cost_on_demand(self, os_type, num_cpu, num_gb_ram, num_gb_storage, time, free_usage = False):
        if not self._is_on_demand_config_supported(os_type, num_cpu, num_gb_ram, num_gb_storage):
            raise Exception(f'Invalid Fargate On-Demand configuration: (OS Type: {os_type}, vCPUs = {num_cpu}, GB RAM = {num_gb_ram}, GB Storage = {num_gb_storage})')

        base_prices = self._get_base_prices_on_demand()
        _time = Decimal(time)

        # Account for free tier if specified
        if free_usage:
            adjusted_used_storage = max(num_gb_storage - self.NUM_GB_FREE_STORAGE, 0)
        else:
            adjusted_used_storage = num_gb_storage

        cost_cpu_usage = Decimal(num_cpu) * base_prices['cpu'][os_type]['price'] * (_time / base_prices['cpu'][os_type]['unit-time'])
        cost_ram_usage = Decimal(num_gb_ram) * base_prices['memory'][os_type]['price'] * (_time / base_prices['memory'][os_type]['unit-time'])
        cost_cpu_os_license_fee_usage = Decimal(num_cpu) * base_prices['os-license-fee'][os_type]['price'] * (_time / base_prices['os-license-fee'][os_type]['unit-time'])
        cost_storage_usage = Decimal(adjusted_used_storage) * base_prices['storage'][os_type]['price'] * (_time / base_prices['storage'][os_type]['unit-time'])

        total_cost = cost_cpu_usage + cost_ram_usage + cost_cpu_os_license_fee_usage + cost_storage_usage

        return {
            'total-cost': total_cost,
            'cpu-cost': cost_cpu_usage,
            'memory-cost': cost_ram_usage,
            'os-license-cost': cost_cpu_os_license_fee_usage,
            'storage-cost': cost_storage_usage,
        }


    def _get_base_prices_spot(self):
        region_specific_data = [blob for blob in self.spot_price_raw_data['prices'] if blob['attributes']['aws:region'] == self.region]

        cpu_price_info = [datum for datum in region_specific_data if datum['unit'] == 'vCPU-Hours'][0]
        memory_price_info = [datum for datum in region_specific_data if datum['unit'] == 'GB-Hours'][0]
        raw_base_prices = self.price_fetcher.get_prices_by_region(self.region)

        unit_time = Decimal(60 * 60) # 1 hour -> seconds

        return {
            'cpu': {'price': Decimal(cpu_price_info['price']['USD']), 'unit-time': unit_time},
            'memory': {'price': Decimal(memory_price_info['price']['USD']), 'unit-time': unit_time},
            'storage': {'price': Decimal(raw_base_prices['Storage per GB-Hours']['price']), 'unit-time': unit_time},
        }

    def _is_spot_config_supported(self, num_cpu, num_gb_ram, num_gb_storage):
        is_valid_num_cpus = num_cpu in self.get_supported_vcpus()
        is_valid_num_gb_ram = num_gb_ram in self.get_supported_memory()[num_cpu]
        is_valid_num_gb_storage = num_gb_storage > 0
        return is_valid_num_cpus and is_valid_num_gb_ram and is_valid_num_gb_storage


    def _calculate_cost_spot(self, num_cpu, num_gb_ram, num_gb_storage, time, free_usage = False):
        if not self._is_spot_config_supported(num_cpu, num_gb_ram, num_gb_storage):
            raise Exception(f'Invalid Fargate Spot configuration: (vCPUs = {num_cpu}, GB RAM = {num_gb_ram}, GB Storage = {num_gb_storage})')

        base_prices = self._get_base_prices_spot()
        _time = Decimal(time)

        # Account for free tier if specified
        if free_usage:
            adjusted_used_storage = max(num_gb_storage - self.NUM_GB_FREE_STORAGE, 0)
        else:
            adjusted_used_storage = num_gb_storage

        cost_cpu_usage = Decimal(num_cpu) * base_prices['cpu']['price'] * (_time / base_prices['cpu']['unit-time'])
        cost_ram_usage = Decimal(num_gb_ram) * base_prices['memory']['price'] * (_time / base_prices['memory']['unit-time'])
        cost_cpu_os_license_fee_usage = Decimal('0')
        cost_storage_usage = Decimal(adjusted_used_storage) * base_prices['storage']['price'] * (_time / base_prices['storage']['unit-time'])

        total_cost = cost_cpu_usage + cost_ram_usage + cost_storage_usage

        return {
            'total-cost': total_cost,
            'cpu-cost': cost_cpu_usage,
            'memory-cost': cost_ram_usage,
            'os-license-cost': cost_cpu_os_license_fee_usage,
            'storage-cost': cost_storage_usage,
        }


    def calculate_cost(self, os_type, num_cpu, num_gb_ram, num_gb_storage, time, spot = False, free_usage = False):
        if spot:
            total_price = self._calculate_cost_spot(num_cpu, num_gb_ram, num_gb_storage, time, free_usage)
        else:
            total_price = self._calculate_cost_on_demand(os_type, num_cpu, num_gb_ram, num_gb_storage, time, free_usage)

        return total_price


    def calculate_savings(self, os_type, num_cpu, num_gb_ram, num_gb_storage, time, free_usage = False):
        on_demand_costs = self.calculate_cost(os_type, num_cpu, num_gb_ram, num_gb_storage, time, spot = False, free_usage = free_usage)
        spot_costs = self.calculate_cost(os_type, num_cpu, num_gb_ram, num_gb_storage, time, spot = True, free_usage = free_usage)

        _calculate_savings_percent = lambda orig, new: np.nan if orig == 0 else (orig - new) / orig * 100

        return {
            'total-cost-savings': _calculate_savings_percent(on_demand_costs['total-cost'], spot_costs['total-cost']),
            'cpu-cost-savings': _calculate_savings_percent(on_demand_costs['cpu-cost'], spot_costs['cpu-cost']),
            'memory-cost-savings': _calculate_savings_percent(on_demand_costs['memory-cost'], spot_costs['memory-cost']),
            'os-license-cost-savings': _calculate_savings_percent(on_demand_costs['os-license-cost'], spot_costs['os-license-cost']),
            'storage-cost-savings': _calculate_savings_percent(on_demand_costs['storage-cost'], spot_costs['storage-cost']),
        }

if __name__ == '__main__':
    fargate_calc = AWSFargatePriceCalculator('us-west-1')

    print(
        fargate_calc.calculate_cost(
            os_type='linux-x86',
            num_cpu=1,
            num_gb_ram=2,
            num_gb_storage=20,
            time=60 * 10
        )
    )
