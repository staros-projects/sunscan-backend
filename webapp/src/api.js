// Client of the SUNSCAN backend. The API runs on port 8000 of the host that served the page,
// so the gallery works whatever the address used to reach it (sunscan.local, hotspot IP...).
// VITE_API_URL overrides it for development.
const API = import.meta.env.VITE_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`;

export const apiUrl = (path) => API + path;

const encodePath = (path) => path.split('/').map(encodeURIComponent).join('/');
const pathsQuery = (paths, exts) => paths.map((p) => 'paths=' + encodeURIComponent(p))
  .concat((exts || []).map((e) => 'exts=' + encodeURIComponent(e)))
  .join('&');

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(url, options) {
  let res;
  try {
    res = await fetch(url, options);
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(`No answer from the SUNSCAN backend (${API}). Check the Wi-Fi connection, or restart the SUNSCAN.`, 0);
  }
  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      // not a JSON error
    }
    throw new ApiError(typeof detail === 'string' ? detail : `Error ${res.status}`, res.status);
  }
  return res;
}

export const SECTIONS = ['scans', 'stacking', 'animations', 'snapshots'];

// flat: at the root of the scans, every scan of every date instead of the date folders
export const listFolder = (section, path, signal, flat = false) =>
  request(apiUrl(`/gallery/list/${section}${path ? '/' + encodePath(path) : ''}${flat ? '?flat=1' : ''}`), { signal })
    .then((r) => r.json());

// { bytes, files, by_ext: { ser: { bytes, files }, ... }, max_bytes }; exts restricts to these file types
export const selectionSize = (section, paths, signal, exts) =>
  request(apiUrl(`/gallery/size/${section}?${pathsQuery(paths, exts)}`), { signal }).then((r) => r.json());

export const deleteEntries = (section, paths) =>
  request(apiUrl(`/gallery/${section}?${pathsQuery(paths)}`), { method: 'DELETE' }).then((r) => r.json());

export const fetchText = (section, path) => request(fileUrl(section, path)).then((r) => r.text());

export const getStats = () => request(apiUrl('/sunscan/stats')).then((r) => r.json());

export const fileUrl = (section, path) => apiUrl(`/gallery/file/${section}/${encodePath(path)}`);

// thumb is the URL given by the listing, already versioned with the file mtime
export const thumbUrl = (thumb, width = 320) => (thumb ? apiUrl(`${thumb}&w=${width}`) : null);

export const downloadUrl = (section, paths, exts) => apiUrl(`/gallery/download/${section}?${pathsQuery(paths, exts)}`);

// The response is an attachment: the browser downloads it without leaving the page
export function triggerDownload(url) {
  const a = document.createElement('a');
  a.href = url;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
}
