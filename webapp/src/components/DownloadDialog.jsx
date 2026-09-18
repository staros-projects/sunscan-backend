// Choose what to download: file types (SER, FITS, PNG, JPG...) and, in a scan, which images.
// In a folder of files (a scan) everything is known from the listing and the exact files are
// requested; for a selection of folders the server gives the size per type and filters them.
import { useEffect, useMemo, useState } from 'react';
import { downloadUrl, selectionSize, triggerDownload } from '../api';
import { formatBytes } from '../lib/format';

const TYPE_GROUPS = [
  { id: 'ser', label: 'Raw video (SER)', exts: ['ser'] },
  { id: 'fits', label: 'FITS data', exts: ['fits', 'fit'] },
  { id: 'png', label: 'PNG images (full quality)', exts: ['png'] },
  { id: 'jpg', label: 'JPG images', exts: ['jpg', 'jpeg'] },
  { id: 'gif', label: 'Animations (GIF)', exts: ['gif'] },
  { id: 'text', label: 'Logs and settings', exts: ['txt', 'log', 'json'] },
];
const IMAGE_GROUPS = ['png', 'jpg', 'gif'];
const SLOW_DOWNLOAD_BYTES = 1024 ** 3;

const extOf = (name) => {
  const i = name.lastIndexOf('.');
  return i > 0 ? name.slice(i + 1).toLowerCase() : '';
};

// Type groups present in { ext: { bytes, files } }, the unknown extensions under 'Other files'
function typeGroups(byExt) {
  const known = new Set(TYPE_GROUPS.flatMap((g) => g.exts));
  const groups = TYPE_GROUPS.map((g) => ({ ...g }));
  // files without extension are the scan tags: empty, sent with a full download only
  const other = Object.keys(byExt).filter((e) => e && !known.has(e));
  if (other.length) groups.push({ id: 'other', label: 'Other files', exts: other });
  return groups
    .map((g) => ({
      ...g,
      bytes: g.exts.reduce((s, e) => s + (byExt[e]?.bytes || 0), 0),
      files: g.exts.reduce((s, e) => s + (byExt[e]?.files || 0), 0),
    }))
    .filter((g) => g.files > 0);
}

const PRESETS = [
  { id: 'all', label: 'Everything', types: null },
  { id: 'ser', label: 'SER only', types: ['ser'] },
  { id: 'images', label: 'Images only', types: IMAGE_GROUPS },
  { id: 'jpg', label: 'JPG only', types: ['jpg'] },
];

/**
 * section, paths: what is downloaded. title: shown under the heading.
 * folder: { path, files, images } when downloading the folder being viewed, files being its file
 * entries and images the image items built from them (see lib/items), to pick images one by one.
 */
