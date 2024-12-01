import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import {  downloadSnapshot, getSnapshots, deleteAllSnapshots } from '../api';
import Layout from './Layout';

// composant pour afficher la liste des dossiers par dates (racine du dossier storaage/scans)

const SnapshotsDashboard = () => {
  const [snapshots, setSnapshots] = useState([]);


  useEffect(() => {
    refreshSnapshots();
  }, []);

  const refreshSnapshots = () => {
    getSnapshots().then((items) => {
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setSnapshots(sortedItems);
    });
  };

  
  const handleDeleteAll = () => {
    if (window.confirm('Are you sure you want to delete all snapshots? This action cannot be undone.')) {
      deleteAllSnapshots()
        .then(() => {
          alert('All snapshots have been successfully deleted.');
          refreshSnapshots(); // Refresh the list after deletion
        })
        .catch((error) => {
          console.error('Error deleting snapshots:', error);
          alert('An error occurred while deleting snapshots.');
        });
    }
  };

  return (
    <Layout title="SUNSCAN Gallery : snapshots" backLink={`/`}>
      <div style={{ marginBottom: '20px', textAlign: 'right' }}>
        <button onClick={handleDeleteAll} className="delete-all-button" style={{ padding: '10px 15px', background: 'red', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>
          Delete All Snapshots
        </button>
      </div>
      <div className="folder-grid">
        {snapshots.map(snapshot => (
          <Link onClick={() => downloadSnapshot(snapshot.name)} key={snapshot.name} className="folder-item">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="file-icon">
          <path d="M12 9a3.75 3.75 0 100 7.5A3.75 3.75 0 0012 9z" />
          <path fillRule="evenodd" d="M9.344 3.071a49.52 49.52 0 015.312 0c.967.052 1.83.585 2.332 1.39l.821 1.317c.24.383.645.643 1.11.71.386.054.77.113 1.152.177 1.432.239 2.429 1.493 2.429 2.909V18a3 3 0 01-3 3h-15a3 3 0 01-3-3V9.574c0-1.416.997-2.67 2.429-2.909.382-.064.766-.123 1.151-.178a1.56 1.56 0 001.11-.71l.822-1.315a2.942 2.942 0 012.332-1.39zM6.75 12.75a5.25 5.25 0 1110.5 0 5.25 5.25 0 01-10.5 0zm12-1.5a.75.75 0 100-1.5.75.75 0 000 1.5z" clipRule="evenodd" />
        </svg>
            <p style={{fontSize:'0.8em'}}>{snapshot.name}</p>
          </Link>
        ))}
      </div>
    </Layout>
  );
};

export default SnapshotsDashboard;