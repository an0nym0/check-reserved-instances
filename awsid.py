#!/usr/bin/python

# our accounts with cross account role "backup-node" based auth
accounts = {
	"account_id": ['awsid'],
}

# accounts with auth via API keys. Format - "aws_account_name": ['aws_access_key', 'aws_secret_key']
standalone_accounts = {
    "account_id": ['aws_access_key', 'aws_secret_key'],
}

# Instances ID with reservation
iidlist = {
	'instanse_id': 'instance-name',
}
