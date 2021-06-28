#!/usr/bin/env python

"""
awsri :: check AWS EC2 Reserved Instances

TODO:

"""


__version__ = "0.5.1"
__author__ = "Ivan Ivanov"
__editor__ = ""
__license__ = "WTFL"

import requests
from argparse import ArgumentParser
from operator import itemgetter
from awsid import accounts, standalone_accounts, iidlist
from email.mime.text import MIMEText
from time import gmtime, strftime, localtime
from boto3.exceptions import botocore
import smtplib
import boto3
import json
from pprint import pprint
from datetime import datetime, timedelta

from collections import defaultdict
import datetime
import re
import six
from dateutil.tz import tzutc

parser = ArgumentParser(description='AWS RI checker')
parser.add_argument('-m', '--mode', help='RI checker mode: standalone/role or both. '
                                         'Space separated. By default - both.',
                    nargs='+', dest='mode', required=False, default=['standalone', 'role'])
parser.add_argument('-r', '--recipients', help='List of emails for send notifications. '
                                               'Space separated. By default - systems-mgmt@lineate.com',
                    nargs='+', dest='recipients', required=False, default=['systems-mgmt@lineate.com'])
parser.add_argument('-w', '--warn-time', help='Expire period for reserved instances in days. '
                                              'Default is 30 days',
                    dest='warn_time', type=int, required=False, default=30,)

arguments = parser.parse_args()


# some options
sender = 'aws-ri-checker@ase.ops.lineate.com'

# get current time and initialize empty list for untagged resources
tnow = strftime("%a %h %d %H:%M:%S %Z %Y", localtime())

datamsg = []

# instance IDs/name to report with unreserved instances
instance_ids = defaultdict(list)

# reserve expiration time to report with unused reservations
reserve_expiry = defaultdict(list)

# global results for all accounts
#results = {
#    'ec2_running_instances': {},
#    'ec2_reserved_instances': {},
#    'elc_running_instances': {},
#    'elc_reserved_instances': {},
#    'rds_running_instances': {},
#    'rds_reserved_instances': {},
#}


# function for output
def prepare_output(service, acc_id, reg, resource_name, error_msg):
    if reg is None:
        formatted_msg = '===> {} {} -> {} - {}'.format(service, acc_id, resource_name, error_msg)
    else:
        formatted_msg = '===> {} {} -> {} -> {} - {}'.format(service, acc_id, reg, resource_name, error_msg)
    datamsg.append(formatted_msg)
    return formatted_msg


# function to get temporary credentials
def get_tmp_cred(awsid):
    sts_client = boto3.client('sts')
    sts_response = sts_client.assume_role(
        RoleArn="arn:aws:iam::" + awsid + ":role/backup-node",
        RoleSessionName="AssumeRoleSession"
    )
    access_key_id = sts_response['Credentials']['AccessKeyId']
    secret_access_key = sts_response['Credentials']['SecretAccessKey']
    session_token = sts_response['Credentials']['SessionToken']
    return access_key_id, secret_access_key, session_token


# function to describe regions
def describe_regions():
    sts_ak, sts_sak, sts_sk = get_tmp_cred("059209358064")
    ec2_conn = boto3.client('ec2', aws_access_key_id=sts_ak,
                            aws_secret_access_key=sts_sak,
                            aws_session_token=sts_sk,
                            region_name='us-east-1')
    regions = [region['RegionName'] for region in ec2_conn.describe_regions()['Regions']]
    return regions


# function to check for expiration reserved instances
def get_exp_ri(regions):
    aws_service = 'EC2 Reserved Instances'
    for account_id in aws_id_list:
        for region in regions:
            if check_mode == 'standalone':
                ec2_conn = boto3.client('ec2', aws_access_key_id=standalone_accounts[account_id][0],
                                        aws_secret_access_key=standalone_accounts[account_id][1],
                                        region_name=region)
            else:
                sts_ak, sts_sak, sts_sk = get_tmp_cred(accounts[account_id][0])
                ec2_conn = boto3.client('ec2', aws_access_key_id=sts_ak,
                                        aws_secret_access_key=sts_sak,
                                        aws_session_token=sts_sk,
                                        region_name=region)

            reserved_instances = {}
            reservations = ec2_conn.describe_reserved_instances()
            now = datetime.datetime.utcnow().replace(tzinfo=tzutc())
            for ri in reservations['ReservedInstances']:
                if ri['State'] not in ('active', 'payment-pending'):
                    continue
                key = (ri['ProductDescription'], ri['InstanceType'], ri['End'])

                reserved_instances[key] = \
                    reserved_instances.get(key, 0) + ri['InstanceCount']
                expire_time = ri['Start'] + datetime.timedelta(seconds=ri['Duration'])
                if (expire_time - now) < datetime.timedelta(days=arguments.warn_time):
                    print(prepare_output(aws_service, account_id, region, key, "Soon expire"))


def calc_expiry_time(expiry):
    return (expiry.replace(tzinfo=None) - datetime.datetime.utcnow()).days


