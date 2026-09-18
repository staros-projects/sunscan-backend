// Full screen viewer: images (zoom, rotation, swipe), FITS (through a JPEG preview), text files,
// and a summary for the others
import { useEffect, useRef, useState } from 'react';
import { TransformComponent, TransformWrapper } from 'react-zoom-pan-pinch';
import { fetchText, fileUrl, thumbUrl } from '../api';
import { formatBytes } from '../lib/format';
import {
  FileIcon, IconChevronLeft, IconChevronRight, IconClose, IconDownload, IconRotate, IconZoomIn, IconZoomOut,
} from './Icons';

const SWIPE_MIN_PX = 60;

// src: the image shown, the full file by default
function ImageStage({ item, src, onSwipe, onError }) {
  const [rotation, setRotation] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const scale = useRef(1);
  const touch = useRef(null);

  // only swipe when not zoomed, otherwise the gesture pans the image
  const onTouchStart = (e) => {
    touch.current = scale.current <= 1.01 && e.touches.length === 1 ? e.touches[0].clientX : null;
  };
  const onTouchEnd = (e) => {
    if (touch.current == null) return;
    const dx = e.changedTouches[0].clientX - touch.current;
    if (Math.abs(dx) > SWIPE_MIN_PX) onSwipe(dx < 0 ? 1 : -1);
    touch.current = null;
  };

  return (
    <TransformWrapper minScale={1} maxScale={8} centerOnInit onTransformed={(_, s) => { scale.current = s.scale; }}>
      {({ zoomIn, zoomOut, resetTransform }) => (
        <>
          <div className="viewer-tools">
            <button className="icon-btn" onClick={() => zoomIn()} aria-label="Zoom in"><IconZoomIn /></button>
            <button className="icon-btn" onClick={() => zoomOut()} aria-label="Zoom out"><IconZoomOut /></button>
            <button className="icon-btn" onClick={() => { setRotation((r) => r + 90); resetTransform(); }} aria-label="Rotate"><IconRotate /></button>
          </div>
          <div className="viewer-stage" onTouchStart={onTouchStart} onTouchEnd={onTouchEnd}>
            <TransformComponent wrapperClass="zoom-wrapper" contentClass="zoom-content">
              {/* the cached thumbnail shows at once, the full image replaces it once loaded */}
              {!loaded && item.thumb && (
                <img className="viewer-img viewer-placeholder" src={thumbUrl(item.thumb, 640)} alt=""
                  style={{ transform: `rotate(${rotation}deg)` }} />
              )}
              <img className="viewer-img" src={src} alt={item.title}
                onLoad={() => setLoaded(true)} onError={onError}
                style={{ transform: `rotate(${rotation}deg)`, display: loaded ? 'block' : 'none' }} />
            </TransformComponent>
          </div>
        </>
      )}
    </TransformWrapper>
  );
}

const FITS_EXTS = ['fits', 'fit'];
const TEXT_EXTS = ['txt', 'log', 'json'];

// A browser can't display a FITS: shows the preview rendered by the backend, the file summary if it fails
function FitsStage({ item, onSwipe, onDownload }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <FileStage item={item} onDownload={onDownload} />;
  return <ImageStage item={item} src={thumbUrl(item.thumb, 1280)} onSwipe={onSwipe} onError={() => setFailed(true)} />;
}

function TextStage({ item, section }) {
  const [text, setText] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => {
    setText(null);
    fetchText(section, item.paths[0]).then(setText).catch((e) => setError(e.message));
  }, [item, section]);
  return (
    <div className="viewer-text">
      {error ? <p className="error-text">{error}</p> : <pre>{text ?? 'Loading…'}</pre>}
    </div>
  );
}

function FileStage({ item, onDownload }) {
  return (
    <div className="viewer-file">
      <FileIcon ext={item.ext} size={64} />
      <p className="viewer-file-name">{item.name}</p>
      <p className="muted">{formatBytes(item.size)}</p>
      {item.ext === 'ser' && <p className="muted">Raw scan video, for reprocessing in INTI or JSol&apos;Ex.</p>}
      {(item.ext === 'fits' || item.ext === 'fit') && <p className="muted">Scientific data, open it with a FITS viewer.</p>}
      <button className="btn btn-primary" onClick={() => onDownload(item.paths)}><IconDownload /> Download</button>
    </div>
  );
}

export default function Viewer({ items, index, section, onNavigate, onClose, onDownload }) {
  const item = items[index];
  const go = (delta) => {
    const next = index + delta;
    if (next >= 0 && next < items.length) onNavigate(items[next].key);
  };

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      else if (e.key === 'ArrowRight') go(1);
      else if (e.key === 'ArrowLeft') go(-1);
    };
    window.addEventListener('keydown', onKey);
    document.body.classList.add('no-scroll');
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.classList.remove('no-scroll');
    };
  });

  if (!item) return null;
  const fits = item.kind === 'file' && FITS_EXTS.includes(item.ext) && Boolean(item.thumb);

  return (
    <div className="viewer" role="dialog" aria-modal="true" aria-label={item.title}>
      <div className="viewer-header">
        <div className="viewer-title">
          <strong>{item.title}</strong>
          <span className="muted">{index + 1} / {items.length} · {item.subtitle}{fits && ' · preview'}</span>
        </div>
        <div className="viewer-actions">
          {item.kind === 'image'
            ? item.entries.map((e) => (
              <button key={e.path} className="btn btn-small" onClick={() => onDownload([e.path])}>
                <IconDownload size={16} /> {e.name.split('.').pop().toUpperCase()}
              </button>
            ))
            : <button className="btn btn-small" onClick={() => onDownload(item.paths)}><IconDownload size={16} /> Download</button>}
          <button className="icon-btn" onClick={onClose} aria-label="Close"><IconClose /></button>
        </div>
      </div>

      <div className="viewer-body">
        {item.kind === 'image' && (
          <ImageStage key={item.key} item={item} src={fileUrl(section, item.display.path)} onSwipe={go} />
        )}
        {fits && <FitsStage key={item.key} item={item} onSwipe={go} onDownload={onDownload} />}
        {item.kind === 'file' && TEXT_EXTS.includes(item.ext) && <TextStage item={item} section={section} />}
        {item.kind === 'file' && !fits && !TEXT_EXTS.includes(item.ext) && <FileStage item={item} onDownload={onDownload} />}

        {index > 0 && (
          <button className="viewer-nav viewer-prev" onClick={() => go(-1)} aria-label="Previous"><IconChevronLeft size={28} /></button>
        )}
        {index < items.length - 1 && (
          <button className="viewer-nav viewer-next" onClick={() => go(1)} aria-label="Next"><IconChevronRight size={28} /></button>
        )}
      </div>
    </div>
  );
}
