import os
import psutil
import time
import json
from pathlib import Path


def get_directory_size(path='storage'):
    p = Path(path)
    return sizeof_fmt(sum(f.stat().st_size for f in p.glob('**/*') if f.is_file()))

def get_scan_count(path):
    pass

def get_data(path='storage/scans/'):
    scans = get_scans(path)
    html = '<h1>SUNSCAN</h1>'
    for s in scans:
        html += '<h2>'+os.path.basename(s['path'])+'</h2><a href="/'+os.path.join(s['path'],'scan.ser')+'" target="_blank">Download SER file</a><br><a href="/'+os.path.join(s['path'],'Complements/_scan_raw.fits')+'" target="_blank">Download RAW fits file</a><p>'
        for k, im in s['images'].items():
            html += '<a href="/'+s['path']+'/sunscan_'+k+'.png" target="_blank"><img src="/'+s['path']+'/sunscan_'+k+'.jpg" width="200" height="200"/></a>'
        html += '</p>'
    return html

def get_data2(path='storage/snapshots/'):
    html = '<h1>SUNSCAN snapshots</h1>'
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            if '.png' in name:
                html += '<a href="/'+os.path.join(root, name)+'" target="_blank">'+os.path.join(root, name)+'<br><img src="/'+os.path.join(root, name)+'" width="200"/></a><br><br>'
    return html

def get_single_scan(path):
    base = os.path.dirname(path)
    print(base)
    return get_scans(base, True)[0]

def get_paginated_scans(page: int = 1, size: int = 2):
    all_files = get_scans()
    total_files = len(all_files)
    
    start = (page - 1) * size
    end = start + size

    if start >= total_files:
        return {"total":total_files, "scans":[]}

    paginated_files = all_files[start:end]

    return {"total":total_files, "scans":paginated_files}

def get_scans(path='storage/scans/', withDetails=False):
    scans = []
    images_type = {'clahe':'Clahe + Unsharp mask',
                    'protus':'Artificial eclipse : Clahe + Unsharp mask',
                    'cont':'Continuum : Clahe + Unsharp mask',
                    'doppler':'Doppler',
                    'clahe_colour':'Clahe + Unsharp mask + Halpha colorization',
                    'clahe_colour_caII':'Clahe + Unsharp mask + Ca II colorization',
                    'raw':  'Raw'}

    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            if name == "scan.ser":
                dir_name = root.split('/')[-1]
                if dir_name:
                    ser_path = os.path.join(root, name)
                    ser_dirname = os.path.dirname(ser_path)
                    cti = int(os.path.getmtime(ser_path))

                    images = {}

                    if withDetails:  
                        for im, im_desc in images_type.items():
                            p = os.path.join(ser_dirname,'sunscan_'+im+'.jpg')
                            ti_m = os.path.getmtime(path)
                            images[im] = [im_desc, os.path.exists(p), ti_m]
                                
                    scans.append({'path':ser_dirname, 'ser':ser_path, 'images':images, 'status':'pending', 'creation_date':cti})
    scans = sorted(scans, key=lambda x: x['creation_date'], reverse=True)

    scans_with_status = []
    for s in scans:
        
        if os.path.exists(os.path.join(s['path'],'sunscan_clahe.png')):
            s['status'] = 'completed'
        elif os.path.exists(os.path.join(s['path'],'sunscan_log.txt')):
            s['status'] = 'failed'

        if os.path.exists(os.path.join(s['path'], 'sunscan_conf.txt')):
            d = open(os.path.join(s['path'], 'sunscan_conf.txt'))
            c = json.load(d)
            s['configuration'] = c
        scans_with_status.append(s)
        print(s)
    return scans_with_status  
    

def sizeof_fmt(num, suffix="b"):
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"


def get_available_size(path="/"):
    du = psutil.disk_usage(path)
    return {"total":sizeof_fmt(du.total),"used":sizeof_fmt(du.used),"free":sizeof_fmt(du.free)}

if __name__ == '__main__':
    print(get_available_size())
    print(get_directory_size())
    print(get_scans())