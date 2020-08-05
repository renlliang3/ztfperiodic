#!/usr/bin/env python

import os, sys
import glob
import optparse
import copy
import time
import h5py

import numpy as np

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

from astroquery.simbad import Simbad
Simbad.ROW_LIMIT = -1
Simbad.TIMEOUT = 300000

from ztfperiodic.utils import convert_to_hex

def parse_commandline():
    """
    Parse the options given on the command-line.
    """
    parser = optparse.OptionParser()
    parser.add_option("--doPlots",  action="store_true", default=False)
    parser.add_option("--doFermi",  action="store_true", default=False)
    parser.add_option("--doSimbad",  action="store_true", default=False)
    parser.add_option("--doCrossMatch",  action="store_true", default=False)
    parser.add_option("--doVariability",  action="store_true", default=False)

    parser.add_option("--doField",  action="store_true", default=False)
    parser.add_option("-f","--field",default=853,type=int)

    parser.add_option("-o","--outputDir",default="/home/michael.coughlin/ZTF/output_quadrants/catalog/compare")
    parser.add_option("--catalog1",default="/home/michael.coughlin/ZTF/output_quadrants/catalog/LS")
    parser.add_option("--catalog2",default="/home/michael.coughlin/ZTF/output_quadrants/catalog/CE")
   
    parser.add_option("--catalog_file",default="../catalogs/CRTS.dat")    

    parser.add_option("--sig1",default=1e6,type=float)
    parser.add_option("--sig2",default=7.0,type=float)    

    parser.add_option("--crossmatch_distance",default=1.0,type=float)

    opts, args = parser.parse_args()

    return opts

def read_catalog(catalog_file):

    amaj, amin, phi = None, None, None
    default_err, default_mag = 5.0, np.nan

    if ".dat" in catalog_file:
        lines = [line.rstrip('\n') for line in open(catalog_file)]
        names, ras, decs, errs = [], [], [], []
        periods, classifications, mags = [], [], []
        if ("fermi" in catalog_file):
            amaj, amin, phi = [], [], []
        for line in lines:
            lineSplit = list(filter(None,line.split(" ")))
            if ("blue" in catalog_file) or ("uvex" in catalog_file) or ("xraybinary" in catalog_file):
                ra_hex, dec_hex = convert_to_hex(float(lineSplit[0])*24/360.0,delimiter=''), convert_to_hex(float(lineSplit[1]),delimiter='')
                if dec_hex[0] == "-":
                    objname = "ZTFJ%s%s"%(ra_hex[:4],dec_hex[:5])
                else:
                    objname = "ZTFJ%s%s"%(ra_hex[:4],dec_hex[:4])
                names.append(objname)
                ras.append(float(lineSplit[0]))
                decs.append(float(lineSplit[1]))
            elif ("CRTS" in catalog_file):
                names.append(lineSplit[0])
                ras.append(float(lineSplit[1]))
                decs.append(float(lineSplit[2]))
                errs.append(default_err)
                periods.append(float(lineSplit[3]))
                classifications.append(lineSplit[4])
                mags.append(default_mag)
            elif ("vlss" in catalog_file):
                names.append(lineSplit[0])
                ras.append(float(lineSplit[1]))
                decs.append(float(lineSplit[2]))
                err = np.sqrt(float(lineSplit[3])**2 + float(lineSplit[4])**2)*3600.0
                errs.append(err)
            elif ("fermi" in catalog_file):
                names.append(lineSplit[0])
                ras.append(float(lineSplit[1]))
                decs.append(float(lineSplit[2]))
                err = np.sqrt(float(lineSplit[3])**2 + float(lineSplit[4])**2)*3600.0
                errs.append(err)
                amaj.append(float(lineSplit[3]))
                amin.append(float(lineSplit[4]))
                phi.append(float(lineSplit[5]))
            elif ("swift" in catalog_file) or ("xmm" in catalog_file):
                names.append(lineSplit[0])
                ras.append(float(lineSplit[1]))
                decs.append(float(lineSplit[2]))
                err = float(lineSplit[3])
                errs.append(err)
            else:
                names.append(lineSplit[0])
                ras.append(float(lineSplit[1]))
                decs.append(float(lineSplit[2]))
                errs.append(default_err)
        names = np.array(names)
        ras, decs, errs = np.array(ras), np.array(decs), np.array(errs)
        if ("fermi" in catalog_file):
            amaj, amin, phi = np.array(amaj), np.array(amin), np.array(phi)
    elif ".hdf5" in catalog_file:
        with h5py.File(catalog_file, 'r') as f:
            ras, decs = f['ra'][:], f['dec'][:]
        catalog_file_mag = catalog_file.replace(".hdf5",
                                                "_mag.hdf5")
        if os.path.isfile(catalog_file_mag):
            with h5py.File(catalog_file_mag, 'r') as f:
                mags = f['mag'][:]

        errs = default_err*np.ones(ras.shape)
        periods = np.zeros(ras.shape)
        classifications = np.zeros(ras.shape)

        names = []
        for ra, dec in zip(ras, decs):
            ra_hex, dec_hex = convert_to_hex(ra*24/360.0,delimiter=''), convert_to_hex(dec,delimiter='')
            if dec_hex[0] == "-":
                objname = "ZTFJ%s%s"%(ra_hex[:4],dec_hex[:5])
            else:
                objname = "ZTFJ%s%s"%(ra_hex[:4],dec_hex[:4])
            names.append(objname)
        names = np.array(names)

    columns = ["name", "ra", "dec", "period", "classification",
               "mag"]
    tab = Table([names, ras, decs, periods, classifications,
                 mags],
                names=columns)

    return tab

