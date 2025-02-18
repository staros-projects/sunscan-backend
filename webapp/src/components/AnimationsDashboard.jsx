import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { getAnimationFolders, downloadAnimationFile, downloadMultipleAnimationFolders, deleteAnimationFolders } from '../api';
import Layout from './Layout';
import { devLog } from '../config';
import './Dashboard.css';

const AnimationsDashboard = () => {
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('');

  useEffect(() => {
    getAnimationFolders().then((items) => {
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
      await downloadMultipleAnimationFolders(selectedFiles);
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
      await deleteAnimationFolders(selectedFiles);
      setDeleteStatus('Folders deleted successfully!');
      
      // Rafraîchir la liste des dossiers
      const items = await getAnimationFolders();
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

  // set date and time format
  const formatDateTime = (folderName) => {
    try {
      const [datePart, timePart] = folderName.split('_');
      
      const formattedDate = datePart.replaceAll('-', '/');
      
      const formattedTime = timePart.replaceAll('-', ':');
      
      return `${formattedDate} - ${formattedTime}`;
    } catch (error) {
      console.error('Error formatting date time:', error);
      return folderName;
    }
  };

  return (
    <Layout title={`Animations`} subtitle={`All folders`} backLink={`/`}>
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
              to={`/animations/${file.name}/${file.name}`}
              className="folder-link"
              onClick={(e) => {
                if (e.target.tagName === 'INPUT') {
                  e.preventDefault();
                }
              }}
            >
              <div className="folder-icon">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" d="M4.5 5.653c0-1.426 1.529-2.33 2.779-1.643l11.54 6.348c1.295.712 1.295 2.573 0 3.285L7.28 19.991c-1.25.687-2.779-.217-2.779-1.643V5.653z" />
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

export default AnimationsDashboard; 