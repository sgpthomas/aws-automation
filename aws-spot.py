#!/usr/bin/env python3

import argparse
import subprocess
import json
import os
from paramiko import RSAKey, SSHClient, AutoAddPolicy
from pathlib import Path
from time import sleep
import glob

IMAGE_ID = "ami-5d2dcf3e" # scheduler image
SECURITY_GROUP = "sg-8f621df7"
INSTANCE_TYPE = 'c4.4xlarge'
REGION = 'us-west-1'

KEY = "tiger"
KEYFILE = "~/.ssh/{}.pem".format(KEY)

PORT = 3000
NUMCLIENTS = 100
OUTPUTDIR = "~/output"

def get_instances(region):
    proc = subprocess.run(['aws', 'ec2', 'describe-instances',
                           '--region', region], stdout=subprocess.PIPE)
    instances_data = json.loads(proc.stdout)
    reservations = instances_data['Reservations']
    return {instance['InstanceId']: instance
            for instance in list(map(lambda r: r['Instances'][0], reservations))
            if instance['State']['Name'] != 'terminated'}

def start_scheduler():
    cmd = ['aws', 'ec2', 'run-instances',
           '--image-id', IMAGE_ID,
           '--instance-type', INSTANCE_TYPE,
           '--key-name', KEY,
           '--security-group-ids', SECURITY_GROUP,
           '--region', REGION,
           '--tag-specifications',
           'ResourceType=instance,Tags=[{}Key=Name,Value=scheduler{}]'.format('{','}')]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE)
    iid = json.loads(proc.stdout)['Instances'][0]['InstanceId']
    print("Starting {}...".format(iid), end="", flush=True)

    instance = get_instances(REGION)[iid]
    while instance['State']['Name'] != 'running':
        sleep(3)
        instance = get_instances(REGION)[iid]

    print("Started!")

    k = RSAKey.from_private_key_file(Path(KEYFILE).expanduser())
    c = SSHClient()
    c.set_missing_host_key_policy(AutoAddPolicy())

    ip = instance['PublicIpAddress']
    print("Connecting to {}".format(ip))
    c.connect(hostname=ip, username="ubuntu", pkey=k)

    # send progress if there is any
    archives = glob.glob('archive/*.tar')
    if len(archives) > 0:
        tar = archives[0]
        print("Sending {}...".format(tar), end="", flush=True)
        sftp = c.open_sftp()
        def transfer_progress(completed, todo):
            print("\rSending {}...{:.2%}".format(tar, completed/todo), end="", flush=True)
        sftp.put(tar, "{}".format(Path(tar).name), callback=transfer_progress)
        print("\rSending {}...Done!  ".format(tar))

        print("Unpacking archives...", end="", flush=True)
        cmd = 'tar -xf {}'.format(Path(tar).name)
        c.exec_command(cmd)
        print("Done!")

    # start the scheduler
    print("Starting scheduler...", end="", flush=True)
    cmd = "tmux new -d -s scheduler './sklearn-pmlb-benchmarks/src/scheduler.py --resume {} --max-connections {}'".format(OUTPUTDIR, NUMCLIENTS)

    c.exec_command(cmd)
    c.close()
    print("Done!")
    print("Started at {}:{}".format(instance['PrivateIpAddress'], PORT))

def finish_scheduler():
    print("[wip] stop")

def start_spot():
    cmd = ['aws', 'ec2', 'request-spot-fleet',
           # '--dry',
           '--region', REGION,
           '--spot-fleet-request-config', 'file://config.json'
    ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE)
    spot_id = json.loads(proc.stdout)['SpotFleetRequestId']
    print("Started {}!".format(spot_id))

def info_spot():
    cmd = ['aws', 'ec2', 'describe-spot-fleet-requests']
    proc = subprocess.run(cmd, stdout=subprocess.PIPE)
    configs = json.loads(proc.stdout)['SpotFleetRequestConfigs']
    active_requests = {conf['SpotFleetRequestId']: conf for conf in configs if
                       conf['SpotFleetRequestState'] == "active"}

    for sfr, data in active_requests.items():
        cmd = ['aws', 'ec2', 'describe-spot-fleet-instances',
               '--spot-fleet-request-id', sfr]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE)
        output = json.loads(proc.stdout)['ActiveInstances']
        for info in output:
            print("{} : {}".format(info['InstanceId'], info['InstanceType']))
    # for conf in configs:
    #     print(conf['SpotFleetRequestId'], conf['SpotFleetRequestState'])
    # cmd = ['aws', 'ec2', 'des',
    #        '--spot-instance-request-ids', spot_id]


def cancel_spot():
    cmd = ['aws', 'ec2', 'cancel-spot-instance-requests',
           '--spot-instance-request-ids', spot_id]


choices = {"start-scheduler": start_scheduler,
           "finish-scheduler": finish_scheduler,
           "start-spot": start_spot,
           "info-spot": info_spot,
           "cancel-spot": cancel_spot
}

def make_parser():
    descr = "Tool to automate AWS Spot Instances."
    parser = argparse.ArgumentParser(description=descr)

    parser.add_argument("command", action="store", choices=list(choices.keys()))

    return parser

if __name__ == "__main__":
    options = make_parser().parse_args()

    choices[options.command]()
