import argparse
import json
import os

import boto3


class OpenSearch:
    def __init__(self):
        pass

    @staticmethod
    def __read_json_file(filename):
        with open(filename, 'r', encoding='utf-8') as file:
            data = json.loads(file.read())

        return data

    def query_opensearch(self, query_data, record_type, limit=100, *args, **kwargs):
        # print(f'doing: {self.__name__}')
        lambda_arn = os.getenv('OPENSEARCH_LAMBDA_ARN')
        if not lambda_arn:
            raise Exception('The ARN for the OpenSearch lambda is not defined. Provide it as an environment variable.')

        # Invoke OpenSearch lambda
        data = self.__read_json_file(query_data)
        payload = {
            'query': data,
            'record_type': str(record_type).rstrip('s'),
            'limit': limit
        }
        print('Invoking OpenSearch lambda...')
        client = boto3.client('lambda')
        rsp = client.invoke(
            FunctionName=lambda_arn,
            Payload=json.dumps(payload).encode('utf-8')
        )
        if rsp.get('StatusCode') != 200:
            raise Exception(f'The OpenSearch lambda failed. Check the Cloudwatch logs for '
                            f'{os.getenv("OPENSEARCH_LAMBDA_ARN")}')

        # Download results from S3
        print('Downloading query results...')
        temp = rsp.get('Payload').read().decode('utf-8')
        ret_dict = json.loads(temp)
        s3_client = boto3.client('s3')
        rsp = s3_client.get_object(
            Bucket=ret_dict.get('bucket'),
            Key=ret_dict.get('key')
        )

        with open('query_results.json', 'w+', encoding='utf-8') as json_file:
            json.dump(rsp.get('Body').read().decode('utf-8'), fp=json_file, indent=2)

        ret = f'Query results: {os.getcwd()}/query_results.json'
        return ret


def return_parser(subparsers):
    # print('returning aopensearch parser')
    subparser = subparsers.add_parser('aopensearch')
    subparser.add_argument('-d', '--data', nargs='?', help='json file', metavar='')

    subparser = subparsers.add_parser('aopensearch', help='help_text', description='Descri')
    subparser.add_argument('opensearch arg', nargs='?', choices='choices', help=f'arg help', metavar='')

def a_test():
    return 'success'

def add_args(subparsers):
    # parser = argparse.ArgumentParser(prog='prog_a', description='Command line interface for OpenSearch.',
    #                                  usage=argparse.SUPPRESS)
    # parser.add_argument('query', choices=['opensearch'])
    # parser.add_argument('query', nargs='?', choices=['opensearch'], help='temp help', metavar='')

    # subparsers = parser.add_subparsers()
    subparser = subparsers.add_parser('opensearch')
    subparser.add_argument('-d', '--data', nargs='?', help='json file', metavar='')
    # parser.add_argument('query', nargs='?', choices=['opensearch'], help='temp help', metavar='')

    # subparser = subparsers.add_parser('query', help=f'[opensearch]')
    # subparser.add_argument('-d', '--d', nargs='?', help='json file')

    # return parser
