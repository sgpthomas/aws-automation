#!/usr/bin/env python3

import argparse
import subprocess
import json
import os
from paramiko import RSAKey, SSHClient, AutoAddPolicy
from pathlib import Path
from datetime import datetime, timedelta
from time import sleep

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# IMAGE_ID = 'ami-003caac684d26c013'
# SECURITY_ID = 'sg-0986839b16b02894f'

# KEY = "tiger"
# KEYFILE = "~/.ssh/{}.pem".format(KEY)


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

def parse_tags(instance):
    res = {}
    if 'Tags' in instance:
        for tag in instance['Tags']:
            res[tag['Key']] = tag['Value']
    return res

def filter_instances(instances, options):
    valid_iids = []
    for iid in options.iid:
        valid_iids.append(iid)

    for name in options.nametag:
        for iid, v in instances.items():
            tags = parse_tags(v)
            if 'Name' in parse_tags(v):
                if tags['Name'] == name:
                    valid_iids.append(iid)

    if len(options.iid) > 0 or len(options.nametag) > 0:
        if options.inverse:
            return {iid: data for iid, data in instances.items() if not iid in valid_iids}
        else:
            return {iid: data for iid, data in instances.items() if iid in valid_iids}
    else:
        return instances

def select_dict(d, a, b):
    allowed = list(d.keys())[a:b]
    return {k: v for k, v in d.items() if k in allowed}

def iso_to_datetime(iso_str):
    date_time_split = iso_str.split("T")
    date, time = date_time_split[0], date_time_split[1]

    # date
    date_split = date.split('-')
    year, month, day = int(date_split[0]), int(date_split[1]), int(date_split[2])

    # time
    time = time[:-1]
    time_split = time.split(':')
    hour, minute, second = int(time_split[0]), int(time_split[1]), int(time_split[2])

    return datetime(year, month, day, hour=hour, minute=minute, second=second)

def h_info(options, instances, keyfile):
    for iid, instance in instances.items():
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

def h_connect(options, instances, keyfile):
    for iid, instance in instances.items():
        ip = instance['PublicIpAddress']
        cmd = ['ssh', '-i', keyfile,
               '-o', 'StrictHostKeyChecking no',
               'ubuntu@{}'.format(ip)]
        print(' '.join(cmd))
        subprocess.run(cmd)
        print("Done with {}!".format(ip))

def h_terminate(options, instances, keyfile):
    for iid, instance in instances.items():
        cmd = ['aws', 'ec2', 'terminate-instances',
               '--instance-ids', '{}'.format(iid),
               '--region', options.region]
        subprocess.run(cmd, stdout=subprocess.PIPE)
        print("Terminating {}".format(iid))

def get_cpu_data(iid, start_time, end_time):
    cmd = ['aws', 'cloudwatch', 'get-metric-statistics',
        '--metric-name', 'CPUUtilization',
        '--start-time', start_time.isoformat(timespec='minutes'),
        '--end-time', end_time.isoformat(timespec='minutes'),
        '--period', '300',
        '--namespace', 'AWS/EC2',
        '--statistics', 'Average',
        '--dimensions', 'Name=InstanceId,Value={}'.format(iid)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE)
    output = json.loads(proc.stdout)
    data = {}
    for point in sorted(output['Datapoints'], key=lambda o: o['Timestamp']):
        data[iso_to_datetime(point['Timestamp'])] = [float(point['Average'])]
    return data

def h_cpu(options, instances, keyfile):
    iids = list(instances.keys())
    now_time = datetime.utcnow()
    datas = {}
    print("[0/{}]".format(len(iids)), end="")
    for i, iid in enumerate(iids):
        print("\r[{}/{}] : {}".format(i+1, len(iids), iid), end='')
        path = Path(options.data_dir, "{}.pkl".format(iid))
        data = None
        if path.exists():
            data = pd.read_pickle(str(path))
            last_datapoint = data.index[-1].to_pydatetime()
            if now_time - last_datapoint > timedelta(minutes=10):
                new_data = get_cpu_data(iid, last_datapoint, now_time)
                df = pd.DataFrame(new_data).transpose()
                data = data.append(df).drop_duplicates()
                data.to_pickle(str(path))
        else:
            start_time = now_time - timedelta(hours=24)
            data = get_cpu_data(iid, start_time, now_time)
            data = pd.DataFrame(data).transpose()
            if (len(data) > 0):
                data.to_pickle(str(path))
        if (len(data) > 0):
            datas[iid] = data

    print()
    if options.graph:
        for iid, data in datas.items():
            index = int((options.delta * 60) / 5)
            plt.plot(data[-index+1:], linestyle='-', marker='o', label=iid)
        plt.grid()
        plt.ylim([0,100])
        plt.xticks(rotation=30)
        plt.legend()
        plt.show()
    else:
        to_kill = []
        for iid, data in datas.items():
            print("{} : {:.2f}".format(iid, data[0].mean()))
            if data[0].mean() < 55:
                to_kill.append(iid)
        if options.drop:
            newInstances = {iid: inst for iid, inst in instances.items() if iid in to_kill}
            print(list(newInstances.keys()))
            h_terminate(options, newInstances, keyfile)

choices = {
    "info": h_info,
    "connect": h_connect,
    "terminate": h_terminate,
    "cpu": h_cpu,
}

def make_parser():
    descr = "Tool to automate AWS things."
    parser = argparse.ArgumentParser(description=descr)

    parser.add_argument("info_type", action="store", choices=list(choices.keys()))
    parser.add_argument("--region", action="store", default="us-west-1")
    parser.add_argument("--key", action="store", default="tiger")
    parser.add_argument("--data-dir", action="store", default="data")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--graph", action="store_true")
    parser.add_argument("--drop", action="store_true")

    # filter options
    parser.add_argument("--iid", action="store", nargs='*')
    parser.add_argument("--nametag", action="store", nargs='*')
    parser.add_argument("-i", "--inverse", action="store_true")
    parser.add_argument("--select", action="store", default="")

    # display options
    parser.add_argument("--pub-ip", action="store_true")
    parser.add_argument("--priv-ip", action="store_true")
    parser.add_argument("--tags", action="store_true")
    parser.add_argument("--state", action="store_true")

    parser.add_argument("--delta", action="store", default=1, type=int)

    # other options
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

if __name__ == "__main__":
    options = make_parser().parse_args()
    keyfile = "~/.ssh/{}.pem".format(options.key)

    try:
        os.mkdir(options.data_dir)
    except OSError:
        pass

    if options.iid == None: options.iid = []
    if options.nametag == None: options.nametag = []

    try:
        while True:
            instances = get_instances(options.region)
            filtered = filter_instances(instances, options)

            if options.select != "":
                parts = options.select.split(":")
                lower, upper = int(parts[0]), int(parts[1])
                filtered = select_dict(filtered, lower, upper)

            choices[options.info_type](options, filtered, keyfile)
            if options.watch:
                sleep(45)
                print()
            else:
                break
    except KeyboardInterrupt:
        pass