def load_catalog(catalog,doFermi=False,doSimbad=False,
                         doField=False,field=-1):

    customSimbad=Simbad() 
    customSimbad.add_votable_fields("otype(V)")
    customSimbad.add_votable_fields("otype(3)")
    customSimbad.add_votable_fields("otype(N)")
    customSimbad.add_votable_fields("otype(S)")

    if doFermi:
        filenames = sorted(glob.glob(os.path.join(catalog,"*/*.dat")))[::-1] + \
                    sorted(glob.glob(os.path.join(catalog,"*/*.h5")))[::-1]
    elif doField:
        filenames = sorted(glob.glob(os.path.join(catalog,"%d_*.dat" % field)))[::-1] + \
                    sorted(glob.glob(os.path.join(catalog,"%d_*.h5" % field)))[::-1]
    else:
        filenames = sorted(glob.glob(os.path.join(catalog,"*.dat")))[::-1] + \
                    sorted(glob.glob(os.path.join(catalog,"*.h5")))[::-1]
                     
    #filenames = filenames[:100]
    names = ["name", "objid", "ra", "dec", "period", "sig", "pdot", "filt",
             "stats0", "stats1", "stats2", "stats3", "stats4",
             "stats5", "stats6", "stats7", "stats8", "stats9",
             "stats10", "stats11", "stats12", "stats13", "stats14",
             "stats15", "stats16", "stats17", "stats18", "stats19",
             "stats20", "stats21", "stats22", "stats23", "stats24",
             "stats25", "stats26", "stats27", "stats28", "stats29",
             "stats30", "stats31", "stats32", "stats33", "stats34",
             "stats35"]

    h5names = ["objid", "ra", "dec", "period", "sig", "pdot",
               "stats0", "stats1", "stats2", "stats3", "stats4",
               "stats5", "stats6", "stats7", "stats8", "stats9",
               "stats10", "stats11", "stats12", "stats13", "stats14",
               "stats15", "stats16", "stats17", "stats18", "stats19",
               "stats20", "stats21", "stats22", "stats23", "stats24",
               "stats25", "stats26", "stats27", "stats28", "stats29",
               "stats30", "stats31", "stats32", "stats33", "stats34",
               "stats35"]

    cnt = 0
    #filenames = filenames[:500]
    for ii, filename in enumerate(filenames):
        if np.mod(ii,100) == 0:
            print('Loading file %d/%d' % (ii, len(filenames)))

        filenameSplit = filename.split("/")
        catnum = filenameSplit[-1].replace(".dat","").replace(".h5","").split("_")[-1]

        if "h5" in filename:
            try:
                with h5py.File(filename, 'r') as f:
                    name = f['names'].value
                    filters = f['filters'].value
                    stats = f['stats'].value 
            except:
                continue
            data_tmp = Table(rows=stats, names=h5names)
            data_tmp['name'] = name
            data_tmp['filt'] = filters 
        else:
            data_tmp = ascii.read(filename,names=names)
        if len(data_tmp) == 0: continue

        data_tmp['name'] = data_tmp['name'].astype(str)
        data_tmp['filt'] = data_tmp['filt'].astype(str)
        data_tmp['catnum'] = int(catnum) * np.ones(data_tmp["ra"].shape)

        coord = SkyCoord(data_tmp["ra"], data_tmp["dec"], unit=u.degree)
        simbad = ["N/A"] * len(coord)
        if doSimbad:
            print('Querying simbad: %d/%d' %(ii,len(filenames)))
            doQuery = True
            result_table = None
            nquery = 1
            while doQuery and (not ii==1078):
                try:
                    result_table = customSimbad.query_region(coord,
                                                             radius=2*u.arcsecond)
                    doQuery = False
                    nquery = nquery + 1
                except:
                    nquery = nquery + 1
                    time.sleep(10)
                    continue
                if nquery >= 3:
                    break

            if not result_table is None:
                ra = result_table['RA'].filled().tolist()
                dec = result_table['DEC'].filled().tolist()
    
                ra  = Angle(ra, unit=u.hour)
                dec = Angle(dec, unit=u.deg)
    
                coords2 = SkyCoord(ra=ra,
                                   dec=dec, frame='icrs')
                idx,sep,_ = coords2.match_to_catalog_sky(coord)
                for jj, ii in enumerate(idx):
                    simbad[ii] = result_table[jj]["OTYPE_S"]
        data_tmp['simbad'] = simbad
        data_tmp['simbad'] = data_tmp['simbad'].astype(str)

        if cnt == 0:
            data = copy.copy(data_tmp)
        else:
            data = vstack([data,data_tmp])
        cnt = cnt + 1

    sig = data["sig"]
    idx = np.arange(len(sig))/len(sig)
    sigsort = idx[np.argsort(sig)]
    data["sigsort"] = sigsort

    return data

