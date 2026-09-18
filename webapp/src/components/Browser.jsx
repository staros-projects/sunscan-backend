// One page for every folder of every section: cards grouped by heading, multi-selection,
// download (size checked first) and deletion, full screen viewer.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  SECTIONS, deleteEntries, downloadUrl, listFolder, selectionSize, thumbUrl, triggerDownload,
} from '../api';
import { formatBytes } from '../lib/format';
import { buildItems, segmentLabel } from '../lib/items';
import DownloadDialog from './DownloadDialog';
import { useFeedback } from './Feedback';
import {
  FileIcon, IconCheck, IconClose, IconDownload, IconFolder, IconRefresh, IconSelect, IconSun, IconTrash,
} from './Icons';
import { Shell, useStats } from './Shell';
import Viewer from './Viewer';

const SECTION_TITLES = { scans: 'Scans', stacking: 'Stacking', animations: 'Animations', snapshots: 'Snapshots' };

const encodePath = (path) => path.split('/').map(encodeURIComponent).join('/');
const folderLink = (section, path) => `/${section}${path ? '/' + encodePath(path) : ''}`;

function useListing(section, path, flat) {
  const [state, setState] = useState({ listing: null, error: null, loading: true });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    const ctrl = new AbortController();
    setState((s) => ({ listing: s.listing?.section === section && s.listing?.path === path ? s.listing : null, error: null, loading: true }));
    listFolder(section, path, ctrl.signal, flat)
      .then((listing) => setState({ listing, error: null, loading: false }))
      .catch((error) => error.name !== 'AbortError' && setState({ listing: null, error, loading: false }));
    return () => ctrl.abort();
  }, [section, path, flat, version]);

  return { ...state, reload: useCallback(() => setVersion((v) => v + 1), []) };
}

function Thumb({ item, width }) {
  const [failed, setFailed] = useState(false);
  if (item.thumb && !failed) {
    return <img src={thumbUrl(item.thumb, width)} alt="" loading="lazy" decoding="async" onError={() => setFailed(true)} />;
  }
  return (
    <div className="thumb-icon">
      {item.kind === 'dir' ? <IconFolder size={40} /> : <FileIcon ext={item.ext} size={40} />}
    </div>
  );
}

function Card({ item, section, selected, selecting, onToggle, onOpen }) {
  const body = (
    <>
      <div className="card-thumb"><Thumb item={item} width={320} /></div>
      <div className="card-body">
        <span className="card-title">{item.title}</span>
        <span className="card-sub">
          {item.subtitle}
          {item.formats?.length > 1 && <span className="badge">{item.formats.join(' · ').toUpperCase()}</span>}
          {item.tag && <span className="badge badge-accent">{item.tag}</span>}
        </span>
      </div>
    </>
  );

  let main;
  if (selecting) {
    main = <button className="card-main" onClick={() => onToggle(item)} aria-pressed={selected}>{body}</button>;
  } else if (item.kind === 'dir') {
    main = <Link className="card-main" to={folderLink(section, item.path)}>{body}</Link>;
  } else {
    main = <button className="card-main" onClick={() => onOpen(item)}>{body}</button>;
  }

  return (
    <div className={`card ${selected ? 'card-selected' : ''} ${selecting ? 'card-selecting' : ''}`}>
      {main}
      <button className="card-check" onClick={() => onToggle(item)} aria-pressed={selected}
        aria-label={`${selected ? 'Unselect' : 'Select'} ${item.title}`}>
        {selected && <IconCheck size={16} />}
      </button>
    </div>
  );
}

// The newest scan, shown big at the top of the scans
function LatestScan({ scan }) {
  return (
    <Link className="hero" to={folderLink('scans', scan.path)}>
      <div className="hero-thumb">
        {scan.thumb ? <img src={thumbUrl(scan.thumb, 640)} alt="" /> : <IconSun size={64} />}
      </div>
      <div className="hero-body">
        <span className="eyebrow">Latest scan</span>
        <span className="hero-title">{scan.heading}</span>
        <span className="hero-sub">
          {scan.title}
          {scan.tag && <span className="badge badge-accent">{scan.tag}</span>}
        </span>
        <span className="btn btn-primary">Open</span>
      </div>
    </Link>
  );
}

