import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getScanFolders } from '../api';
import Layout from './Layout';

// composant pour afficher la liste des scans d'une date

const DateView = () => {
  const { dateFolder } = useParams();
  const [scanFolders, setScanFolders] = useState([]);

  useEffect(() => {
    getScanFolders(dateFolder).then(setScanFolders);
  }, [dateFolder]);

  return (
    <Layout title={`Date: ${dateFolder}`} backLink="/">
      <div className="folder-grid">
        {scanFolders.map(scan => (
          <Link to={`/date/${dateFolder}/scan/${scan.name}`} key={scan.name} className="folder-item">
            <div className="folder-icon">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M19.5 21a3 3 0 003-3v-4.5a3 3 0 00-3-3h-15a3 3 0 00-3 3V18a3 3 0 003 3h15zM1.5 10.146V6a3 3 0 013-3h5.379a2.25 2.25 0 011.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 013 3v1.146A4.483 4.483 0 0019.5 9h-15a4.483 4.483 0 00-3 1.146z" />
              </svg>
            </div>
            <p>{scan.name}</p>
          </Link>
        ))}
      </div>
    </Layout>
  );
};

export default DateView;