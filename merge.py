#!/usr/bin/env python3

import pandas as pd
import argparse
import glob

def make_parser():
    descr = "Merges all .pkl files into a single .pkl file."
    parser = argparse.ArgumentParser(description=descr)

    parser.add_argument('resultsdir', action="store")
    parser.add_argument('output_name', action="store")

    return parser

order = ['dataset',
         'classifier',
         'parameters',
         'avg_fit_time',
         'avg_score_time',
         'avg_test_accuracy',
         'avg_test_bal_accuracy',
         'avg_test_f1_macro',
         'avg_train_accuracy',
         'avg_train_bal_accuracy',
         'avg_train_f1_macro',
         'std_fit_time',
         'std_score_time',
         'std_test_accuracy',
         'std_test_bal_accuracy',
         'std_test_f1_macro',
         'std_train_accuracy',
         'std_train_bal_accuracy',
         'std_train_f1_macro']

def sortCSVString(string):
    if string == "": return ""
    tuplify = lambda s: tuple(s.split('='))
    newD = dict(sorted(map(tuplify, string.split(',')), key=lambda x: x[0]))
    res = []
    for k, v in newD.items():
        res.append('{}={}'.format(k, v))
    return ','.join(res)

def chunk(lst, size):
    acc = []
    count = 0
    for i, item in enumerate(lst):
        if len(acc) == size:
            yield count, acc
            count += 1
            acc = []
        acc.append(item)
    yield count, acc

def merge(resultsdir, tmpdir, chunksize=500):
    print("Reading {}".format(resultsdir), end='', flush=True)
    files = glob.glob("{}/*.pkl".format(resultsdir))
    acc = pd.DataFrame()
    print("\r                                        ", end='')
    for i, f_lst in chunk(files, chunksize):
        print("\r[{}/{}]".format(i, int(len(files)/chunksize)), end=' '*50)
        df = pd.DataFrame()
        new = []
        for f in f_lst:
            try:
                newDf = pd.read_pickle(f)
                # newDf = newDf[order]
                # newDf['parameters'] = sortCSVString(newDf['parameters'][0])
                new.append(newDf)
            except EOFError:
                pass
        df = pd.concat([df] + new)
        df.to_pickle("{}/int-{}.pkl".format(tmpdir, i))
    print("\r[Done]                                                         ")

def merge_all(resultsdir):
    files = glob.glob("{}/*.pkl".format(resultsdir))
    df = pd.DataFrame()
    for i, f in enumerate(files):
        try:
            new = pd.read_pickle(f)
            print("\r[{}/{}] : {} -> {}".format(i+1, len(files), f, new['dataset'].values[0]), end=" "*40)
            df = pd.concat([df, new])
        except EOFError:
            pass
            # print("Found empty file called {}!".format(f))
    return df.sort_values('dataset').reset_index(drop=True)

if __name__ == "__main__":
    parser = make_parser().parse_args()

    combined = merge_all(parser.resultsdir)
    combined.to_pickle(parser.output_name)
