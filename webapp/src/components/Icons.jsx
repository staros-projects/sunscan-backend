// Stroke icons (24px grid), inherit the text color
const Icon = ({ children, size = 20, ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {children}
  </svg>
);

export const IconFolder = (p) => <Icon {...p}><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /></Icon>;
export const IconDownload = (p) => <Icon {...p}><path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14" /></Icon>;
export const IconTrash = (p) => <Icon {...p}><path d="M4 7h16M10 11v6m4-6v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></Icon>;
export const IconCheck = (p) => <Icon {...p}><path d="m5 12 5 5 9-10" /></Icon>;
export const IconClose = (p) => <Icon {...p}><path d="M6 6l12 12M18 6 6 18" /></Icon>;
export const IconChevronLeft = (p) => <Icon {...p}><path d="m15 5-7 7 7 7" /></Icon>;
export const IconChevronRight = (p) => <Icon {...p}><path d="m9 5 7 7-7 7" /></Icon>;
export const IconZoomIn = (p) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="M11 8v6M8 11h6m4 7 3 3" /></Icon>;
export const IconZoomOut = (p) => <Icon {...p}><circle cx="11" cy="11" r="7" /><path d="M8 11h6m4 7 3 3" /></Icon>;
export const IconRotate = (p) => <Icon {...p}><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" /></Icon>;
export const IconFile = (p) => <Icon {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5" /></Icon>;
export const IconText = (p) => <Icon {...p}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" /><path d="M14 3v5h5M9 13h6M9 17h4" /></Icon>;
export const IconFilm = (p) => <Icon {...p}><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M7 5v14M17 5v14M3 9h4m10 0h4M3 15h4m10 0h4" /></Icon>;
export const IconData = (p) => <Icon {...p}><ellipse cx="12" cy="6" rx="7" ry="3" /><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" /></Icon>;
export const IconSun = (p) => <Icon {...p}><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>;
export const IconBattery = ({ charging, ...p }) => (
  <Icon {...p}>
    <rect x="2" y="7" width="17" height="10" rx="2" /><path d="M22 11v2" />
    {charging && <path d="m11 8-2 4h3l-2 4" />}
  </Icon>
);
export const IconSelect = (p) => <Icon {...p}><rect x="4" y="4" width="16" height="16" rx="3" /><path d="m8 12 3 3 5-6" /></Icon>;
export const IconRefresh = (p) => <Icon {...p}><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5" /></Icon>;

export function FileIcon({ ext, ...p }) {
  if (ext === 'ser') return <IconFilm {...p} />;
  if (ext === 'fits' || ext === 'fit') return <IconData {...p} />;
  if (ext === 'txt' || ext === 'log' || ext === 'json') return <IconText {...p} />;
  return <IconFile {...p} />;
}