export default function DownloadDialog({ section, paths, title, folder, maxBytes, onClose, onStarted, onError }) {
  const [byExt, setByExt] = useState(null);
  const [limit, setLimit] = useState(maxBytes || null);
  const [types, setTypes] = useState(null); // Set of type group ids, null until known
  const [images, setImages] = useState(() => new Set(folder?.images.map((i) => i.key) || []));

  // size per type
  useEffect(() => {
    if (folder) {
      const map = {};
      for (const f of folder.files) {
        const s = (map[extOf(f.name)] ||= { bytes: 0, files: 0 });
        s.bytes += f.size;
        s.files += 1;
      }
      setByExt(map);
      return undefined;
    }
    const ctrl = new AbortController();
    selectionSize(section, paths, ctrl.signal)
      .then((size) => {
        setByExt(size.by_ext);
        setLimit(size.max_bytes);
      })
      .catch((e) => {
        if (e.name !== 'AbortError') {
          onError(e.message);
          onClose();
        }
      });
    return () => ctrl.abort();
  }, [section, paths, folder, onClose, onError]);

  const groups = useMemo(() => (byExt ? typeGroups(byExt) : []), [byExt]);

  useEffect(() => {
    if (byExt && types === null) setTypes(new Set(groups.map((g) => g.id)));
  }, [byExt, groups, types]);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const imageTypesChecked = types && IMAGE_GROUPS.some((id) => types.has(id));
  const allTypes = types && groups.every((g) => types.has(g.id));
  const allImages = !folder || folder.images.every((i) => images.has(i.key));

  // What the download will contain
  const plan = useMemo(() => {
    if (!types) return null;
    const checked = groups.filter((g) => types.has(g.id));
    const exts = new Set(checked.flatMap((g) => g.exts));
    if (folder) {
      const excluded = new Set(folder.images.filter((i) => !images.has(i.key)).flatMap((i) => i.paths));
      const files = folder.files.filter((f) => exts.has(extOf(f.name)) && !excluded.has(f.path));
      const bytes = files.reduce((s, f) => s + f.size, 0);
      // everything: the folder itself, so the zip is named after it and keeps the tag
      const request = allTypes && allImages ? { paths: [folder.path] } : { paths: files.map((f) => f.path) };
      return { bytes, files: files.length, ...request };
    }
    return {
      bytes: checked.reduce((s, g) => s + g.bytes, 0),
      files: checked.reduce((s, g) => s + g.files, 0),
      paths,
      exts: allTypes ? undefined : [...exts],
    };
  }, [types, groups, folder, images, allTypes, allImages, paths]);

  const toggleType = (id) => setTypes((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });

  const toggleImage = (key) => setImages((prev) => {
    const next = new Set(prev);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    return next;
  });

  const applyPreset = (preset) => {
    const present = groups.map((g) => g.id);
    setTypes(new Set(preset.types ? present.filter((id) => preset.types.includes(id)) : present));
    if (folder) setImages(new Set(folder.images.map((i) => i.key)));
  };

  const activePreset = types && PRESETS.find((p) => {
    const want = groups.map((g) => g.id).filter((id) => !p.types || p.types.includes(id));
    return allImages && want.length === types.size && want.every((id) => types.has(id));
  });
  const presets = PRESETS.filter((p) => !p.types || groups.some((g) => p.types.includes(g.id)));

  const tooBig = plan && limit && plan.bytes > limit;
  const start = () => {
    triggerDownload(downloadUrl(section, plan.paths, plan.exts));
    onStarted();
  };

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <div className="dialog dialog-wide" role="dialog" aria-modal="true" aria-labelledby="download-title" onClick={(e) => e.stopPropagation()}>
        <h2 id="download-title">Download</h2>
        {title && <p className="muted dialog-subtitle">{title}</p>}

        {!types ? (
          <p className="muted">Computing sizes…</p>
        ) : (
          <>
            <div className="presets" role="group" aria-label="Quick choices">
              {presets.map((p) => (
                <button key={p.id} className={`chip ${activePreset?.id === p.id ? 'chip-active' : ''}`} onClick={() => applyPreset(p)}>
                  {p.label}
                </button>
              ))}
            </div>

            <fieldset className="choice-list">
              <legend>File types</legend>
              {groups.map((g) => (
                <label key={g.id} className="check-row">
                  <input type="checkbox" checked={types.has(g.id)} onChange={() => toggleType(g.id)} />
                  <span className="check-label">{g.label}</span>
                  <span className="muted">{formatBytes(g.bytes)} · {g.files} {g.files === 1 ? 'file' : 'files'}</span>
                </label>
              ))}
            </fieldset>

            {folder && folder.images.length > 0 && (
              <fieldset className="choice-list" disabled={!imageTypesChecked}>
                <legend>
                  Images
                  <button type="button" className="link-btn" onClick={() => setImages(new Set(folder.images.map((i) => i.key)))}>All</button>
                  <button type="button" className="link-btn" onClick={() => setImages(new Set())}>None</button>
                </legend>
                <div className="chips">
                  {folder.images.map((i) => (
                    <label key={i.key} className={`chip ${images.has(i.key) ? 'chip-active' : ''}`}>
                      <input type="checkbox" className="visually-hidden" checked={images.has(i.key)} onChange={() => toggleImage(i.key)} />
                      {i.title}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}

            <p className={`download-total ${tooBig ? 'error-text' : ''}`}>
              {plan.files === 0
                ? 'Nothing selected'
                : `${plan.files} ${plan.files === 1 ? 'file' : 'files'} · ${formatBytes(plan.bytes)}`}
              {tooBig && ` · over the ${formatBytes(limit)} limit per download`}
            </p>
            {!tooBig && plan.bytes > SLOW_DOWNLOAD_BYTES && (
              <p className="muted">Over the SUNSCAN Wi-Fi this can take several minutes. Your browser shows the progress.</p>
            )}
          </>
        )}

        <div className="dialog-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" disabled={!plan || plan.files === 0 || tooBig} onClick={start}>Download</button>
        </div>
      </div>
    </div>
  );
}
