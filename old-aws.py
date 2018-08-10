#!/usr/bin/env python3

import argparse
import subprocess
import json
import os
from paramiko import RSAKey, SSHClient, AutoAddPolicy
from pathlib import Path


IMAGE_ID = 'ami-003caac684d26c013'
SECURITY_ID = 'sg-0986839b16b02894f'

KEY = "tiger"
KEYFILE = "~/.ssh/{}.pem".format(KEY)

SCHEDULER = 'scheduler'
CLIENTS = 'clients'
ALL = 'all'
CONNECT = 'connect'
TERMINATE = 'terminate'
COPY = 'copy'
NEW = 'new'
START = 'start'
START_SCHEDULER = 'start-scheduler'

choices = [SCHEDULER, CLIENTS, ALL, CONNECT, TERMINATE, COPY, NEW, START, START_SCHEDULER]

def make_parser():
    descr = "Tool to automate AWS things."
    parser = argparse.ArgumentParser(description=descr)

    parser.add_argument("info_type", action="store", choices=choices)
    parser.add_argument("--region", action="store", default="us-west-1")
    parser.add_argument("--pub-ip", action="store_true")
    parser.add_argument("--priv-ip", action="store_true")
    parser.add_argument("--tags", action="store_true")
    parser.add_argument("--state", action="store_true")
    parser.add_argument("--iid", action="store", nargs='*')
    parser.add_argument("--name", action="store", nargs='*')
    parser.add_argument("--path", action="store")
    parser.add_argument("-r", "--recursive", action="store_true")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--type", action="store", type=str, default="t2.micro")
    parser.add_argument("--scheduler", action="store", type=str)
    parser.add_argument("--port", action="store", type=int)
    parser.add_argument("--start", action="store", type=int, default=0)
    parser.add_argument("--count", action="store", type=int)
    parser.add_argument("--basename", action="store")

    return parser

def get_instances(region):
    proc = subprocess.run(['aws', 'ec2', 'describe-instances',
                           '--region', region], stdout=subprocess.PIPE)
    instances_data = json.loads(proc.stdout)
    reservations = instances_data['Reservations']
    # print(len(reservations[7]['Instances']))

    res = {}

    for r in reservations:
        for inst in r['Instances']:
            if inst['State']['Name'] != 'terminated':
                res[inst['InstanceId']] = inst
    return res
    # return {instance['InstanceId']: instance
    #         for instance in list(map(lambda r: r['Instances'][0], reservations))
    #         if instance['State']['Name'] != 'terminated'}

def parse_tags(instance):
    res = {}
    if 'Tags' in instance:
        for tag in instance['Tags']:
            res[tag['Key']] = tag['Value']
    return res

def display(options, iid, instance):
    tags = parse_tags(instance)
    if 'Name' in tags:
        print("{} : ".format(tags['Name']), end='')
    print(iid)
    if options.pub_ip:
        print(" [-] Public IP: {}".format(instance['PublicIpAddress']))

    if options.priv_ip:
        print(" [-] Private IP: {}".format(instance['PrivateIpAddress']))

    if options.tags:
        if tags != {}:
            print(" [-] Tags")
            for k, v in tags.items():
                print("   * {}= {}".format(k, v))

    if options.state:
        if tags != {}:
            print(" [-] {}".format(instance['State']['Name']))

def get_names(options):
    names = []
    if options.name != None:
        names = options.name
    elif options.count != None and options.basename != None:
        names = ['{}{}'.format(options.basename, i)
                 for i in range(options.start, options.count)]
    else:
        return None
    return names

def get_ip(options, instances):
    names = get_names(options)
    if options.iid != None:
        res = {}
        for iid in options.iid:
            res[iid] = instances[iid]['PublicIpAddress']
        return res

    elif names:
        res = {}
        for name in names:
            for k, v in instances.items():
                tags = parse_tags(v)
                if 'Name' in parse_tags(v):
                    if tags['Name'] == name:
                        res[k] = instances[k]['PublicIpAddress']
        return res

    else:
        print("Need to specify iid or name!")
        exit(-1)

def display_scheduler(options, instances):
    for k, v in instances.items():
        tags = parse_tags(v)
        if 'Name' in tags:
            if tags['Name'] == 'scheduler':
                display(options, k, v)