# Parse command line
opts = parse_commandline()

catalog1 = opts.catalog1
catalog2 = opts.catalog2
outputDir = opts.outputDir

if opts.doField:
    outputDir = os.path.join(outputDir,str(opts.field))

if not os.path.isdir(outputDir):
    os.makedirs(outputDir)

name1, name2 = list(filter(None,catalog1.split("/")))[-1], list(filter(None,catalog2.split("/")))[-1]
if opts.doCrossMatch:
    name2 = list(filter(None,opts.catalog_file.split("/")))[-1].replace(".dat","").replace(".hdf5","")

cat1file = os.path.join(outputDir,'catalog_%s.fits' % name1)
cat2file = os.path.join(outputDir,'catalog_%s.fits' % name2)

if not os.path.isfile(cat1file):
    cat1 = load_catalog(catalog1,doFermi=opts.doFermi,doSimbad=opts.doSimbad,
                                 doField=opts.doField,field=opts.field)
    cat1.write(cat1file, format='fits')
else:
    cat1 = Table.read(cat1file, format='fits')
idx1 = np.where(cat1["sig"] >= opts.sig1)[0]
print('Keeping %.5f %% of objects in catalog 1' % (100*len(idx1)/len(cat1)))
catalog1 = SkyCoord(ra=cat1["ra"]*u.degree, dec=cat1["dec"]*u.degree, frame='icrs')

if opts.doCrossMatch:
    if not os.path.isfile(cat2file):
        cat2 = read_catalog(opts.catalog_file)
        cat2.write(cat2file, format='fits')
    else:
        cat2 = Table.read(cat2file, format='fits')
else:
    if not os.path.isfile(cat2file):
        cat2 = load_catalog(catalog2,doFermi=opts.doFermi,
                            doSimbad=opts.doSimbad,
                            doField=opts.doField,field=opts.field)
        cat2.write(cat2file, format='fits')
    else:
        cat2 = Table.read(cat2file, format='fits')

    idx2 = np.where(cat2["sig"] >= opts.sig2)[0]
    print('Keeping %.5f %% of objects in catalog 2' % (100*len(idx2)/len(cat2)))

catalog2 = SkyCoord(ra=cat2["ra"]*u.degree, dec=cat2["dec"]*u.degree, frame='icrs')
idx,sep,_ = catalog1.match_to_catalog_sky(catalog2)

xs, ys, zs = [], [], []

