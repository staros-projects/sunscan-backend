import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getStackingFolders, downloadStackingFile, downloadMultipleStackingFolders, deleteStackingFolders } from '../api';
import Layout from './Layout';
import { devLog } from '../config';
import './Dashboard.css';

const StackingDashboard = () => {
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('');

  useEffect(() => {
    getStackingFolders().then((items) => {
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setFiles(sortedItems);
    });
  }, []);

  const handleSelectFile = (file) => {
    setSelectedFiles(prev => {
      if (prev.includes(file.name)) {
        return prev.filter(f => f !== file.name);
      }
      return [...prev, file.name];
    });
  };

  const handleSelectAll = () => {
    if (selectedFiles.length === files.length) {
      setSelectedFiles([]);
    } else {
      setSelectedFiles(files.map(file => file.name));
    }
  };

  const downloadSelected = async () => {
    if (selectedFiles.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
        await downloadMultipleStackingFolders(selectedFiles);

      setDownloadStatus('Download started!');
      await new Promise(resolve => setTimeout(resolve, 1000));
    } catch (error) {
      console.error('Error downloading files:', error);
      setDownloadStatus('Download failed. Please try again.');
      await new Promise(resolve => setTimeout(resolve, 2000));
    } finally {
      setIsLoading(false);
      setDownloadStatus('');
    }
  };

  const handleDelete = async () => {
    if (selectedFiles.length === 0) return;
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    setShowDeleteConfirm(false);
    setIsDeleting(true);
    setDeleteStatus('Deleting folders...');

    try {
      await deleteStackingFolders(selectedFiles);
      setDeleteStatus('Folders deleted successfully!');
      
      // Rafraîchir la liste des dossiers
      const items = await getStackingFolders();
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setFiles(sortedItems);
      setSelectedFiles([]);
      
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

  // date et heure
  const formatDateTime = (folderName) => {
    try {
      const [datePart, timePart] = folderName.split('_');
      
      // date 
      const formattedDate = datePart.replaceAll('-', '/');
      
      // heure 
      const formattedTime = timePart.replaceAll('-', ':');
      
      return `${formattedDate} - ${formattedTime}`;
    } catch (error) {
      console.error('Error formatting date time:', error);
      return folderName;
    }
  };

  return (
    <Layout title={`Stacked`} subtitle={`All stacked folders`} backLink={`/`}>
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
            <p>Are you sure you want to delete {selectedFiles.length} folder(s)?</p>
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
          disabled={selectedFiles.length === 0 || isLoading}
          className="action-button"
        >
          Download Selected ({selectedFiles.length})
        </button>
        <button 
          onClick={handleSelectAll}
          className="action-button"
        >
          {selectedFiles.length === files.length ? 'Unselect All' : 'Select All'}
        </button>
        <button 
          onClick={handleDelete}
          disabled={selectedFiles.length === 0 || isLoading || isDeleting}
          className="action-button delete-button"
        >
          Delete Selected ({selectedFiles.length})
        </button>
      </div>

      <div className="folder-grid">
        {files.map(file => (
          <div key={file.name} className="folder-item">
            <div className="folder-checkbox">
              <input
                type="checkbox"
                checked={selectedFiles.includes(file.name)}
                onChange={() => handleSelectFile(file)}
              />
            </div>
            <Link 
              to={`/stacking/${file.name}/${file.name}`}
              className="folder-link"
              onClick={(e) => {
                if (e.target.tagName === 'INPUT') {
                  e.preventDefault();
                }
              }}
            >
              <div className="folder-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" d="M5.625 1.5H9a3.75 3.75 0 013.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 013.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 01-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875zM9.75 17.25a.75.75 0 00-1.5 0v2.25a.75.75 0 001.5 0v-2.25zm3.75-1.5a.75.75 0 00-1.5 0v3.75a.75.75 0 001.5 0v-3.75zm3.75-3a.75.75 0 00-1.5 0v6.75a.75.75 0 001.5 0v-6.75z" />
                </svg>
              </div>
              <p>{formatDateTime(file.name)}</p>
            </Link>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default StackingDashboard; 