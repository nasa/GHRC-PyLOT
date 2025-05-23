import argparse
import inspect
import json
import os
from argparse import RawTextHelpFormatter, SUPPRESS
from inspect import getmembers, isfunction, ismethod

import boto3
from cumulus_api import CumulusApi
from ..helpers.pylot_helpers import PyLOTHelpers


def is_action_function(value):
    """
    Used to determine if the value passed in is a public method. The value passed in is assumed to be in the form
    module.function_name
    :param value: string to determine if it is a publish function or not
    :return: boolean
    """
    ret = True
    if isfunction(value) or ismethod(value):
        function_name = str(value).split('.', maxsplit=1)[-1]
        if function_name.startswith('_'):
            ret = False
    else:
        ret = False

    return ret


def extract_action_target_args(target_class=CumulusApi):
    """
    Extracts and processes all public member functions in the CumulusApi file and returns a dictionary of the form
    {"action": {"target": {arguments}}}
    These values are derived from the function signatures update_granule(self, data) where update, granule, and data are
    the action, target, and arguments respectively.
    """
    # Actions -> targets -> params
    action_target_dict = {}
    for member_function in getmembers(target_class, is_action_function):
        inspection = inspect.getfullargspec(member_function[1])
        args = inspection.args[1:]
        split_action_target = str(member_function[0]).split('_', maxsplit=1)
        action_target_dict.setdefault(
            split_action_target[0], {split_action_target[1]: args}
        )[split_action_target[1]] = args

    return action_target_dict


def generate_parser(subparsers, action_target_dict):
    cumulus_api_parser = subparsers.add_parser(
        'cumulus',
        help='This plugin provides a commandline interface to the cumulus api endpoints.',
        description='Provides commandline access to the cumulus api. To see available arguments '
                    'check the cumulus documentation here: https://nasa.github.io/cumulus-api/#cumulus-api\n'
                    'If more than 10 records are needed to be returned use the limit keyword argument: limit=XX\n'
                    'Examples: \n'
                    ' - pylot cumulus_api list collections fields="name,version"\n'
                    ' - pylot cumulus_api list collections fields="name,version" limit=12 name__in="msuttp,msutls"\n'
                    ' - pylot cumulus_api update granule \'{"collectionId": "nalmaraw___1", "granuleId": '
                    '"LA_NALMA_firetower_220706_063000.dat", "status": "completed"}\' \n'
                    ' - pylot cumulus_api update granule update.json\n',
        usage='<action> -h to see help for each action.',
        formatter_class=RawTextHelpFormatter
    )
    cumulus_api_parser.add_argument(
        '-o', '--output', metavar='file.json', help='specify a json file to write api response to.', nargs='?'
    )

    action_subparsers = cumulus_api_parser.add_subparsers(title='actions', dest='action', required=True)
    for action_k, target_v in action_target_dict.items():
        action_parser = action_subparsers.add_parser(
            action_k, help=f'{action_k} action for the cumulus API',
            usage=f'{action_k} <target> ',
            description=f'{action_k} action for the cumulus API'
        )
        target_subparsers = action_parser.add_subparsers(title='target', dest='target', required=True)
        for target_k, argument_v in target_v.items():
            plural = ''
            for arg in argument_v:
                plural.join(f'<{arg}> ')
            target_subparser = target_subparsers.add_parser(
                target_k, help='',
                usage=f'{target_k} {plural}',
                description=f'{target_k} target for cumulus API commands'
            )
            for argument in argument_v:
                if argument == 'data':
                    arg_help_text = f"a json file <filename>.json or a json string containing {target_k} {action_k}" \
                                    f" definition: \'{{\"field_1\": \"value_1\", \"field_2\": \"value_2\"}}\'"
                else:
                    arg_help_text = f'Provide a {argument}'
                target_subparser.add_argument(argument, nargs='?', help=arg_help_text, default='')
            pass
    pass


def return_parser(subparsers):
    new_command_dict = extract_action_target_args()
    return generate_parser(subparsers, new_command_dict)