filename = os.path.join(outputDir,'catalog.dat')
fid = open(filename,'w')
for i,ii,s in zip(np.arange(len(sep)),idx,sep):
    if s.arcsec > opts.crossmatch_distance: continue
  
    catnum = cat1["catnum"][i]
    objid = cat1["objid"][i]
    ra1, dec1 = cat1["ra"][i], cat1["dec"][i]
    ra2, dec2 = cat2["ra"][ii], cat2["dec"][ii]
    radiff = (ra1 - ra2)*3600.0
    decdiff = (dec1 - dec2)*3600.0

    if opts.doCrossMatch:
        sig1, sigsort1 = cat1["sig"][i], cat1["sigsort"][i]
        if opts.doVariability:
            sig1 = cat1["stats9"][i]
        sig2, sigsort2 = np.inf, np.inf
        classification = cat2["classification"][ii]
        magnitude = cat2["mag"][ii]
    else:
        sig1, sig2 = cat1["sig"][i], cat2["sig"][ii]
        sigsort1, sigsort2 = cat1["sigsort"][i], cat2["sigsort"][ii]
    period1, period2 = cat1["period"][i],cat2["period"][ii]

    if sig1 < opts.sig1: continue
    if sig2 < opts.sig2: continue

    xs.append(1.0/period1)
    ys.append(1.0/period2)
    if opts.doCrossMatch:
        ratio = 1.0
    else:
        ratio = np.min([sigsort1/sigsort2,sigsort2/sigsort1])
    zs.append(ratio)

    if opts.doCrossMatch:
        fid.write('%d %d %.5f %.5f %.10f %.10f %.5e %.5f %.5f %.5f %.5f %s\n' % (
                                                             catnum, objid,
                                                             ra1, dec1,
                                                             period1, period2,
                                                             sig1,
                                                             magnitude,
                                                             s.arcsec,
                                                             radiff,
                                                             decdiff,
                                                             classification))
    else:
        fid.write('%d %d %.5f %.5f %.10f %.10f %.5e %.5e\n' % (catnum, objid,
                                                               ra1, dec1,
                                                               period1, period2,
                                                               sig1, sig2))
fid.close() 

if opts.doCrossMatch:
    data_out = np.genfromtxt(filename)
else:
    data_out = np.loadtxt(filename)

