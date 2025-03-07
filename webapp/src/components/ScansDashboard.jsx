import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getDateFolders, downloadScan, downloadMultipleScans, deleteScanFolders } from '../api';
import Layout from './Layout';
import { config, devLog } from '../config';
import './Dashboard.css';

// composant pour afficher la liste des dossiers par dates (racine du dossier storaage/scans)

const ScansDashboard = () => {
  const [dateFolders, setDateFolders] = useState([]);
  const [selectedFolders, setSelectedFolders] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('');

  useEffect(() => {
    getDateFolders().then((items)=>{
      // Sort by the name field
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setDateFolders(sortedItems);
    });
  }, []);

  const handleSelectFolder = (folder) => {
    setSelectedFolders(prev => {
      if (prev.includes(folder.name)) {
        return prev.filter(f => f !== folder.name);
      }
      return [...prev, folder.name];
    });
  };

  const handleSelectAll = () => {
    if (selectedFolders.length === dateFolders.length) {
      setSelectedFolders([]);
    } else {
      setSelectedFolders(dateFolders.map(folder => folder.name));
    }
  };

  const downloadSelected = async () => {
    if (selectedFolders.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
      if (selectedFolders.length === 1) {
        await downloadScan(selectedFolders[0]);
        await new Promise(resolve => setTimeout(resolve, 1000));
      } else {
        // On attend que le téléchargement commence réellement
        await downloadMultipleScans(selectedFolders);
      }
      setDownloadStatus('Download started!');
    } catch (error) {
      console.error('Error downloading folders:', error);
      setDownloadStatus('Download failed. Please try again.');
      // si erreur
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsLoading(false);
      setDownloadStatus('');
    }
  };

  const downloadAll = async () => {
    if (dateFolders.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
      // download start
      await downloadMultipleScans(dateFolders.map(folder => folder.name));
      setDownloadStatus('Download started!');
    } catch (error) {
      console.error('Error downloading all folders:', error);
      setDownloadStatus('Download failed. Please try again.');
      // erreur
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsLoading(false);
      setDownloadStatus('');
    }
  };

  const handleDelete = async () => {
    if (selectedFolders.length === 0) return;
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    setShowDeleteConfirm(false);
    setIsDeleting(true);
    setDeleteStatus('Deleting folders...');

    try {
      await deleteScanFolders(selectedFolders);
      setDeleteStatus('Folders deleted successfully!');
      
      // Rafraîchir la liste des dossiers
      const items = await getDateFolders();
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setDateFolders(sortedItems);
      
      // Réinitialiser la sélection
      setSelectedFolders([]);
      
      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Error deleting folders:', error);
      setDeleteStatus('Failed to delete folders. Please try again.');
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsDeleting(false);
      setDeleteStatus('');
    }
  };

  // date
  const formatDate = (folderName) => {
    try {
      const [year, month, day] = folderName.split('_');
      return `${year}/${month}/${day}`;
    } catch (error) {
      console.error('Error formatting date:', error);
      return folderName;
    }
  };

  return (
    <Layout title={`Scans`} subtitle={`All scans`} backLink={`/`}>
      {(isLoading && downloadStatus) || (isDeleting && deleteStatus) ? (
        <div className="waiting-popup">
          <div className="waiting-message">
            <div className="loading-spinner"></div>
            <p>{downloadStatus || deleteStatus}</p>
          </div>
        </div>
      ) : null}

      {showDeleteConfirm && (
        <div className="confirm-popup">
          <div className="confirm-message">
            <h3>Confirm Deletion</h3>
            <p>Are you sure you want to delete {selectedFolders.length} folder(s)?</p>
            <p className="warning">This action cannot be undone!</p>
            <div className="confirm-actions">
              <button 
                onClick={() => setShowDeleteConfirm(false)}
                className="action-button"
              >
                Cancel
              </button>
              <button 
                onClick={confirmDelete}
                className="action-button delete-button"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="dashboard-actions">
        <button 
          onClick={downloadSelected} 
          disabled={selectedFolders.length === 0 || isLoading}
          className="action-button"
        >
          Download Selected ({selectedFolders.length})
        </button>
        <button 
          onClick={downloadAll}
          disabled={isLoading}
          className="action-button"
        >
          Download All ({dateFolders.length})
        </button>
        <button 
          onClick={handleSelectAll}
          className="action-button"
        >
          {selectedFolders.length === dateFolders.length ? 'Unselect All' : 'Select All'}
        </button>
        <button 
          onClick={handleDelete}
          disabled={selectedFolders.length === 0 || isLoading || isDeleting}
          className="action-button delete-button"
        >
          Delete Selected ({selectedFolders.length})
        </button>
      </div>

      <div className="folder-grid">
        {dateFolders.map(folder => (
          <div key={folder.name} className="folder-item">
            <div className="folder-checkbox">
              <input
                type="checkbox"
                checked={selectedFolders.includes(folder.name)}
                onChange={() => handleSelectFolder(folder)}
              />
            </div>
            <Link to={`/date/${folder.name}`} className="folder-link">
              <div className="folder-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.5 21a3 3 0 003-3v-4.5a3 3 0 00-3-3h-15a3 3 0 00-3 3V18a3 3 0 003 3h15zM1.5 10.146V6a3 3 0 013-3h5.379a2.25 2.25 0 011.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 013 3v1.146A4.483 4.483 0 0019.5 9h-15a4.483 4.483 0 00-3 1.146z" />
                </svg>
              </div>
              <p>{formatDate(folder.name)}</p>
            </Link>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default ScansDashboard;