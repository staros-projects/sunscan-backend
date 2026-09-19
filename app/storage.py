import os
import psutil
import time
import re
import json
from collections import Counter
from pathlib import Path
from typing import Callable
from config import LineDict

# Images of a processed scan : sunscan_<key>.jpg and their description
images_type = { 'clahe':'Clahe + Unsharp mask',
                'negative':'Negative clahe + Unsharp mask',
                'helium_cont': 'Helium + Continuum',
                'helium': 'Helium',
                'protus':'Artificial eclipse : Clahe + Unsharp mask',
                'protus_doppler':'Artificial eclipse : Clahe + Unsharp mask',
                'cont':'Continuum : Clahe + Unsharp mask',
                'doppler':'Doppler',
                'color': 'Artificial color',
                'clahe_colour':'Clahe + Unsharp mask + Artificial color',
                'hepsilon':'Hε : Clahe + Unsharp mask',
                'hepsilon_color':'Hε : Artificial color',
                'hepsilon_protus':'Hε : Artificial eclipse',
                'raw':  'Raw'}

# Written in the directory of a scan, a stack or an animation by spectrosolhub.py once its images are on SpectroSolHub
SPECTROSOLHUB_FILE = 'sunscan_spectrosolhub.json'

# Written in the directory of a stack or an animation when it is created : the scans it comes from, their
# line and their acquisition dates. The directory itself is named after the time it was created, which can
# be months after the observation.
SOURCES_FILE = 'sunscan_sources.json'

def hub_mark(path):
    """Fields added to a scan, a stack or an animation : last upload to SpectroSolHub (None if never sent) and its mark."""
    record = None
    try:
        with open(os.path.join(path, SPECTROSOLHUB_FILE)) as d:
            record = json.load(d)
    except Exception as e:
        pass
    return {'spectrosolhub': record, 'hub_status': 'sent' if record else 'not_sent'}

def get_tag(path):
    """Tag of a scan, a stack or an animation : the <key> of its tag_<key> file, '' when it has none. Not only keys of LineDict ('other')."""
    try:
        tags = [f.split('_', 1)[-1] for f in os.listdir(path) if f.startswith('tag_')]
    except OSError:
        return ''
    return tags[0] if tags else ''

def get_scan_tag_key(path):
    """Line tag of a scan as a key of LineDict ('halpha'), '' when it has none. get_scan_tag returns its label."""
    tag = get_tag(path)
    return tag if tag in LineDict else ''

def get_creation_date(directory):
    """
    Creation time of a stack or an animation, from its directory, named after it (Pi local time).
    Not the date of the directory : it changes each time a file is added to it (tag, mark of the upload
    to SpectroSolHub), which moved the stack to the top of the list.
    """
    try:
        return int(time.mktime(time.strptime(os.path.basename(directory), '%Y-%m-%d_%H-%M-%S')))
    except ValueError:
        # Renamed directory : its oldest file, the files added later do not count
        return int(min(os.path.getmtime(os.path.join(directory, f)) for f in os.listdir(directory)))

def read_sources(path):
    """Content of SOURCES_FILE of a stack or an animation, None for those created before it existed."""
    try:
        with open(os.path.join(path, SOURCES_FILE)) as d:
            return json.load(d)
    except Exception as e:
        return None

