import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getScanFolders, downloadDateScan, downloadMultipleDateScans, deleteDateScans } from '../api';
import Layout from './Layout';
import { config, devLog } from '../config';

// composant pour afficher la liste des scans d'une date

const DateView = () => {
  const { dateFolder } = useParams();
  const [scanFolders, setScanFolders] = useState([]);
  const [selectedFolders, setSelectedFolders] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('');

  useEffect(() => {
    getScanFolders(dateFolder).then((items) => {
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setScanFolders(sortedItems);
    });
  }, [dateFolder]);

  const handleSelectFolder = (folder) => {
    setSelectedFolders(prev => {
      if (prev.includes(folder.name)) {
        return prev.filter(f => f !== folder.name);
      }
      return [...prev, folder.name];
    });
  };

  const handleSelectAll = () => {
    if (selectedFolders.length === scanFolders.length) {
      setSelectedFolders([]);
    } else {
      setSelectedFolders(scanFolders.map(folder => folder.name));
    }
  };

  const downloadSelected = async () => {
    if (selectedFolders.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
      if (selectedFolders.length === 1) {
        await downloadDateScan(dateFolder, selectedFolders[0]);
      } else {
        await downloadMultipleDateScans(dateFolder, selectedFolders);
      }
      
      setDownloadStatus('Download started!');
      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Error downloading folders:', error);
      setDownloadStatus('Download failed. Please try again.');
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsLoading(false);
      setDownloadStatus('');
    }
  };

  const downloadAll = async () => {
    if (scanFolders.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
      await downloadMultipleDateScans(dateFolder, scanFolders.map(folder => folder.name));
      setDownloadStatus('Download started!');
      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Error downloading all folders:', error);
      setDownloadStatus('Download failed. Please try again.');
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
    setDeleteStatus('Deleting scans...');

    try {
      await deleteDateScans(dateFolder, selectedFolders);
      setDeleteStatus('Scans deleted successfully!');
      
      // Rafraîchir la liste des dossiers
      const items = await getScanFolders(dateFolder);
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setScanFolders(sortedItems);
      
      // Réinitialiser la sélection
      setSelectedFolders([]);
      
      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Error deleting scans:', error);
      setDeleteStatus('Failed to delete scans. Please try again.');
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsDeleting(false);
      setDeleteStatus('');
    }
  };

  const scanDate = (dateFolder.split('-')[0]).replaceAll("_", "/");

  // date time format
  const formatScanDateTime = (folderName) => {
    try {

      const [firstPart, timePart] = folderName.split('-');
      
      // date
      const dateParts = firstPart.split('_');
      const [year, month, day] = dateParts.slice(-3); 
      const formattedDate = `${year}/${month}/${day}`;
      
      // heure
      const [hours, minutes, seconds] = timePart.split('_');
      const formattedTime = `${hours}:${minutes}:${seconds}`;
      
      return `${formattedDate} - ${formattedTime}`;
    } catch (error) {
      console.error('Error formatting date time:', error);
      return folderName; 
    }
  };

  return (
    <Layout title={`Scan`} subtitle={`Date: ${scanDate}`} backLink={`/scans`}>
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
            <p>Are you sure you want to delete {selectedFolders.length} scan(s)?</p>
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
          Download All ({scanFolders.length})
        </button>
        <button 
          onClick={handleSelectAll}
          className="action-button"
        >
          {selectedFolders.length === scanFolders.length ? 'Unselect All' : 'Select All'}
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
        {scanFolders.map(folder => (
          <div key={folder.name} className="folder-item">
            <div className="folder-checkbox">
              <input
                type="checkbox"
                checked={selectedFolders.includes(folder.name)}
                onChange={() => handleSelectFolder(folder)}
              />
            </div>
            <Link to={`/date/${dateFolder}/scan/${folder.name}`} className="folder-link">
              <div className="folder-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M19.5 21a3 3 0 003-3v-4.5a3 3 0 00-3-3h-15a3 3 0 00-3 3V18a3 3 0 003 3h15zM1.5 10.146V6a3 3 0 013-3h5.379a2.25 2.25 0 011.59.659l2.122 2.121c.14.141.331.22.53.22H19.5a3 3 0 013 3v1.146A4.483 4.483 0 0019.5 9h-15a4.483 4.483 0 00-3 1.146z" />
                </svg>
              </div>
              <p>{formatScanDateTime(folder.name)}</p>
            </Link>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default DateView;