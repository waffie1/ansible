#!/usr/bin/python
# This file is part of Ansible

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}

DOCUMENTATION = '''
---
module: lambda_version
short_description: Creates and deletes lambda function versions
description:
  - Publishes a new version of a function when $LATEST is newer than the last version
  - Deletes a specific function version when absent
requirements:
  - boto3 >= 1.0.0
  - python >= 2.6
version_added: "2.10"
author:
    - Kevin Coming (@waffie1)
options:
    code_sha_256:
        description:
            - Only publish a version if the hash value matches the value that's specified.
            - Use this option to avoid publishing a version if the function code has changed since you last updated it.
        type: str
    function_name:
        description:
            - The name or arn of the function that a new version will be published for.
        type: str
        required: true
    function_version:
        description:
            - The function version to delete.
            - Required if I(state=present).
        type: str
    revision_id:
        description:
            - Only publish a version if the revision ID matches the ID that's specified.
            - Use this option to avoid publishing a version if the function configuration has changed since you last updated it.
        type: str
    version_description:
        description:
            - Only publish a version if the hash value matches the value that's specified.
            - A description for the version to override the description in the function configuration.

extends_documentation_fragment:
    - aws
    - ec2
'''

EXAMPLES = r'''
---
# Note: These examples do not set authentication details, see the AWS Guide for details.

# Publish a new version if $LATEST is newer than last published version.
- lambda_version:
    function_name: LambdaFunctionName

# Publish a new version with a description if $LATEST is newer than last published version.
- lambda_version:
    function_name: LambdaFunctionName
    function_description: Function Version Description

# Delete a function version
- lambda_version:
    state: absent
    function_name: LambdaFunctionName
    function_version: 10
'''

RETURN = r'''
---
version:
    description: Configuration details of the lambda function version, as returned by boto3 publish_version
    returned: present
    type: dict
    contains:
        code_sha256:
            description: The SHA256 hash of the function's deployment package.
            type: str
            returned: present
            sample: fNGeOhSxAjcYuNyGJaC8XbYFghjTXjpUuLttdt5xkPk=
        code_size:
            description: The size of the function's deployment package, in bytes.
            type: int
            returned: present
            sample: 1514
        description:
            description: The function's description.
            type: str
            returned: present
            sample: My Description
        environment:
            description: The function's environment variables.
            type: dict
            returned: present
            contains:
                Variables:
                    description: lambda function environment variables
                    type: dict
                    returned: present
                    sample:
                        MY_VAR: my_value
        function_arn:
            description: The function's Amazon Resource Name (ARN).
            type: str
            returned: present
            sample: arn:aws:lambda:us-east-1:0123456789ab:function:MyFunction:1
        function_name:
            description: The name of the function.
            type: str
            returned: present
            sample: MyFunction
        handler:
            description: The function that Lambda calls to begin executing your function.
            type: str
            returned: present
            sample: lambda_function.lambda_handler
        last_modified:
            description: The date and time that the function was last updated, in ISO-8601 format (YYYY-MM-DDThh:mm:ss.sTZD).
            type: str
            returned: present
            sample: 2019-12-30T14:25:24.026+0000
        memory_size:
            description: The memory that's allocated to the function.
            type: int
            returned: present
            sample: 128
        revision_id:
            description: The latest updated revision of the function or alias.
            type: str
            returned: present
            sample: 06eeb565-3d98-5cde-a955-87634628623a
        role:
            description: The function's execution role.
            type: str
            returned: present
            sample: arn:aws:iam::0123456789ab:role/MyRole
        runtime:
            description: The runtime environment for the Lambda function.
            type: str
            returned: present
            sample: python3.7
        timeout:
            description: The amount of time that Lambda allows a function to run before stopping it.
            type: int
            returned: present
            sample: 10
        tracing_config:
            description:
            type: dict
            returned: present
            contains:
                mode:
                    description: Tracing config mode
                    sample: PassThrough
        version:
            description: The version of the Lambda function.
            type: str
            returned: present
            sample: '1'
        vpc_config:
            description: The function's networking configuration.
            type: dict
            returned: present
            contains:
                security_group_ids:
                    description: A list of VPC security groups IDs.
                    type: list
                subnet_ids:
                    description: A list of VPC subnet IDs.
                    type: list
                vpc_id :
                    description: The ID of the VPC.
                    type: str
'''


