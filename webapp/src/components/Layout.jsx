import React from 'react';
import { Link } from 'react-router-dom';

// structure de base de la gallery

const Layout = ({ children, title, backLink }) => {
  return (
    <div className="dashboard">
      <header className="dashboard-header">
        {backLink && (
          <Link to={backLink} className="back-button">
            &#8592; Back
          </Link>
        )}
        <h1>{title}</h1>
      </header>
      <main className="dashboard-main">
        {children}
      </main>
    </div>
  );
};

export default Layout;