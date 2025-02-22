import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import logo from '../assets/sunscan_logo.png';
import { getSunscanStats } from '../api';

// structure de base de la gallery

const Layout = ({ children, title, backLink, subtitle }) => {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const statsData = await getSunscanStats();
        setStats(statsData);
      } catch (error) {
        console.error('Error fetching stats:', error);
      }
    };
    fetchStats();
  }, []);

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <div className="header-content">
          <div className="header-left">
            {backLink && (
              <Link to={backLink} className="back-button">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" d="M11.03 3.97a.75.75 0 010 1.06l-6.22 6.22H21a.75.75 0 010 1.5H4.81l6.22 6.22a.75.75 0 11-1.06 1.06l-7.5-7.5a.75.75 0 010-1.06l7.5-7.5a.75.75 0 011.06 0z" clipRule="evenodd" />
                </svg>
                Back
              </Link>
            )}
          </div>
          <div className="header-center">
            <h1 className="header-title">{title}</h1>
            {subtitle && <p className="header-subtitle">{subtitle}</p>}
          </div>
          <div className="header-right">
            <Link to="/" className="header-logo-link">
              <img src={logo} alt="StarOS Logo" className="header-logo" />
            </Link>
          </div>
        </div>
      </header>
      <main className="dashboard-main">
        {children}
      </main>
      {stats && (
        <footer className="stats-footer">
          <div className="stats-container">
            <div className="stat-item">
              <span>Storage: {stats.used} / {stats.total} (Free: {stats.free})</span>
            </div>
            <div className="stat-item">
              <span>Camera: {stats.camera}</span>
            </div>
            <div className="stat-item">
              <span>Server version: v{stats.backend_api_version}</span>
            </div>
          </div>
        </footer>
      )}
    </div>
  );
};

export default Layout;