import botocore
import traceback
from ansible.module_utils.aws.core import AnsibleAWSModule
from ansible.module_utils.ec2 import camel_dict_to_snake_dict
from datetime import datetime


class LambdaVersion:
    def __init__(self, module):
        self.boto3_params = {}
        self.function_name = module.params['function_name']
        self.state = module.params['state']

        self.client = module.client('lambda')
        try:
            paginator = self.client.get_paginator('list_versions_by_function')
            self.versions = paginator.paginate(FunctionName=self.function_name).build_full_result().get('Versions')
        except self.client.exceptions.ResourceNotFoundException:
            self.versions = None
        except botocore.exceptions.ClientError as e:
            module.fail_json_aws(e, msg='Error retrieving version info for function %s' % self.function_name)

        self.module = module

    # Returns True if the supplied version exists
    def check_version_exists(self, function_version):
        for item in self.versions:
            if item['Version'] == function_version:
                return True

    def create_version(self):
        # These seem to be sorted already, but not taking chances.  $LATEST will be last on list
        self.versions.sort(key=lambda k: str(datetime.max) if k['Version'] == '$LATEST' else k['LastModified'])
        latest_version = self.versions.pop()
        last_version = self.versions.pop()
        if latest_version['LastModified'] > last_version['LastModified']:
            params = {'FunctionName': self.function_name}
            if self.module.params.get('version_description', None):
                params['Description'] = self.module.params['version_description']
            if self.module.params.get('code_sha_256', None):
                params['CodeSha256'] = self.module.params['code_sha_256']
            if self.module.params.get('revision_id', None):
                params['RevisionId'] = self.module.params['revision_id']
            try:
                result = self.client.publish_version(**params)
            except self.client.exceptions.PreconditionFailedException:
                return {'changed': False, 'msg': 'revision_id does not match $LATEST'}
            except self.client.exceptions.InvalidParameterValueException:
                return {'changed': False, 'msg': 'code_sha_256 does not match $LATEST'}
            except botocore.exceptions.ClientError as e:
                module.fail_json_aws(e, msg='Error publishing new version for function {0}'.format(self.function_name))
            else:
                del(result['ResponseMetadata'])
                version = camel_dict_to_snake_dict(result, ignore_list=['Environment'])
                return {'changed': True, 'version': version}
        else:
            version = camel_dict_to_snake_dict(latest_version, ignore_list=['Environment'])
            return {'changed': False, 'version': version}

    def delete_version(self):
        if not self.module.params['function_version']:
            self.module.fail_json(msg='Cannot delete a version without function_version parameter')

        # API calls always succeeds deleting a version that does not exist, just exit
        # early if the version doesn't exist
        if not self.check_version_exists(self.module.params['function_version']):
            return {'changed': False}
        try:
            self.client.delete_function(FunctionName=self.function_name,
                                        Qualifier=self.module.params['function_version'])
        except (self.client.exceptions.ResourceNotFoundException,
                self.client.exceptions.ResourceConflictException,
                botocore.exceptions.ClientError) as e:
            self.module.fail_json_aws(e, msg='Error deleting version %s for function %s' % (
                    function_version, function_name))
        else:
            return {'changed': True}

    def run(self):
        if not self.versions:
            if self.state == 'present':
                self.module.fail_json(msg='Cannot create a version for function {0}.  Function does not exist.'.format(
                                      self.function_name))
            else:
                return {'changed': False}
        else:
            if self.state == 'present':
                return self.create_version()
            else:
                return self.delete_version()


def main():
    argument_spec = dict(
        code_sha_256=dict(),
        function_name=dict(type=str, required=True),
        function_version=dict(type=str),
        revision_id=dict(),
        state=dict(default='present', choices=['present', 'absent']),
        version_description=dict(type=str)
    )

    module = AnsibleAWSModule(argument_spec=argument_spec, supports_check_mode=True,)
    result = LambdaVersion(module).run()
    module.exit_json(**result)


if __name__ == '__main__':
    main()