if opts.doPlots:

    if opts.doCrossMatch:
        pdffile = os.path.join(outputDir,'periods.pdf')
        cmap = cm.autumn

        fig = plt.figure(figsize=(10,10))
        ax=fig.add_subplot(1,1,1)
        sc = plt.scatter(data_out[:,4],data_out[:,5],c=data_out[:,6],vmin=0.0,vmax=100.0,cmap=cmap,s=20,alpha=0.5)
        vals = np.linspace(np.min(data_out[:,4]), np.max(data_out[:,4]), 100)
        plt.plot(vals, vals, 'k--')
        ax.set_xscale('log')
        ax.set_yscale('log')
        cbar = plt.colorbar(sc)
        cbar.set_label('Significance')
        plt.xlabel('%s Frequency [1/days]' % name1)
        plt.ylabel('%s Frequency [1/days]' % name2)
        fig.savefig(pdffile)
        plt.close()

        pdffile = os.path.join(outputDir,'radec.pdf')
        fig = plt.figure(figsize=(10,10))
        ax=fig.add_subplot(1,1,1)
        idx = np.where(data_out[:,6]>=0.5)[0]
        hist2 = plt.scatter(data_out[idx,9], data_out[idx,10],
                            c=data_out[idx,6], s=20,
                            alpha = 0.2)
        ii = np.linspace(0,2*np.pi,100)
        radius = 10.0
        plt.plot(radius*np.cos(ii), radius*np.sin(ii), 'k--')
        radius = 13.0
        plt.plot(radius*np.cos(ii), radius*np.sin(ii), 'g--')
        height, width = 60.0, 4.0
        plt.plot([-height/2.0,height/2.0],[-width/2.0,-width/2.0], 'g--')
        plt.plot([height/2.0,height/2.0],[-width/2.0,width/2.0], 'g--')
        plt.plot([height/2.0,-height/2.0],[width/2.0,width/2.0], 'g--')
        plt.plot([-height/2.0,-height/2.0],[width/2.0,-width/2.0], 'g--')
        plt.xlabel('RA [arcsec]')
        plt.ylabel('Declination [arcsec]')
        fig.savefig(pdffile)
        plt.close()

        pdffile = os.path.join(outputDir,'magnitude.pdf')
        fig = plt.figure(figsize=(10,10))
        ax=fig.add_subplot(1,1,1)
        hist2 = plt.hist2d(data_out[:,6], data_out[:,7], bins=100,
                           zorder=0,norm=LogNorm())
        plt.xlabel('IQR')
        plt.ylabel('Magnitude')
        fig.savefig(pdffile)
        plt.close()

        pdffile = os.path.join(outputDir,'distance.pdf')
        fig = plt.figure(figsize=(10,10))
        ax=fig.add_subplot(1,1,1)
        hist2 = plt.hist2d(data_out[:,6], data_out[:,8], bins=100,
                           zorder=0,norm=LogNorm())
        plt.xlabel('IQR')
        plt.ylabel('Distance [arcsec]')
        fig.savefig(pdffile)
        plt.close()

    else:
        pdffile = os.path.join(outputDir,'periods.pdf')
        cmap = cm.autumn
    
        fig = plt.figure(figsize=(10,10))
        ax=fig.add_subplot(1,1,1)
        sc = plt.scatter(xs,ys,c=zs,vmin=0.0,vmax=1.0,cmap=cmap,s=20,alpha=0.5)
        vals = np.linspace(np.min(xs), np.max(xs), 100)
        plt.plot(vals, vals, 'k--')
        ax.set_xscale('log')
        ax.set_yscale('log')
        cbar = plt.colorbar(sc)
        cbar.set_label('min(%s/%s,%s/%s) significance' % (name1, name2, name2, name1))
        plt.xlabel('%s Frequency [1/days]' % name1)
        plt.ylabel('%s Frequency [1/days]' % name2)
        fig.savefig(pdffile)
        plt.close()
   
        pdffile = os.path.join(outputDir,'periods.pdf')
        cmap = cm.autumn

        plt.xlabel('%s Frequency [1/days]' % name1)
        plt.ylabel('%s Frequency [1/days]' % name2)
        fig.savefig(pdffile)
        plt.close() 

        xedges = np.logspace(np.log10(0.02),3.0,100)
        #yedges = np.linspace(4.0,40.0,50)
        yedges = np.linspace(1.0,40.0,50)

        H, xedges, yedges = np.histogram2d(cat1["period"], cat1["sig"], bins=(xedges, yedges))
        H = H.T  # Let each row list bins with common y range.
        X, Y = np.meshgrid(xedges, yedges)
        #H[H==0] = np.nan

        cmap = matplotlib.cm.viridis
        cmap.set_bad('white',0)

        plotName = os.path.join(outputDir, "period_significance_1.pdf")
        fig = plt.figure(figsize=(10,8))

        gs = fig.add_gridspec(nrows=4, ncols=3, wspace=0.2, hspace=0.3)
        ax1 = fig.add_subplot(gs[1:, :])
        ax2 = fig.add_subplot(gs[0, 0])
        ax3 = fig.add_subplot(gs[0, 1])
        ax4 = fig.add_subplot(gs[0, 2])

        plt.axes(ax1)
        c = plt.pcolormesh(X, Y, H, vmin=1.0,vmax=np.max(H),norm=LogNorm(),
                           cmap=cmap)
        plt.xlabel('Period [days]')
        plt.ylabel('Significance')
        cbar = plt.colorbar(c)
        cbar.set_label('Counts')
        ax1.set_xscale('log')
        #ax.set_yscale('log')
        plt.xlim([0.02, 1000])
        plt.ylim([4.0, 40])

        bins = np.linspace(0.45,0.55,21)
        hist, bin_edges = np.histogram(cat1["period"], bins=bins, density=False)
        bins = (bin_edges[1:] + bin_edges[:-1])/2.0

        plt.axes(ax2)
        plt.plot(bins, hist, color = 'k', linestyle='-', drawstyle='steps')
        plt.ylabel('Counts')
        plt.yticks([], [])

        bins = np.linspace(0.95,1.05,21)
        hist, bin_edges = np.histogram(cat1["period"], bins=bins, density=False)
        bins = (bin_edges[1:] + bin_edges[:-1])/2.0

        plt.axes(ax3)
        plt.plot(bins, hist, color = 'k', linestyle='-', drawstyle='steps')
        plt.yticks([], [])

        bins = np.linspace(26,30,21)
        hist, bin_edges = np.histogram(cat1["period"], bins=bins, density=False)
        bins = (bin_edges[1:] + bin_edges[:-1])/2.0

        plt.axes(ax4)
        plt.plot(bins, hist, color = 'k', linestyle='-', drawstyle='steps')
        plt.yticks([], [])

        plt.savefig(plotName, bbox_inches='tight')
        plt.close()