def report_diffs(running_instances, reserved_instances):
    instance_diff = {}
    regional_benefit_ris = {}
    # loop through the reserved instances
    for placement_key in reserved_instances:
        # if the AZ from an RI is 'All' (regional benefit RI)
        if placement_key[1] == 'All':
            # put into another dict for these RIs for processing later
            regional_benefit_ris[placement_key[0]] = reserved_instances[
                placement_key]
        else:
            instance_diff[placement_key] = reserved_instances[
                placement_key] - running_instances.get(placement_key, 0)

    # add unreserved instances to instance_diff
    for placement_key in running_instances:
        if placement_key not in reserved_instances:
            instance_diff[placement_key] = -running_instances[
                placement_key]

    # loop through regional benefit RI's
    for ri in regional_benefit_ris:
        # loop through the entire instace diff
        for placement_key in instance_diff:
            # find unreserved instances with the same type as the regional benefit RI
            if (placement_key[0] == ri and placement_key[1] != 'All' and
                    instance_diff[placement_key] < 0):
                # loop while incrementing unreserved instances (less than 0)
                # and decrementing count of regional benefit RI's
                while True:
                    if (instance_diff[placement_key] == 0 or
                            regional_benefit_ris[ri] == 0):
                        break
                    instance_diff[placement_key] += 1
                    regional_benefit_ris[ri] -= 1

        instance_diff[(ri, 'All')] = regional_benefit_ris[ri]

    unused_reservations = {key: value for key, value in
                           instance_diff.items() if value > 0}
    unreserved_instances = {key: -value for key, value in
                            instance_diff.items() if value < 0}

    qty_running_instances = 0
    for instance_count in running_instances.values():
        qty_running_instances += instance_count

    qty_reserved_instances = 0
    for instance_count in reserved_instances.values():
        qty_reserved_instances += instance_count

    qty_unreserved_instances = 0
    for instance_count in unreserved_instances.values():
        qty_unreserved_instances += instance_count
    return {
        'unused_reservations': unused_reservations,
        'unreserved_instances': unreserved_instances,
        #'qty_running_instances': qty_running_instances,
        #'qty_reserved_instances': qty_reserved_instances,
        #'qty_unreserved_instances': qty_unreserved_instances,
    }


# function to check for unused reservation
def get_run_res_instances(regions):
    results = {}
    aws_service = 'EC2'
    resource_name = 'AWS EC2 Reserved Instances'
    for account_id in aws_id_list:
        results = {
            'ec2_running_instances': {},
            'ec2_reserved_instances': {}}
        for region in regions:
            if check_mode == 'standalone':
                ec2_conn = boto3.client('ec2', aws_access_key_id=standalone_accounts[account_id][0],
                                        aws_secret_access_key=standalone_accounts[account_id][1],
                                        region_name=region)
            else:
                sts_ak, sts_sak, sts_sk = get_tmp_cred(accounts[account_id][0])
                ec2_conn = boto3.client('ec2', aws_access_key_id=sts_ak,
                                        aws_secret_access_key=sts_sak,
                                        aws_session_token=sts_sk,
                                        region_name=region)
            paginator = ec2_conn.get_paginator('describe_instances')
            page_iterator = paginator.paginate(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
            # Loop through running EC2 instances and record their AZ, type, and
            # Instance ID or Name Tag if it exists.
            for page in page_iterator:
                for reservation in page['Reservations']:
                    for instance in reservation['Instances']:
                        az = instance['Placement']['AvailabilityZone']
                        instance_type = instance['InstanceType']
                        instance_id = instance['InstanceId']
                        instance_name = None
                        if instance_id in iidlist:
                            results['ec2_running_instances'][(instance_type, az)] = results['ec2_running_instances'].get((instance_type, az), 0) + 1
                            instance_ids[(instance_type, az)].append(instance['InstanceId'] if not instance_name else instance_name)
            # Loop through active EC2 RIs and record their AZ and type.
            for reserved_instance in ec2_conn.describe_reserved_instances(
                    Filters=[{'Name': 'state', 'Values': ['active']}])[
                    'ReservedInstances']:
                # Detect if an EC2 RI is a regional benefit RI or not
                if reserved_instance['Scope'] == 'Availability Zone':
                    az = reserved_instance['AvailabilityZone']
                else:
                    az = 'All'
                instance_type = reserved_instance['InstanceType']
                results['ec2_reserved_instances'][(
                    instance_type, az)] = results[
                    'ec2_reserved_instances'].get(
                    (instance_type, az), 0) + reserved_instance['InstanceCount']
                reserve_expiry[(instance_type, az)].append(calc_expiry_time(
                    expiry=reserved_instance['End']))
            # function to get report
        report = {}
        acc_id = account_id
        error_msg = report
        reg = None
        report[account_id] = report_diffs(
            results['ec2_running_instances'],
            results['ec2_reserved_instances'])
        print(prepare_output(aws_service, acc_id, reg, resource_name, error_msg))
    return results


# function that send report resources to sysadmins
def send_2_admins():
    fmsg = '\n'.join(datamsg)
    if len(datamsg) > 0:
        msg = MIMEText(str(fmsg))
        msg['Subject'] = 'Status of AWS Reserved Instances ' + tnow
        msg['From'] = sender
        msg['To'] = ", ".join(arguments.recipients)
        s = smtplib.SMTP('localhost')
        s.sendmail(sender, arguments.recipients, msg.as_string())
        s.quit()


def runner():
    regions = describe_regions()
#    get_exp_ri(regions)
    get_run_res_instances(regions)


# call this sh1t
if __name__ == "__main__":
    for mode in arguments.mode:
        check_mode = mode
        if check_mode == 'standalone':
            aws_id_list = sorted(standalone_accounts, key=itemgetter(0))
        else:
            aws_id_list = sorted(accounts, key=itemgetter(0))
        runner()
    send_2_admins()