def save_sources(work_dir, kind, paths):
    """
    Record what a new stack or animation is made of. Never raises : it must not fail a stacking.

    Args:
        work_dir (str): Directory of the new stack or animation.
        kind (str): 'stack' or 'animation'.
        paths (list): Sources as sent by the frontend : SER files or directories of scans, or directories of stacks.
    """
    try:
        sources, dates, tag, other_tag = [], [], '', ''
        for p in paths:
            directory = os.path.dirname(p) if str(p).endswith('.ser') else str(p).rstrip('/')
            sources.append(directory)
            # The tag_ file of a scan, or of a stack (animation of stacks) : a stack made before its sources
            # were recorded can have been tagged by hand
            tag = tag or get_scan_tag_key(directory)
            other_tag = other_tag or get_tag(directory)
            # The directories of the scans are named with the UTC time of their recording
            match = re.search(r'sunscan_(\d{4})_(\d{2})_(\d{2})-(\d{2})_(\d{2})_(\d{2})$', directory)
            if match:
                dates.append('{}-{}-{}T{}:{}:{}Z'.format(*match.groups()))
                continue
            # An animation of stacks : the dates and the line are the ones of the stacks
            nested = read_sources(directory)
            if nested and nested.get('date_first'):
                dates += [nested['date_first'], nested['date_last']]
                tag = tag or nested.get('line', '')
            else:
                dates.append(None)
        known = None not in dates and len(dates) > 0
        meta = {'kind': kind, 'sources': sources, 'count': len(sources), 'line': tag,
                'date_first': min(dates) if known else None, 'date_last': max(dates) if known else None}
        with open(os.path.join(work_dir, SOURCES_FILE), 'w') as d:
            json.dump(meta, d)
        # Same tag_<key> file as the scans, to filter the stacks and the animations by line : the line written
        # on their images (first scan tagged with a line), else the first tag which is not a line ('other')
        if tag or other_tag:
            open(os.path.join(work_dir, 'tag_' + (tag or other_tag)), 'w').close()
    except Exception as e:
        print('error save_sources', e)

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

    # Create the directory if it doesn't exist
    if not os.path.exists(path):
        os.mkdir(path)
        
    scans = []
    regex = r"stacked_(helium|helium_cont|negative|clahe|cont|protus)_(\d)_(raw|sharpen).png"
    for root, dirs, files in os.walk(path, topdown=False):
        stacking_dirname = None
        images = []
        for name in files:
            if "stacked" in name:
                dir_name = root.split('/')[-1]
                if dir_name:
                    file_path = os.path.join(root, name)
                    stacking_dirname = os.path.dirname(file_path)

                    if "stacked_negative" in file_path:
                        images.append(file_path)
                    if "stacked_color" in file_path:
                        images.append(file_path)
                    if "stacked_clahe" in file_path:
                        images.append(file_path)
                    elif "stacked_cont" in file_path:
                        images.append(file_path)
                    # elif "stacked_protus" in file_path:
                    #     images.append(file_path)
                    match = re.match(regex, name)
                    if match:
                        stacked_img_count = match.group(2)
        if len(dirs) ==0 and stacking_dirname:                    
            scans.append({'path':stacking_dirname, 'stacked_img_count':stacked_img_count, 'images':images, 'creation_date':get_creation_date(stacking_dirname), 'tag':get_tag(stacking_dirname)} | hub_mark(stacking_dirname))
    scans = sorted(scans, key=lambda x: x['creation_date'], reverse=True)
    return scans  

def get_animated_scans(path='storage/animations/', withDetails=False):

    # Create the directory if it doesn't exist
    if not os.path.exists(path):
        os.mkdir(path)

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

                    if "helium" in file_path:
                        images.append(file_path)
                    elif "negative" in file_path:
                        images.append(file_path)
                    elif "clahe" in file_path:
                        images.append(file_path)
                    elif "cont" in file_path:
                        images.append(file_path)
                    elif "color" in file_path:
                        images.append(file_path)
                    elif "protus" in file_path:
                        images.append(file_path)

        if len(dirs) ==0 and stacking_dirname:                    
            scans.append({'path':stacking_dirname, 'images':images, 'creation_date':get_creation_date(stacking_dirname), 'tag':get_tag(stacking_dirname)} | hub_mark(stacking_dirname))
    scans = sorted(scans, key=lambda x: x['creation_date'], reverse=True)
    return scans  

def get_scan_day(scan_dir, creation_date):
    # Acquisition day 'YYYY-MM-DD' (Pi local time), from the scan folder name which survives
    # a copy of the files, else from the file date
    m = re.match(r"sunscan_(\d{4})_(\d{2})_(\d{2})-", os.path.basename(scan_dir))
    if m:
        return '-'.join(m.groups())
    return time.strftime('%Y-%m-%d', time.localtime(creation_date))

