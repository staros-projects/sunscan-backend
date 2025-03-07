import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

import Layout from './Layout';

// composant pour afficher la liste des dossiers par dates (racine du dossier storaage/scans)

const Dashboard = () => {
  const [dateFolders, setDateFolders] = useState([]);

  return (
    <Layout title="SUNSCAN Gallery">
      <div className="folder-grid">
        <Link to={`/scans`} key='scans' className="folder-item">
          <div className="folder-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path d="M19.5 21a3 3 0 003-3v-4.5a3 3 0 00-3-3h-15a3 3 0 00-3 3V18a3 3 0 003 3h15zM1.5 10.146V6a3 3 0 013-3h5.379a2.25 2.25 0 011.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 013 3v1.146A4.483 4.483 0 0019.5 9h-15a4.483 4.483 0 00-3 1.146z" />
            </svg>
          </div>
          <p>SCANS</p>
        </Link>

        <Link to={`/snapshots`} key='snapshots' className="folder-item">
          <div className="folder-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 9a3.75 3.75 0 100 7.5A3.75 3.75 0 0012 9z" />
              <path fillRule="evenodd" d="M9.344 3.071a49.52 49.52 0 015.312 0c.967.052 1.83.585 2.332 1.39l.821 1.317c.24.383.645.643 1.11.71.386.054.77.113 1.152.177 1.432.239 2.429 1.493 2.429 2.909V18a3 3 0 01-3 3h-15a3 3 0 01-3-3V9.574c0-1.416.997-2.67 2.429-2.909.382-.064.766-.123 1.151-.178a1.56 1.56 0 001.11-.71l.822-1.315a2.942 2.942 0 012.332-1.39zM6.75 12.75a5.25 5.25 0 1110.5 0 5.25 5.25 0 01-10.5 0zm12-1.5a.75.75 0 100-1.5.75.75 0 000 1.5z" clipRule="evenodd" />
            </svg>
          </div>
          <p>SNAPSHOTS</p>
        </Link>

        <Link to={`/stacking`} key='stacking' className="folder-item">
          <div className="folder-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path fillRule="evenodd" d="M5.625 1.5H9a3.75 3.75 0 013.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 013.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 01-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875zM9.75 17.25a.75.75 0 00-1.5 0v2.25a.75.75 0 001.5 0v-2.25zm3.75-1.5a.75.75 0 00-1.5 0v3.75a.75.75 0 001.5 0v-3.75zm3.75-3a.75.75 0 00-1.5 0v6.75a.75.75 0 001.5 0v-6.75z" />
            </svg>
          </div>
          <p>STACKING</p>
        </Link>

        <Link to={`/animations`} key='animations' className="folder-item">
          <div className="folder-icon">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
              <path fillRule="evenodd" d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 19.991c-1.25.687-2.779-.217-2.779-1.643V5.653z" />
            </svg>
          </div>
          <p>ANIMATIONS</p>
        </Link>
      </div>
    </Layout>
  );
};

export default Dashboard;