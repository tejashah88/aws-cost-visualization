# Source: https://www.sentiatechblog.com/retrieving-all-region-codes-and-names-with-boto3

import boto3

class AWSRegions:
    # Note: Need to specify a default region or Boto3 will complain
    ssm = boto3.client('ssm', 'us-east-1')

    @classmethod
    def fetch_regions(cls):
        short_codes = cls._fetch_region_short_codes()

        regions = [{
            'name': cls._fetch_region_long_name(sc),
            'code': sc
        } for sc in short_codes]

        regions_sorted = sorted(
            regions,
            key=lambda k: k['name']
        )

        return regions_sorted

    @classmethod
    def _fetch_region_long_name(cls, short_code):
        param_name = (
            '/aws/service/global-infrastructure/regions/'
            f'{short_code}/longName'
        )
        response = cls.ssm.get_parameters(
            Names=[param_name]
        )
        return response['Parameters'][0]['Value']

    @classmethod
    def _fetch_region_short_codes(cls):
        output = set()
        for page in cls.ssm.get_paginator('get_parameters_by_path').paginate(
            Path='/aws/service/global-infrastructure/regions'
        ):
            output.update(p['Value'] for p in page['Parameters'])

        return output

if __name__ == '__main__':
    aws_regions = AWSRegions()
    print(aws_regions.fetch_regions())
