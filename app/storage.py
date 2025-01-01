import os
import psutil
import time
import re
import json
from pathlib import Path
from typing import Callable
from config import LineDict

def get_directory_size(path='storage'):
    """
    Calculate the total size of a directory.

    Args:
        path (str): Path to the directory. Defaults to 'storage'.

    Returns:
        str: Formatted string representing the total size of the directory.
    """
    p = Path(path)
    return sizeof_fmt(sum(f.stat().st_size for f in p.glob('**/*') if f.is_file()))

def get_scan_count(path):
    """
    Get the count of scans in a directory.

    Args:
        path (str): Path to the directory containing scans.

    Returns:
        None: This function is not implemented yet.
    """
    pass

def get_data(path='storage/scans/'):
    """
    Generate HTML content for scan data.

    Args:
        path (str): Path to the scans directory. Defaults to 'storage/scans/'.

    Returns:
        str: HTML content displaying scan information and thumbnails.
    """
    scans = get_scans(path, True)
    html = '<h1>SUNSCAN</h1>'
    for s in scans:
        html += '<h2>'+os.path.basename(s['path'])+'</h2><a href="/'+os.path.join(s['path'],'scan.ser')+'" target="_blank">Download SER file</a><br><a href="/'+os.path.join(s['path'],'Complements/_scan_raw.fits')+'" target="_blank">Download RAW fits file</a><p>'
        for k, im in s['images'].items():
            html += '<a href="/'+s['path']+'/sunscan_'+k+'.png" target="_blank"><img src="/'+s['path']+'/sunscan_'+k+'.jpg" width="200" height="200"/></a>'
        html += '</p>'
    return html

def get_data2(path='storage/snapshots/'):
    """
    Generate HTML content for snapshot data.

    Args:
        path (str): Path to the snapshots directory. Defaults to 'storage/snapshots/'.

    Returns:
        str: HTML content displaying snapshot information and thumbnails.
    """
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

def get_scan_tag(path):
    tag = ''
    tag_files = [f for f in os.listdir(path) if f.startswith('tag_')]
    if tag_files:
        tag_value = tag_files[0].split('_', 1)[-1]  # Extract tag value after 'tag_' 
        if tag_value in LineDict:
            tag = LineDict[tag_value]
    return tag

def get_stacked_scans(path='storage/stacking/', withDetails=False):
    scans = []
    regex = r"stacked_(clahe|cont|protus)_(\d)_(raw|sharpen).png"
    for root, dirs, files in os.walk(path, topdown=False):
        stacking_dirname = None
        images = []
        for name in files:
            if "stacked" in name:
                dir_name = root.split('/')[-1]
                if dir_name:
                    file_path = os.path.join(root, name)
                    stacking_dirname = os.path.dirname(file_path)
                    cti = int(os.path.getmtime(stacking_dirname))

                    if "stacked_clahe" in file_path:
                        images.append(file_path)
                    elif "stacked_cont" in file_path:
                        images.append(file_path)

                    match = re.match(regex, name)
                    if match:
                        stacked_img_count = match.group(2)
        if len(dirs) ==0 and stacking_dirname:                    
            scans.append({'path':stacking_dirname, 'stacked_img_count':stacked_img_count, 'images':images, 'creation_date':cti})
    scans = sorted(scans, key=lambda x: x['creation_date'], reverse=True)
    return scans  

def get_animated_scans(path='storage/animations/', withDetails=False):
    scans = []

    for root, dirs, files in os.walk(path, topdown=False):
        stacking_dirname = None
        images = []
        for name in files:
            if "animated" in name:
                dir_name = root.split('/')[-1]
                if dir_name:
                    file_path = os.path.join(root, name)
                    stacking_dirname = os.path.dirname(file_path)
                    cti = int(os.path.getmtime(stacking_dirname))

                    if "clahe" in file_path:
                        images.append(file_path)
                    elif "cont" in file_path:
                        images.append(file_path)
                    elif "protus" in file_path:
                        images.append(file_path)

        if len(dirs) ==0 and stacking_dirname:                    
            scans.append({'path':stacking_dirname, 'images':images, 'creation_date':cti})
    scans = sorted(scans, key=lambda x: x['creation_date'], reverse=True)
    return scans  

def get_scans(path='storage/scans/', withDetails=False):
    scans = []
    images_type = {'clahe':'Clahe + Unsharp mask',
                    'protus':'Artificial eclipse : Clahe + Unsharp mask',
                    'cont':'Continuum : Clahe + Unsharp mask',
                    'doppler':'Doppler',
                    'clahe_colour':'Clahe + Unsharp mask + colour',
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
        if os.path.exists(os.path.join(s['path'],'sunscan_clahe.jpg')):
            s['status'] = 'completed'
        elif os.path.exists(os.path.join(s['path'],'sunscan_log.txt')):
            s['status'] = 'failed'

        # Check for tag_ file and set s['tag'] accordingly
        s['tag'] = ''
        tag_files = [f for f in os.listdir(s['path']) if f.startswith('tag_')]
        if tag_files:
            tag_value = tag_files[0].split('_', 1)[-1]  # Extract tag value after 'tag_'
            s['tag'] = tag_value

        try:
            with open(os.path.join(s['path'], 'sunscan_conf.txt')) as d:
                c = json.load(d)
                s['configuration'] = c
        except Exception as e:
            pass
        scans_with_status.append(s)
    return scans_with_status  
    
def get_paginated_scans(page: int = 1, size: int = 20, get_scan_fct: Callable = get_scans):
    all_files = get_scan_fct()
    total_files = len(all_files)
    
    start = (page - 1) * size
    end = start + size

    if start >= total_files:
        return {"total":total_files, "scans":[]}

    paginated_files = all_files[start:end]

    return {"total":total_files, "scans":paginated_files}

def sizeof_fmt(num, suffix="b"):
    """
    Format a file size into a human-readable string.

    Args:
        num (int): The file size in bytes.
        suffix (str): The suffix to use for the units. Defaults to "b".

    Returns:
        str: A formatted string representing the file size.
    """
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Y{suffix}"


def get_available_size(path="/"):
    """
    Get the available disk space for a given path.

    Args:
        path (str): The path to check for disk space. Defaults to "/".

    Returns:
        dict: A dictionary containing total, used, and free disk space in formatted strings.
    """
    du = psutil.disk_usage(path)
    return {"total":sizeof_fmt(du.total),"used":sizeof_fmt(du.used),"free":sizeof_fmt(du.free)}

if __name__ == '__main__':
    print(get_available_size())
    print(get_directory_size())
    print(get_animated_scans())