function SelectionBar({ section, items, allSelected, onSelectAll, onClear, onDownload, onDelete }) {
  const [size, setSize] = useState(null);
  const paths = useMemo(() => items.flatMap((i) => i.paths), [items]);
  const deletable = items.length > 0 && items.every((i) => i.deletable);

  useEffect(() => {
    setSize(null);
    if (!paths.length) return undefined;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      selectionSize(section, paths, ctrl.signal).then(setSize).catch(() => {});
    }, 250);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [section, paths]);

  const tooBig = size && size.bytes > size.max_bytes;

  return (
    <div className="selection-bar" role="toolbar" aria-label="Selection">
      <div className="selection-info">
        <strong>{items.length} selected</strong>
        <span className={tooBig ? 'error-text' : 'muted'}>
          {size ? formatBytes(size.bytes) : items.length ? '…' : ''}
          {tooBig && ` · over the ${formatBytes(size.max_bytes)} limit`}
        </span>
      </div>
      <div className="selection-actions">
        <button className="btn" onClick={allSelected ? onClear : onSelectAll}>{allSelected ? 'Select none' : 'Select all'}</button>
        <button className="btn btn-primary" disabled={!items.length || tooBig} onClick={() => onDownload(paths)}>
          <IconDownload size={18} /> Download
        </button>
        <button className="btn btn-danger" disabled={!deletable} onClick={() => onDelete(items)}
          title={items.length && !deletable ? 'Files of a scan are not deleted one by one: delete the whole scan' : undefined}>
          <IconTrash size={18} /> Delete
        </button>
        <button className="icon-btn" onClick={onClear} aria-label="End selection"><IconClose /></button>
      </div>
    </div>
  );
}