def get_scans(path='storage/scans/', withDetails=False):

    # Create the directory if it doesn't exist
    if not os.path.exists(path):
        os.mkdir(path)

    scans = []
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
                                
                    scans.append({'path':ser_dirname, 'ser':ser_path, 'images':images, 'status':'pending', 'creation_date':cti, 'day':get_scan_day(ser_dirname, cti), 'planispheres':[]})
    # By day first, so that scans of a same day stay together even when the file date differs (copied scans)
    scans = sorted(scans, key=lambda x: (x['day'], x['creation_date']), reverse=True)

    scans_with_status = []
    for s in scans:   
        if os.path.exists(os.path.join(s['path'],'sunscan_preview.jpg')):
            s['status'] = 'completed'
        elif os.path.exists(os.path.join(s['path'],'sunscan_log.txt')):
            s['status'] = 'failed'

        for suffix in ["clahe", "negative", "color", "doppler", "cont", "helium_cont", "helium"]:
            fname = f"sunscan_{suffix}_proj.jpg"
            fpath = os.path.join(s["path"], fname)
            if os.path.exists(fpath):
                s["planispheres"].append(fpath)
         
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

        # Last upload of the scan to SpectroSolHub (session url, published or draft) and mark of the
        # scans whose images are on the hub, to filter them (and free the SD card)
        s.update(hub_mark(s['path']))
        scans_with_status.append(s)
    return scans_with_status  
    
# Gallery filters : query parameter -> test on a scan ('none' = untagged scans, dates are 'YYYY-MM-DD', inclusive)
SCAN_FILTERS = {
    'tag': lambda s, v: s['tag'] == ('' if v == 'none' else v),
    'status': lambda s, v: s['status'] == v,
    'date_from': lambda s, v: s['day'] >= v,
    'date_to': lambda s, v: s['day'] <= v,
    'hub_status': lambda s, v: s['hub_status'] == v,
}

# Counts returned with the scans : response key -> (scan field, filters acting on that field)
SCAN_COUNTS = {
    'tags': ('tag', ('tag',)),
    'statuses': ('status', ('status',)),
    'days': ('day', ('date_from', 'date_to')),
    'hub_statuses': ('hub_status', ('hub_status',)),
}

# Stacks and animations : they have a tag and a mark of SpectroSolHub, no status, and their day is not an observation day
STACK_COUNTS = {key: SCAN_COUNTS[key] for key in ('tags', 'hub_statuses')}

def filter_scans(scans, filters, ignore=()):
    active = [(SCAN_FILTERS[k], v) for k, v in filters.items() if v is not None and k not in ignore]
    return [s for s in scans if all(test(s, v) for test, v in active)]

def get_paginated_scans(page: int = 1, size: int = 20, get_scan_fct: Callable = get_scans, filters: dict = None, counted: dict = SCAN_COUNTS):
    all_files = get_scan_fct()

    counts = {}
    if filters is not None:
        # Each count applies the other filters but not its own : it tells how many scans picking that value would give
        for key, (field, own_filters) in counted.items():
            counts[key] = dict(Counter(s[field] for s in filter_scans(all_files, filters, ignore=own_filters)))
        # Filter before paginating so that total and pages match the filters
        all_files = filter_scans(all_files, filters)

    total_files = len(all_files)

    start = (page - 1) * size
    end = start + size

    paginated_files = [] if start >= total_files else all_files[start:end]

    return {"total":total_files, "scans":paginated_files} | counts

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
    return {"total":sizeof_fmt(du.total),"used":sizeof_fmt(du.used),"free_raw":du.free,"free":sizeof_fmt(du.free)}

if __name__ == '__main__':
    print(get_available_size())
    print(get_directory_size())
    print(get_animated_scans())