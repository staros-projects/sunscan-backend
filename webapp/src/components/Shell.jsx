import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import logo from '../assets/sunscan_logo.png';
import { getStats } from '../api';
import { formatBytes, parseSize } from '../lib/format';
import { IconBattery } from './Icons';

const TABS = [
  ['scans', 'Scans'],
  ['stacking', 'Stacking'],
  ['animations', 'Animations'],
  ['snapshots', 'Snapshots'],
];

const LOW_STORAGE_BYTES = 5 * 1024 ** 3;

const StatsContext = createContext({ stats: null, refreshStats: () => {} });
export const useStats = () => useContext(StatsContext);

export function StatsProvider({ children }) {
  const [stats, setStats] = useState(null);
  const refreshStats = useCallback(() => {
    getStats().then(setStats).catch(() => setStats(null));
  }, []);
  useEffect(refreshStats, [refreshStats]);
  return <StatsContext.Provider value={{ stats, refreshStats }}>{children}</StatsContext.Provider>;
}

function StorageMeter({ stats }) {
  const total = parseSize(stats.total);
  const free = stats.free_raw;
  const used = total != null ? total - free : null;
  const ratio = total ? Math.min(1, used / total) : 0;
  const low = free < LOW_STORAGE_BYTES;
  return (
    <div className={`meter ${low ? 'meter-low' : ''}`} title={`${stats.used} used of ${stats.total}`}>
      <div className="meter-bar"><div style={{ width: `${ratio * 100}%` }} /></div>
      <span>{formatBytes(free)} free</span>
    </div>
  );
}

export function Shell({ crumbs, children }) {
  const { stats } = useStats();
  const low = stats && stats.free_raw < LOW_STORAGE_BYTES;

  return (
    <div className="shell">
      <header className="topbar">
        <Link to="/scans" className="brand" aria-label="SUNSCAN gallery home">
          <img src={logo} alt="" />
          <span>SUNSCAN</span>
        </Link>
        <nav className="tabs" aria-label="Sections">
          {TABS.map(([id, label]) => (
            <NavLink key={id} to={`/${id}`} className={({ isActive }) => `tab ${isActive ? 'tab-active' : ''}`}>
              {label}
            </NavLink>
          ))}
        </nav>
        {stats && (
          <div className="status">
            <StorageMeter stats={stats} />
            {typeof stats.battery === 'number' && (
              <span className={`battery ${stats.battery < 20 && !stats.battery_power_plugged ? 'battery-low' : ''}`}
                title={stats.battery_power_plugged ? 'Charging' : 'On battery'}>
                <IconBattery size={18} charging={stats.battery_power_plugged} />
                {Math.round(stats.battery)}%
              </span>
            )}
          </div>
        )}
      </header>

      {low && (
        <div className="banner banner-warning">
          Storage almost full: {formatBytes(stats.free_raw)} left. Download then delete old scans before the next session.
        </div>
      )}

      {crumbs && crumbs.length > 1 && (
        <nav className="crumbs" aria-label="Breadcrumb">
          {crumbs.map((c, i) => (
            <span key={c.to}>
              {i > 0 && <span className="crumb-sep" aria-hidden="true">/</span>}
              {i < crumbs.length - 1 ? <Link to={c.to}>{c.label}</Link> : <span aria-current="page">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}

      <main className="content">{children}</main>

      {stats && (
        <footer className="footer">
          Camera {stats.camera} · Backend v{stats.backend_api_version}
        </footer>
      )}
    </div>
  );
}