export default function Browser() {
  const params = useParams();
  const section = params.section;
  const path = (params['*'] || '').replace(/\/+$/, '');
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast, confirm } = useFeedback();
  const { refreshStats } = useStats();

  // at the root of the scans, the scans themselves (grouped by day) rather than the date folders
  const flat = section === 'scans' && !path;
  const { listing, error, loading, reload } = useListing(section, path, flat);
  const built = useMemo(() => (listing ? buildItems(listing) : null), [listing]);
  const allItems = useMemo(() => (built ? built.groups.flatMap((g) => g.items) : []), [built]);

  const [selected, setSelected] = useState(() => new Map());
  const [selecting, setSelecting] = useState(false);
  const [downloadRequest, setDownloadRequest] = useState(null);

  useEffect(() => {
    setSelected(new Map());
    setSelecting(false);
  }, [section, path]);

  const segments = path ? path.split('/') : [];
  const crumbs = [{ label: SECTION_TITLES[section], to: folderLink(section, '') }].concat(
    segments.map((name, i) => ({ label: segmentLabel(section, i, name), to: folderLink(section, segments.slice(0, i + 1).join('/')) })),
  );
  const title = crumbs[crumbs.length - 1].label;

  useEffect(() => {
    document.title = `${title} · SUNSCAN`;
  }, [title]);

  const clearSelection = useCallback(() => {
    setSelected(new Map());
    setSelecting(false);
  }, []);

  useEffect(() => {
    if (!selecting) return undefined;
    const onKey = (e) => e.key === 'Escape' && !searchParams.get('view') && clearSelection();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selecting, searchParams, clearSelection]);

  const closeDownload = useCallback(() => setDownloadRequest(null), []);
  const downloadStarted = useCallback(() => {
    setDownloadRequest(null);
    toast('Download started');
  }, [toast]);
  const downloadError = useCallback((message) => toast(message, 'error'), [toast]);

  if (!SECTIONS.includes(section)) return <Navigate to="/scans" replace />;

  const toggle = (item) => {
    setSelecting(true);
    setSelected((prev) => {
      const next = new Map(prev);
      if (next.has(item.key)) next.delete(item.key);
      else next.set(item.key, item);
      return next;
    });
  };

  const download = async (paths) => {
    try {
      const size = await selectionSize(section, paths);
      if (size.bytes > size.max_bytes) {
        toast(`${formatBytes(size.bytes)} is over the ${formatBytes(size.max_bytes)} limit per download. Select fewer items.`, 'error');
        return;
      }
      triggerDownload(downloadUrl(section, paths));
      toast('Download started');
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  const remove = async (items) => {
    const paths = items.flatMap((i) => i.paths);
    let sizeText = '';
    try {
      sizeText = ` (${formatBytes((await selectionSize(section, paths)).bytes)})`;
    } catch {
      // the size is only informative
    }
    const ok = await confirm({
      title: `Delete ${items.length} ${items.length === 1 ? 'item' : 'items'}?`,
      body: (
        <>
          <p>{items.slice(0, 5).map((i) => i.title).join(', ')}{items.length > 5 ? '…' : ''}{sizeText}</p>
          <p className="error-text">They are removed from the SUNSCAN for good.</p>
        </>
      ),
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteEntries(section, paths);
      toast(`${items.length} ${items.length === 1 ? 'item' : 'items'} deleted`);
      clearSelection();
      reload();
      refreshStats();
    } catch (e) {
      toast(e.message, 'error');
    }
  };

  // Viewer, driven by ?view=<key> so the back button closes it
  const viewKey = searchParams.get('view');
  const viewable = built?.viewable ?? [];
  const viewIndex = viewKey ? viewable.findIndex((i) => i.key === viewKey) : -1;
  const openItem = (item) => setSearchParams({ view: item.key }, { state: { viewerPushed: true } });
  const navigateViewer = (key) => setSearchParams({ view: key }, { replace: true, state: location.state });
  const closeViewer = () => {
    if (location.state?.viewerPushed) navigate(-1);
    else setSearchParams({}, { replace: true });
  };

  // The folder being viewed: when it only holds files (a scan), choose them one by one
  const openFolderDownload = () => {
    const hasDirs = listing.entries.some((e) => e.kind === 'dir');
    setDownloadRequest({
      paths: [path],
      title: depth === 2 && section === 'scans' ? `Scan of ${segmentLabel(section, 0, segments[0])}, ${title}` : title,
      folder: hasDirs ? null : {
        path,
        files: listing.entries.filter((e) => e.kind === 'file'),
        images: built.groups.find((g) => g.id === 'images')?.items || [],
      },
    });
  };

  const selectedItems = [...selected.values()];
  const depth = segments.length;
  const showLatest = flat && allItems.length > 0 && allItems[0].kind === 'dir';
  // a scan page is titled with its time: recall the date under it
  const folderSubtitle = [];
  if (section === 'scans' && depth === 2) folderSubtitle.push(segmentLabel(section, 0, segments[0]));
  if (listing?.tag) folderSubtitle.push(<span key="tag" className="badge badge-accent">{listing.tag}</span>);

  return (
    <Shell crumbs={crumbs}>
      <div className="page-head">
        <div>
          <h1>{depth === 0 ? SECTION_TITLES[section] : title}</h1>
          {folderSubtitle.length > 0 && <p className="page-sub">{folderSubtitle}</p>}
        </div>
        <div className="page-actions">
          <button className="icon-btn" onClick={reload} aria-label="Refresh" title="Refresh"><IconRefresh /></button>
          {allItems.length > 0 && (
            <button className={`btn ${selecting ? 'btn-active' : ''}`} onClick={() => (selecting ? clearSelection() : setSelecting(true))}>
              <IconSelect size={18} /> {selecting ? 'Done' : 'Select'}
            </button>
          )}
          {depth > 0 && allItems.length > 0 && (
            <button className="btn btn-primary" onClick={openFolderDownload}><IconDownload size={18} /> Download…</button>
          )}
        </div>
      </div>

      {error && (
        <div className="empty">
          <p className="error-text">{error.status === 404 ? 'This folder no longer exists.' : error.message}</p>
          <button className="btn" onClick={reload}>Retry</button>
        </div>
      )}

      {loading && !listing && !error && (
        <div className="grid" aria-busy="true">
          {Array.from({ length: 8 }, (_, i) => <div key={i} className="card skeleton" />)}
        </div>
      )}

      {built && allItems.length === 0 && (
        <div className="empty">
          <IconSun size={48} />
          <p>{depth === 0 ? `No ${SECTION_TITLES[section].toLowerCase()} yet.` : 'This folder is empty.'}</p>
        </div>
      )}

      {showLatest && <LatestScan scan={allItems[0]} />}

      {built?.groups.map((group) => (
        <section key={group.id} className="group">
          {group.title && <h2 className="group-title">{group.title}</h2>}
          <div className={`grid ${group.id === 'images' ? 'grid-images' : ''}`}>
            {group.items.map((item) => (
              <Card key={item.key} item={item} section={section} selected={selected.has(item.key)}
                selecting={selecting} onToggle={toggle} onOpen={openItem} />
            ))}
          </div>
        </section>
      ))}

      {selecting && (
        <SelectionBar section={section} items={selectedItems} allSelected={selected.size === allItems.length}
          onSelectAll={() => setSelected(new Map(allItems.map((i) => [i.key, i])))}
          onClear={clearSelection} onDelete={remove}
          onDownload={(paths) => setDownloadRequest({ paths, title: `${selected.size} selected` })} />
      )}

      {downloadRequest && (
        <DownloadDialog section={section} {...downloadRequest}
          onClose={closeDownload} onStarted={downloadStarted} onError={downloadError} />
      )}

      {viewIndex >= 0 && (
        <Viewer items={viewable} index={viewIndex} section={section}
          onNavigate={navigateViewer} onClose={closeViewer} onDownload={download} />
      )}
    </Shell>
  );
}
