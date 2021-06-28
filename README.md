check-reserved-instances
--------------------------

Check Reserved Instances - Compare instance reservations with running
instances

Amazon ís reserved instances are a great way to save money when using
EC2, RDS, ElastiCache, etc. An instance reservation is specified by an
availability zone, instance type, and quantity. Correlating the
reservations you currently have active with your running instances is a
manual, time-consuming, and error prone process.

This quick little Python script uses boto3 to inspect your reserved
instances and running instances to determine if you currently have any
reserved instances which are not being used. Additionally, it will give
you a list of non-reserved instances which could benefit from additional
reserved instance allocations. The report may also be sent via email.

`Regional Benefit Reserved Instances`_ are also supported!

Installation
------------

Copy script from repository:

::

    $ vim awsid.py
    $ vim check-reserved-instances.py

Configuration
-------------

A sample configuration file is provided for easy use. By default, the
script loads the configuration from awsid.py in the current directory.

::

    $ vim awsid.py

Configuring AWS Accounts/Credentials
------------------------------------

    # our accounts with cross account role "backup-node" based auth
    accounts = {
        "account_id": ['awsid'],
	    "Lineate Infrastructure": ['059209358064'],
    }

    # accounts with auth via API keys. Format - "aws_account_name": ['aws_access_key', 'aws_secret_key']
    standalone_accounts = {
        "Yandex": ['aws_access_key', 'aws_secret_key'],
    }
    
    # Instances ID with reservation
    iidlist = {
        'i-09c914a528b2074c7': 's2s-vpn00-RI',
    }

Usage
-----

Ideally, this script should be ran in a cronjob:

::

    # Run on the 12:00 of every day
    0 12 * * * /opt/aws/check-reserved-instances/check-reserved-instances.py

For one-time use, execute the script:

::

    $ python /opt/aws/check-reserved-instances/check-reserved-instances.py
    ===> EC2 Infrastructure -> AWS EC2 Reserved Instances - {'Infrastructure': {'unreserved_instances': {('t3a.large', 'eu-central-1a'): 1}, 'unused_reservations': {}}}

Required IAM Permissions
------------------------

The following example IAM policy is the minimum set of permissions
needed to run the reporter:

::

    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:DescribeInstances",
                    "ec2:DescribeReservedInstances",
                    "ec2:DescribeAccountAttributes",
                    "rds:DescribeDBInstances",
                    "rds:DescribeReservedDBInstances",
                    "elasticache:DescribeCacheClusters",
                    "elasticache:DescribeReservedCacheNodes"
                ],
                "Resource": "*"
            }
        ]
    }

----------------------------------------------------
