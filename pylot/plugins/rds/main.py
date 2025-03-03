import argparse
import inspect
import json
import os
import pathlib
from time import sleep

import boto3
import concurrent.futures

from tabulate import tabulate

from pylot.plugins.cumulus.main import is_action_function
from pylot.plugins.helpers.pylot_helpers import PyLOTHelpers
from cumulus_api import CumulusApi


class QueryRDS:
    @staticmethod
    def read_json_file(filename, **kwargs):
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.loads(file.read())

        return data

    def invoke_rds_lambda(self, query_data, lambda_client=None, **kwargs):
        if not lambda_client:
            lambda_client = boto3.client('lambda')
        lambda_arn = os.getenv('RDS_LAMBDA_ARN')
        if not lambda_arn:
            raise ValueError('The ARN for the RDS lambda is not defined. Provide it as an environment variable.')

        # Invoke RDS lambda
        print('Invoking RDS lambda...')
        rsp = lambda_client.invoke(
            FunctionName=lambda_arn,
            Payload=json.dumps(query_data).encode('utf-8')
        )
        if rsp.get('StatusCode') != 200:
            raise Exception(
                f'The RDS lambda failed. Check the Cloudwatch logs for {os.getenv("RDS_LAMBDA_ARN")}'
            )

        return rsp

    def download_file(self, bucket, key, results, s3_client=None):
        if not s3_client:
            s3_client = boto3.client('s3')
        print('Downloading query results...')
        s3_client.download_file(
            Bucket=bucket,
            Key=key,
            Filename=f'{os.getcwd()}/{results}'
        )

        file = f'{os.getcwd()}/{results}'
        return file


def query_rds(query, results='query_results.json', **kwargs):
    rds = QueryRDS()
    if isinstance(query, str) and os.path.isfile(query):
        query = rds.read_json_file(query)
    else:
        query = json.loads(query)

    query = {'rds_config': query, 'is_test': True}

    rsp = rds.invoke_rds_lambda(query)
    ret_dict = json.loads(rsp.get('Payload').read().decode('utf-8'))

    # Download results from S3
    file = rds.download_file(bucket=ret_dict.get('bucket'), key=ret_dict.get('key'), results=results)
    print(
        f'{ret_dict.get("count")} {query.get("rds_config").get("records")} records obtained: '
        f'{os.getcwd()}/{results}'
    )
    return file


def return_parser(subparsers):
    query = {
        'records': 'granules',
        'where': 'name LIKE nalma%% ',
        'columns': ['granule_id', 'status'],
        'limit': 10
    }
    subparser = subparsers.add_parser(
        'rds',
        description='This plugin can send queries to the RDS lambda to directly query the Cumulus RDS. It can also apply '
             'Cumulus API functions to query results either from a query results file or immediately after querying.',
        help='Submit queries to the Cumulus RDS instance.\n'
                    f'Example query: {json.dumps(query)}',
        argument_default=argparse.SUPPRESS
    )
    subparser.add_argument(
        '-i', '--input',
        help='The name of the input file containing RDS query results. You should specify an appripriate action when using this. See -a \n'
             'Example: pylot rds -i input.json -a apply_workflow_to_granule -args workflow_name=PublishGranule',
        metavar=''
    )
    subparser.add_argument(
        '-q', '--query',
        help='A file containing an RDS Lambda query: <filename>.json or a json query string '
             'using the RDS DSL syntax: https://github.com/ghrcdaac/ghrc_rds_lambda?tab=readme-ov-file#querying\n'
             f'Example: {json.dumps(query)}',
        metavar=''
    )
    subparser.add_argument(
        '-o', '--output',
        help='The name to give to the query results file.',
        metavar='',
        default='query_results.json'
    )
    subparser.add_argument(
        '-l', '--list-cumulus-api-methods',
        help='Use this argument to list available API methods that can be applied to input files. '
             'Partial strings can be provided to view relevant endpoints. "granule" will list all granule related endpoints.',
        metavar='',
        nargs='?',
        const=''
    )
    subparser.add_argument(
        '-a', '--api-action',
        nargs='?',
        help='Apply the specified Cumulus API action to each element of the query results.'
             'There will be an attempt to pull necessary parameters from the query results or input file but you may need to '
             'provide additional arguments. see -args',
        metavar=''
    )
    subparser.add_argument(
        '-args', '--api-arguments',
        nargs='+',
        help='Additional arguments an API action may require and should be provides as "name_1=value_1 name_2=value_2"',
        metavar=''
    )

def list_methods(input):
    capi = CumulusApi
    res = inspect.getmembers(capi, is_action_function)
    table = []
    for item in res:
        if input in item[0]:
            spec = inspect.getfullargspec(item[1])
            args = ', '.join(spec.args[1:])
            table.append([item[0], args])

    print(tabulate(table, headers=['Function Name', 'Parameters'], tablefmt='psql'))
    print('API Documentation: https://nasa.github.io/cumulus-api/ \n')

def read_json_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as infile:
        res = json.load(infile)
    return res

def apply_api_action(results, action, api_arg_dict):
    capi = PyLOTHelpers.get_cumulus_api_instance()
    capi_function = getattr(capi, action)
    spec = inspect.getfullargspec(capi_function)
    required_args = spec.args[1:]
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        count = 0
        for record in results:
            call_args = {}
            for required_arg in required_args:
                call_args.update({required_arg: record.get(required_arg, api_arg_dict.get(required_arg))})
            print(f'Executing: {action}({call_args})')
            futures.append(executor.submit(capi_function, **call_args))
            count += 1
            if count == 10:
                print('Ten submissions made, sleeping for 1 second...')
                count = 0
                sleep(1)
        for future in concurrent.futures.as_completed(futures):
            print(future.result())

def main(**kwargs):
    if 'list_cumulus_api_methods' in kwargs:
        list_methods(kwargs['list_cumulus_api_methods'])

    else:
        if 'input' in kwargs:
            input_file = kwargs['input']
        elif 'query' in kwargs:
            input_file = query_rds(kwargs['query'])
        else:
            raise ValueError('An input file or query file are required but neither have been provided.')

        res = read_json_file(input_file)
        if 'api_action' in kwargs and len(res) > 0:
            action = kwargs['api_action']
            api_arg_dict = {}
            if 'api_arguments' in kwargs:
                api_args = kwargs['api_arguments']
                for arg in api_args:
                    key_val_list = arg.split('=')
                    api_arg_dict.update({key_val_list[0]: key_val_list[1]})

            apply_api_action(res, action, api_arg_dict)

    return 0