def main(action, target, output=None, **kwargs):
    print(f'kwargs here: {kwargs}')
    capi = PyLOTHelpers().get_cumulus_api_instance()
    data_val = kwargs.get('data', None)
    if data_val:
        if os.path.isfile(data_val):
            print(f'Reading datafile: {data_val}')
            with open(data_val, 'r', encoding='utf-8') as file:
                kwargs.update({'data': json.load(file)})
        else:
            kwargs.update({'data': json.loads(data_val)})

    cumulus_api_lambda_return_limit = 100
    limit = kwargs.pop('limit', cumulus_api_lambda_return_limit)
    function_name = f'{action}_{target}'
    print(f'Calling Cumulus API: {function_name}')
    api_function = getattr(capi, function_name)
    results = []
    while True:
        api_response = api_function(**kwargs)
        if isinstance(api_response, dict) and 'results' in api_response:
            api_response = error_handling(api_response, api_function, **kwargs)
            kwargs.update({'page': api_response.get('meta', {}).get('page', 1) + 1})
            record_count = api_response.get('meta', {}).get('count', 0)
            api_results = api_response.get('results', [])            
            results.extend(api_results[:limit - (len(results))])
            if len(results) >= limit or len(results) >= record_count:
                break
        else:
            results = api_response
            break

    json_results = json.dumps(results, indent=2, sort_keys=True)
    if output:
        with open(output, 'w+', encoding='utf-8') as outfile:
            outfile.write(json_results)
        print(f'Results written to: {output}')
    else:
        print(json_results)

    return 0

def error_handling(results, api_function, **kwargs):
    ret = ''
    if results.get('error', '') == 'Bad Request':
        error_message = results.get('message', '')
        if 'Member must have length less than or equal to 8192' in error_message:
            print(f'Handling error: {error_message}')
            cli = boto3.client('s3')
            stack_prefix = os.getenv('STACK_PREFIX')
            if not stack_prefix:
                raise ValueError('The STACK_PREFIX environment variable has not been set')
            bucket = f'{stack_prefix}-internal'

            common_key_prefix = f'{stack_prefix}/workflows/'
            dgw = f'{common_key_prefix}DiscoverGranules.json'
            hww = f'{common_key_prefix}HelloWorldWorkflow.json'

            rsp = cli.get_object(
                Bucket=bucket,
                Key=dgw
            )
            dgw_full_path = f'/tmp/{dgw.rsplit("/", maxsplit=1)[-1]}'
            print(f'Writing {dgw} to {dgw_full_path}')
            with open(dgw_full_path, 'wb+') as local_file:
                local_file.write(rsp.get('Body').read())
                local_file.seek(0)

                cli.copy_object(
                    Bucket=bucket,
                    Key=dgw,
                    CopySource={
                        'Bucket': bucket,
                        'Key': hww
                    }
                )

                print('Reissuing API request...')
                ret = api_function(**kwargs)

                print(f'Uploading {dgw_full_path} to {dgw}')
                cli.put_object(
                    Body=local_file,
                    Bucket=bucket,
                    Key=dgw
                )

                ec = boto3.client('events')
                rule_name = f'{stack_prefix}-custom-{kwargs.get("data").get("name")}'
                res = ec.list_targets_by_rule(Rule=rule_name)
                print('Updating rule targets HelloWorldWorkflow -> DiscoverGranules')
                for target in res.get('Targets'):
                    if target.get('Id') == 'lambdaTarget':
                        input_json = json.loads(target.get('Input'))
                        definition = input_json.get('definition')
                        definition.update({
                            'arn': definition.get('arn').replace('HelloWorldWorkflow', 'DiscoverGranules'),
                            'definition': {},
                            'name': 'DiscoverGranules'
                        })
                        target.update({'Input': json.dumps(input_json)})

                ec.put_targets(Rule=rule_name, Targets=res.get('Targets'))
    else:
        ret = results
    return ret
