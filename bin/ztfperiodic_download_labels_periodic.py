#!/usr/bin/env python

import os, sys
import glob
import optparse
import copy
import time
import h5py
from functools import reduce
import traceback
import pickle
import itertools

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
font = {'size'   : 22}
matplotlib.rc('font', **font)
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from matplotlib.colors import LogNorm
from matplotlib.colors import Normalize

import astropy
from astropy.table import Table, vstack
from astropy.coordinates import Angle
from astropy.io import ascii
from astropy import units as u
from astropy.coordinates import SkyCoord

from joblib import Parallel, delayed
from tqdm import tqdm

from ztfperiodic.utils import get_kowalski, get_featuresetnames
from ztfperiodic.periodicnetwork.light_curve import LightCurve, Periodogram
from ztfperiodic.periodsearch import find_periods

try:
    from penquins import Kowalski
except:
    print("penquins not installed... need to use matchfiles.")

from zvm import zvm

class ProgressParallel(Parallel):
    def __init__(self, use_tqdm=True, total=None, *args, **kwargs):
        self._use_tqdm = use_tqdm
        self._total = total
        super().__init__(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        with tqdm(disable=not self._use_tqdm, total=self._total) as self._pbar:
            return Parallel.__call__(self, *args, **kwargs)

    def print_progress(self):
        if self._total is None:
            self._pbar.total = self.n_dispatched_tasks
        self._pbar.n = self.n_completed_tasks
        self._pbar.refresh()


def parse_commandline():
    """
    Parse the options given on the command-line.
    """
    parser = optparse.OptionParser()
    #parser.add_option("--doUpload",  action="store_true", default=False)

    #parser.add_option("-o","--outputDir",default="/home/michael.coughlin/ZTF/output_features_20Fields/catalog/compare/bw/")
    parser.add_option("-o","--outputDir",default="/home/michael.coughlin/ZTF/labels_periodic")

    parser.add_option("-t","--tag",default="d12")

    parser.add_option("-u","--user")
    parser.add_option("-w","--pwd")

    parser.add_option("--zvm_user")
    parser.add_option("--zvm_pwd")

    parser.add_option("--doParallel",  action="store_true", default=False)
    parser.add_option("-n","--Ncore",default=8,type=int)

    parser.add_option("-N","--Nexamples",default=500,type=int)

    parser.add_option("--doPeriodSearch", action="store_true", default=False)
    parser.add_option("--doLongPeriod",  action="store_true", default=False)
    parser.add_option("--doRemoveTerrestrial",  action="store_true", default=False)

    parser.add_option("-a", "--algorithms", default="ECE_periodogram,ELS_periodogram,EAOV_periodogram")

    parser.add_option("--doGPU", action="store_true", default=False)
    parser.add_option("--doCPU", action="store_true", default=False)

    opts, args = parser.parse_args()

    return opts

def database_query(kow, qu, nquery = 5):
    r = {}
    cnt = 0
    while cnt < nquery:
        r = kow.query(query=qu)
        if "result_data" in r:
            break
        time.sleep(5)
        cnt = cnt + 1
    return r

def get_program_ids(tag):

    if tag == 'vnv_d1':
        zvm_program_ids = [21, 24, 36]
    elif tag == 'vnv_d2':
        zvm_program_ids = [21, 22, 23, 24, 25, 26, 27, 28]
    elif tag == 'vnv_d3':
        zvm_program_ids = [21, 22, 23, 24, 25, 26, 27, 28, 36]
    elif tag == 'vnv_d5':
        zvm_program_ids = [21, 22, 23, 24, 25, 26, 27, 28, 36, 37, 38, 39]
    elif tag == 'vnv_d6':
        zvm_program_ids = [21, 22, 23, 24, 25, 26, 27, 28, 36, 40, 41, 42]
    elif (tag == 'vnv_d7') or (tag == 'vnv_d8'):
        zvm_program_ids = [
            3, 4, 6, 9, 21, 22, 23, 24, 25, 26, 27, 28, 36, 40, 41, 42,
            44, 45, 46, 47, 48, 49
        ]
    elif tag == 'd9':
        zvm_program_ids = [
            3, 4, 6, 9, 21, 22, 23, 24, 25, 26, 27, 28, 36, 40, 41, 42,
            43, 44, 45, 46, 47, 48, 49, 51, 53, 58, 60, 61
        ]
    elif tag == 'd10':
        zvm_program_ids = [
            3, 4, 6, 9, 21, 22, 23, 24, 25, 26, 27, 28, 36, 40, 41, 42,
            43, 44, 45, 46, 47, 48, 49, 51, 53, 58, 60, 61, 62
        ]
    elif tag == 'd11':
        zvm_program_ids = [
            3, 4, 5, 6, 9,
            11, 12, 13, 14, 15, 16, 17, 18, 19,
            20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
            30, 31, 32, 33, 34, 36, 37,
            40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
            51, 53, 54, 56, 58,
            60, 61, 62, 63, 64, 65, 66, 67, 68, 69,
            70, 71, 72, 73, 74, 75, 76, 77, 78, 79,
            81, 82, 89,
            91
        ]
    elif tag == 'd12':
        zvm_program_ids = [
            3, 4, 5, 6, 9,
            11, 12, 13, 14, 15, 16, 17, 18, 19,
            20, 21, 22, 23, 24, 25, 26, 27, 28, 29,
            30, 31, 32, 33, 34, 36, 37,
            40, 41, 42, 43, 44, 45, 46, 47, 48, 49,
            51, 53, 54, 56, 58,
            60, 61, 62, 63, 64, 65, 66, 67, 68, 69,
            70, 71, 72, 73, 74, 75, 76, 77, 78, 79,
            81, 82, 89,
            91,
            94, 95, 96, 97, 98, 101, 102
        ]

    return zvm_program_ids

def is_ingested(ztf_id):
    # todo: select sources with a threshold on n_obs
    q = {'query_type': 'count_documents',
         'query': {
             'catalog': catalogs['features'],
             'filter': {'_id': int(ztf_id)}
         }}
    r = database_query(kow,q)
    if not bool(r):
        return {}
    r = r.get('data')

    q = {'query_type': 'find',
         'query': {
             'catalog': catalogs['sources'],
             'filter': {'_id': int(ztf_id)},
             'projection': {'_id':0, 'ra': 1, 'dec': 1}
         }}
    radec = database_query(kow,q)
    if radec is None:
        return {}    
    radec = radec.get('data')

    if len(radec) > 0:
        return {'ztf_id': int(ztf_id),
                'ingested': r,
                'ra': radec[0]['ra'],
                'dec': radec[0]['dec']}
    else:
        return {}

def get_labels(zvm_id):
    q = {'query_type': 'find',
         'query': {
             'catalog': 'sources',
             'filter': {
                 '_id': zvm_id
             },
             'projection': {
                 'labels': 1
             }
         }
        }

    r = zvmarshal.query(query=q).get('result').get('result_data').get('query_result')
    #print(r)
    return {'zvm_id': zvm_id, 'labels': r[0]['labels']}

def get_features(ztf_id):
    # fixme: cross_matches are omitted for now
    q = {'query_type': 'find',
         'query': {
             'catalog': catalogs['features'],
             'filter': {'_id': int(ztf_id)},
             'projection': {'coordinates': 0, 'cross_matches': 0}
         }}

    r = database_query(kow,q)
    if not bool(r):
        return {}
    r = r.get('data')[0]

    return r

def get_lightcurves(ztf_id):

    labels = df_labels.loc[df_labels["ztf_id"] == ztf_id]
    scores = np.array(labels[keys])[0]
    if np.sum(scores) == 0:
        return []
    if np.sum(scores) > 1:
        print('%d has multiple labels... returning.' % ztf_id)
        return []
    idxs = np.where(scores == 1)[0]
    if len(idxs) == 0:
        return []
    idx = idxs[0]
    label = target_labels[keys[idx]]

    feat = get_features(ztf_id)
    metadata = []
    for name in featuresetnames:
        if feat[name] is None:
            metadata.append(0)
        else:
            metadata.append(feat[name])
    metadata = np.array(metadata)
    lightcurves_all = get_kowalski(feat['ra'], feat['dec'], kow,
                                   radius=1.0,
                                   min_epochs=50)
    lcs = []
    for objid in lightcurves_all.keys():
        lc = lightcurves_all[objid]
        lcurve = LightCurve(lc["hjd"],
                            lc["mag"],
                            lc["magerr"],
                            survey="ZTF",
                            p=feat["period"],
                            best_period=feat["period"],
                            best_score=feat["significance"],
                            name=ztf_id,
                            label=label,
                            metadata=metadata)
        lcs.append(lcurve)
    return lcs

# Parse command line
opts = parse_commandline()

catalogs = {'features': 'ZTF_source_features_20191101',
            'sources': 'ZTF_sources_20200401'}

outputDir = opts.outputDir
algorithms = opts.algorithms.split(",")

plotDir = os.path.join(outputDir,'plots')
if not os.path.isdir(plotDir):
    os.makedirs(plotDir)

kow = []
nquery = 10
cnt = 0
while cnt < nquery:
    try:
        kow = Kowalski(username=opts.user, password=opts.pwd)
        break
    except:
        time.sleep(5)
    cnt = cnt + 1
if cnt == nquery:
    raise Exception('Kowalski connection failed...')

nquery = 10
cnt = 0
while cnt < nquery:
    try:
        zvmarshal = zvm(username=str(opts.zvm_user),
                        password=str(opts.zvm_pwd),
                        verbose=True, host="rico.caltech.edu")
        break
    except:
        time.sleep(5)
    cnt = cnt + 1
if cnt == nquery:
    raise Exception('zvm connection failed...')

dfmfile = os.path.join(outputDir, 'df_m.hdf5')
if not os.path.isfile(dfmfile):

    r = zvmarshal.api(endpoint='programs', method='get', data={'format': 'json'})
    df_p = pd.DataFrame.from_records(r)
    
    for zvm_program_id in df_p['_id']:
        # number of objects in dataset:
        q = {'query_type': 'count_documents',
             'query': {
                 'catalog': 'sources',
                 'filter': {
                     'zvm_program_id': zvm_program_id
                 }
             }
            }
        r = zvmarshal.query(query=q).get('result').get('result_data').get('query_result')
        w = df_p['_id'] == zvm_program_id
        df_p.loc[w, 'n'] = r
    
        # number of labeled objects in dataset:
        q = {'query_type': 'count_documents',
             'query': {
                 'catalog': 'sources',
                 'filter': {
                     'zvm_program_id': zvm_program_id,
                     'labels.0': {'$exists': True}
                 }
             }
            }
        r = zvmarshal.query(query=q).get('result').get('result_data').get('query_result')
        w = df_p['_id'] == zvm_program_id
        df_p.loc[w, 'n_l'] = r
    
    zvm_program_ids = get_program_ids(opts.tag)
    
    q = {'query_type': 'find',
         'query': {
             'catalog': 'sources',
             'filter': {
                 'zvm_program_id': {'$in': zvm_program_ids},
                 'labels.0': {'$exists': True}
             },
             'projection': {
                 'lc.id': 1
             }
         }
        }
    r = zvmarshal.query(query=q).get('result').get('result_data').get('query_result')
    
    ids = []
    for s in r:
        for i in s['lc']:
            ids.append({'ztf_id': i['id'], 'zvm_id': s['_id']})
    df_i = pd.DataFrame.from_records(ids)
    #df_i = df_i[:10000]
    
    print('Checking objects for features...')
    if opts.doParallel:
        r = ProgressParallel(n_jobs=opts.Ncore,use_tqdm=True,total=len(df_i['ztf_id'].unique()))(delayed(is_ingested)(ztf_id) for ztf_id in df_i['ztf_id'].unique())
    else:
        r = []
        for ii, ztf_id in enumerate(df_i['ztf_id'].unique()):
            if np.mod(ii, 100) == 0:
                print('Checked object %d/%d' % (ii+1, len(df_i['ztf_id'].unique())))
            r.append(is_ingested(ztf_id))
    
    df_r = pd.DataFrame.from_records(r)    
    df_m = pd.merge(df_r, df_i, on='ztf_id')
    df_m.to_hdf(dfmfile, key='df_merged', mode='w')
else:
    df_m = pd.read_hdf(dfmfile, key='df_merged')

zvm_ids = set(df_m.loc[df_m['ingested'] == 1, 'zvm_id'].values)

dflabelsfile = os.path.join(outputDir, 'df_zvm_labels.hdf5')
if not os.path.isfile(dflabelsfile):
    print('Checking ZVM for labels...')
    if opts.doParallel:
        l = ProgressParallel(n_jobs=opts.Ncore,use_tqdm=True,total=len(zvm_ids))(delayed(get_labels)(zvm_id) for zvm_id in zvm_ids)
    else:   
        l = []
        for ii, zvm_id in enumerate(zvm_ids):
            if np.mod(ii, 100) == 0:
                print('Getting labels for object %d/%d' % (ii+1, len(zvm_ids)))
            l.append(get_labels(zvm_id))

    df_zvm_labels = pd.DataFrame(l)
    df_zvm_labels.to_hdf(dflabelsfile, key='df_merged', mode='w')
else:
    df_zvm_labels = pd.read_hdf(dflabelsfile, key='df_merged')

labels_source = []
labels = set()

for tu in df_zvm_labels.itertuples():
    labs = tu.labels
    # multiple users may have classified the same object
    # compute the mean values for each label
    _l = {ll['label']: {'v': 0, 'n': 0} for ll in labs}
    for ll in labs:
        _l[ll['label']]['v'] += ll['value']
        _l[ll['label']]['n'] += 1

        labels.add((ll['type'], ll['label']))
    for ll, vv in _l.items():
        _l[ll] = vv['v'] / vv['n']

    labels_source.append(dict(**{'zvm_id': tu.zvm_id}, **_l))

df_labels_source = pd.DataFrame.from_records(labels_source).fillna(0)
df_labels = pd.merge(df_m, df_labels_source,
                     on='zvm_id').drop_duplicates('ztf_id').reset_index(drop=True)

df_label_stats = pd.DataFrame(labels,
                              columns=['type',
                                       'label']).sort_values(by=['type',
                                                                 'label']).reset_index(drop=True)
df_label_stats['number'] = 0

for dl in df_labels.columns.values[5:]:
    ww = df_label_stats['label'] == dl
    df_label_stats.loc[ww, 'number'] = ((df_labels[dl] > 0.0) & (df_labels['ingested'] == 1)).sum()

ztf_ids = sorted(df_m.loc[df_m['ingested'] == 1, 'ztf_id'].unique())

target_labels = {'Cepheid': 'ceph',
                 'Delta Scu': 'dscu',
                 'EA': 'ea',
                 'EB': 'eb',
                 'EW': 'ew',
                 #'Mira': 'mira',
                 'RR Lyrae': 'rrlyr',
                 'RS CVn': 'rscvn',
                 'YSO': 'yso'
                }
keys = [x for x in target_labels.keys()] 

ids = np.array(df_labels['ztf_id'])
id_intersection, idx1, tmp = np.intersect1d(ids, ztf_ids, return_indices=True)

ztf_ids = []
for label in target_labels.keys():
    scores = np.array(df_labels[label])
    idxs = np.where(scores == 1)[0]
    idx2 = np.intersect1d(idxs, idx1)
    idx2 = np.random.choice(idx2, size=opts.Nexamples, replace=False)

    ztf_ids.append(ids[idx2])
ztf_ids = list(itertools.chain(*ztf_ids))

featuresetname = 'nonztf'
featuresetnames = get_featuresetnames(featuresetname)

lightcurvesfile = os.path.join(outputDir, 'lightcurves.pkl')
if not os.path.isfile(lightcurvesfile):
    print('Pulling lightcurves...')
    if opts.doParallel:
        lightcurves = ProgressParallel(n_jobs=opts.Ncore,use_tqdm=True,total=len(ztf_ids))(delayed(get_lightcurves)(ztf_id) for ztf_id in ztf_ids)
    else:
        lightcurves = []
        for ii, ztf_id in enumerate(ztf_ids):
            if np.mod(ii, 100) == 0:
                print('Getting lightcurves for object %d/%d' % (ii+1, len(ztf_ids)))
            lightcurves.append(get_lightcurves(ztf_id))
    lightcurves = list(itertools.chain(*lightcurves))

    with open(lightcurvesfile, 'wb') as handle:
        pickle.dump(lightcurves, handle,
                    protocol=pickle.HIGHEST_PROTOCOL)

with open(lightcurvesfile, 'rb') as handle:
    lightcurves = pickle.load(handle)

if opts.doPeriodSearch:

    periodogramsfile = os.path.join(outputDir, 'periodograms.pkl')

    periodogramDir = os.path.join(outputDir,'periodograms')
    if not os.path.isdir(periodogramDir):
        os.makedirs(periodogramDir)

    if not (opts.doCPU or opts.doGPU):
        print("--doCPU or --doGPU required")
        exit(0)

    for lc in lightcurves:
        periodogramsfile = os.path.join(periodogramDir, '%s.pkl' % lc.name)
        if os.path.isfile(periodogramsfile): continue
       
        hjd, mag, magerr = lc.times, lc.measurements, lc.errors
        lightcurve = [np.array(hjd), np.array(mag), np.array(magerr)]

        baseline = max(hjd)-min(hjd)
        if baseline<10:
            if opts.doLongPeriod:
                fmin, fmax = 18, 48
            else:
                fmin, fmax = 18, 1440
        else:
            if opts.doLongPeriod:
                fmin, fmax = 2/baseline, 48
            else:
                fmin, fmax = 2/baseline, 480

        samples_per_peak = 3

        dfreq = 1./(samples_per_peak * baseline)
        nf = int(np.ceil((fmax - fmin) / dfreq))
        freqs = fmin + dfreq * np.arange(nf)

        if opts.doRemoveTerrestrial:
            freqs_to_remove = [[3e-2,4e-2], [47.99,48.01], [46.99,47.01], [45.99,46.01], [3.95,4.05], [2.95,3.05], [1.95,2.05], [0.95,1.05], [0.48, 0.52]]
        else:
            freqs_to_remove = None

        #print('Cataloging lightcurves...')
        data = np.zeros((len(algorithms),len(freqs)))
        for ii, algorithm in enumerate(algorithms):
            periods_best, significances, pdots = find_periods(algorithm, [lightcurve], freqs, doGPU=opts.doGPU, doCPU=opts.doCPU, doRemoveTerrestrial=opts.doRemoveTerrestrial, freqs_to_remove=freqs_to_remove)
            data[ii,:] = periods_best[0]["data"].T
        
        pg = Periodogram(1.0/freqs, data,
                         survey=lc.survey, name=lc.name,
                         times=lc.times,
                         measurements=lc.measurements,
                         errors=lc.errors,
                         label=lc.label,
                         p=lc.p,
                         metadata=lc.metadata)

        with open(periodogramsfile, 'wb') as handle:
            pickle.dump(pg, handle,
                        protocol=pickle.HIGHEST_PROTOCOL)

    #with open(periodogramsfile, 'rb') as handle:
    #    pgs = pickle.load(handle)
    #print(pgs[0])