def display_clients(options, instances):
    for k, v in instances.items():
        tags = parse_tags(v)
        if 'Name' in tags:
            if not tags['Name'].startswith('scheduler'):
                display(options, k, v)
        else:
            display(options, k, v)

def display_all(options, instances):
    for k, v in instances.items():
        display(options, k, v)

def connect(options, instances):
    ips = get_ip(options, instances)
    for ip in ips.values():
        cmd = ['ssh', '-i', KEYFILE,
               '-o', 'StrictHostKeyChecking no',
               'ubuntu@{}'.format(ip)]
        print(' '.join(cmd))
        subprocess.run(cmd)
        print("Done with {}!".format(ip))

def terminate(options, instances):
    iids = []
    names = get_names(options)
    if options.iid != None:
        iids = options.iid
    elif names != None:
        for k, v in instances.items():
            tags = parse_tags(v)
            for name in names:
                if 'Name' in tags:
                    if tags['Name'] == name:
                        iids.append(k)
    else:
        print("Need to specify iid or name!")
        exit(-1)

    for iid in iids:
        cmd = ['aws', 'ec2', 'terminate-instances',
               '--instance-ids', '{}'.format(iid),
               '--region', options.region]
        subprocess.run(cmd, stdout=subprocess.PIPE)
        print("Terminating {}".format(iid))

def copy(options, instances):
    ips = get_ip(options, instances)
    if options.path == None:
        print("Need to specify a path!")
        exit(-1)

    else:
        for ip in ips.values():
            cmd = ['scp', '-i', KEYFILE]
            if options.recursive:
                cmd.append('-r')
            if options.send:
                cmd += [options.path, 'ubuntu@{}:{}'.format(ip, Path(options.path).name)]
            else:
                cmd += ['ubuntu@{}:{}'.format(ip, options.path), '.']
            print(' '.join(cmd))
            subprocess.run(cmd)

def new(options, instances):
    names = get_names(options)
    if names == None:
        print("Need to specifiy a name or a basename + count!")
        exit(-1)
    for name in names:
        cmd = ['aws', 'ec2', 'run-instances',
                '--image-id', IMAGE_ID,
                '--instance-type', options.type,
                '--key-name', KEY,
                '--security-group-ids', SECURITY_ID,
                '--region', options.region,
                '--tag-specifications',
                'ResourceType=instance,Tags=[{}Key=Name,Value={}{}]'.format('{', name, '}')]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE)
        for i in json.loads(proc.stdout)['Instances']:
            print("Starting {}".format(i['InstanceId']))

def start(options, instances):
    if options.scheduler == None or options.port == None:
        print("You need to provide a scheduler!")
        exit(-1)

    k = RSAKey.from_private_key_file(Path(KEYFILE).expanduser())
    c = SSHClient()
    c.set_missing_host_key_policy(AutoAddPolicy())

    port = options.port
    scheduler_ip = options.scheduler

    for ip in get_ip(options, instances).values():
        tmux_cmd = "tmux -v new -d -s session './sklearn-benchmarks/model_code/client.py -p {} -o {} --loop'"
        cmds = [
            "cd sklearn-benchmarks && git pull",
            tmux_cmd.format(port, scheduler_ip)
        ]

        print("Connecting to {}".format(ip))
        c.connect(hostname=ip, username="ubuntu", pkey=k)

        for cmd in cmds:
            stdin, stdout, stderr = c.exec_command(cmd)
            print(str(stdout.read(), 'ascii'), str(stderr.read(), 'ascii'))

        c.close()

if __name__ == "__main__":
    options = make_parser().parse_args()
    instances = get_instances(options.region)

    if options.info_type == SCHEDULER:
        display_scheduler(options, instances)

    elif options.info_type == CLIENTS:
        display_clients(options, instances)

    elif options.info_type == ALL:
        display_all(options, instances)

    elif options.info_type == CONNECT:
        connect(options, instances)

    elif options.info_type == TERMINATE:
        terminate(options, instances)

    elif options.info_type == COPY:
        copy(options, instances)

    elif options.info_type == NEW:
        new(options, instances)

    elif options.info_type == START:
        start(options, instances)


# print("Need to specifiy a name or a basename + count!")
# exit(-1)
