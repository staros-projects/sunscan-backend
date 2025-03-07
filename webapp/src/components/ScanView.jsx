import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getImagesInScan, downloadImage, downloadMultipleScanImages, deleteScanImages, getScanLog } from '../api';
import Layout from './Layout';
import { config, devLog } from '../config';

//  types d'images
export const groupFilesByType = (files) => {
  const groups = {};

  files.forEach(file => {
    const ext = file.name.split('.').pop().toLowerCase(); 
    if (!groups[ext]) {
      groups[ext] = []; 
    }
    groups[ext].push(file);
  });

  Object.keys(groups).forEach(type => {
    groups[type].sort((a, b) => b.name.localeCompare(a.name)); 
  });

  return groups; 
};

// composant pour afficher les images d'un scan


const ScanView = () => {
  const { dateFolder, scanFolder } = useParams();
  const [files, setFiles] = useState([]);
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteStatus, setDeleteStatus] = useState('');
  const [imageSize, setImageSize] = useState('normal'); // 'tiny', 'small', 'normal', 'large', 'huge'
  const [showLogPopup, setShowLogPopup] = useState(false);
  const [logContent, setLogContent] = useState('');
  const [isLoadingLog, setIsLoadingLog] = useState(false);

  useEffect(() => {
    getImagesInScan(dateFolder, scanFolder).then(setFiles);
  }, [dateFolder, scanFolder]);

  const isImage = (fileName) => {
    const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp'];
    const extension = fileName.split('.').pop().toLowerCase();
    return imageExtensions.includes(extension);
  };


  const getFileIcon = (fileName) => {
  const extension = fileName.split('.').pop().toLowerCase();
  switch (extension) {
    case 'txt':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="file-icon">
          <path fillRule="evenodd" d="M5.625 1.5c-1.036 0-1.875.84-1.875 1.875v17.25c0 1.035.84 1.875 1.875 1.875h12.75c1.035 0 1.875-.84 1.875-1.875V12.75a3.75 3.75 0 00-3.75-3.75h-1.875a1.875 1.875 0 01-1.875-1.875V5.25A3.75 3.75 0 0012 1.5H5.625zM7.5 15a.75.75 0 01.75-.75h7.5a.75.75 0 010 1.5h-7.5A.75.75 0 017.5 15zm.75 2.25a.75.75 0 000 1.5H12a.75.75 0 000-1.5H8.25z" clipRule="evenodd" />
          <path d="M12.971 1.816A5.23 5.23 0 0114.25 5.25v1.875c0 .207.168.375.375.375H16.5a5.23 5.23 0 013.434 1.279 9.768 9.768 0 00-6.963-6.963z" />
        </svg>
      );
    case 'ser':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="file-icon">
          <path d="M4.5 4.5a3 3 0 00-3 3v9a3 3 0 003 3h8.25a3 3 0 003-3v-9a3 3 0 00-3-3H4.5zM19.94 18.75l-2.69-2.69V7.94l2.69-2.69c.944-.945 2.56-.276 2.56 1.06v11.38c0 1.336-1.616 2.005-2.56 1.06z" />
        </svg>
      );
    case 'fits':
      return (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="file-icon">
          <path d="M12 9a3.75 3.75 0 100 7.5A3.75 3.75 0 0012 9z" />
          <path fillRule="evenodd" d="M9.344 3.071a49.52 49.52 0 015.312 0c.967.052 1.83.585 2.332 1.39l.821 1.317c.24.383.645.643 1.11.71.386.054.77.113 1.152.177 1.432.239 2.429 1.493 2.429 2.909V18a3 3 0 01-3 3h-15a3 3 0 01-3-3V9.574c0-1.416.997-2.67 2.429-2.909.382-.064.766-.123 1.151-.178a1.56 1.56 0 001.11-.71l.822-1.315a2.942 2.942 0 012.332-1.39zM6.75 12.75a5.25 5.25 0 1110.5 0 5.25 5.25 0 01-10.5 0zm12-1.5a.75.75 0 100-1.5.75.75 0 000 1.5z" clipRule="evenodd" />
        </svg>
      );
    default:
      return (
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="file-icon">
          <path fillRule="evenodd" d="M5.625 1.5H9a3.75 3.75 0 013.75 3.75v1.875c0 1.036.84 1.875 1.875 1.875H16.5a3.75 3.75 0 013.75 3.75v7.875c0 1.035-.84 1.875-1.875 1.875H5.625a1.875 1.875 0 01-1.875-1.875V3.375c0-1.036.84-1.875 1.875-1.875zm5.845 17.03a.75.75 0 001.06 0l3-3a.75.75 0 10-1.06-1.06l-1.72 1.72V12a.75.75 0 00-1.5 0v4.19l-1.72-1.72a.75.75 0 00-1.06 1.06l3 3z" clipRule="evenodd" />
          <path d="M14.25 5.25a5.23 5.23 0 00-1.279-3.434 9.768 9.768 0 016.963 6.963A5.23 5.23 0 0016.5 7.5h-1.875a.375.375 0 01-.375-.375V5.25z" />
        </svg>
      );
  }
};

const handleSelectFile = (file) => {
  setSelectedFiles(prev => {
    if (prev.includes(file.name)) {
      return prev.filter(name => name !== file.name);
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
    if (selectedFiles.length === 1) {
      await downloadImage(dateFolder, scanFolder, selectedFiles[0]);
    } else {
      await downloadMultipleScanImages(dateFolder, scanFolder, selectedFiles);
    }
    
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

const downloadAll = async () => {
  if (files.length === 0) return;
  
  setIsLoading(true);
  setDownloadStatus('Preparing download...');
  
  try {
    await downloadMultipleScanImages(dateFolder, scanFolder, files.map(file => file.name));
    setDownloadStatus('Download started!');
    await new Promise(resolve => setTimeout(resolve, 1000));
  } catch (error) {
    console.error('Error downloading all files:', error);
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
  setDeleteStatus('Deleting files...');

  try {
    await deleteScanImages(dateFolder, scanFolder, selectedFiles);
    setDeleteStatus('Files deleted successfully!');
    
    // Rafraîchir la liste des fichiers
    const updatedFiles = await getImagesInScan(dateFolder, scanFolder);
    setFiles(updatedFiles);
    
    // Réinitialiser la sélection
    setSelectedFiles([]);
    
    await new Promise(resolve => setTimeout(resolve, 1000));
  } catch (error) {
    console.error('Error deleting files:', error);
    setDeleteStatus('Failed to delete files. Please try again.');
    await new Promise(resolve => setTimeout(resolve, 2000));
  } finally {
    setIsDeleting(false);
    setDeleteStatus('');
  }
};

const handleSizeChange = (direction) => {
  const sizes = ['tiny', 'small', 'normal', 'large', 'huge'];
  const currentIndex = sizes.indexOf(imageSize);
  
  let newIndex;
  if (direction === 'decrease') {
    newIndex = Math.max(0, currentIndex - 1);
  } else {
    newIndex = Math.min(sizes.length - 1, currentIndex + 1);
  }
  
  const newSize = sizes[newIndex];
  setImageSize(newSize);
  localStorage.setItem('scanViewImageSize', newSize);
};

//  Charge la préférence de taille au démarrage
useEffect(() => {
  const savedSize = localStorage.getItem('scanViewImageSize');
  if (savedSize) {
    setImageSize(savedSize);
  }
}, []);

const handleShowLog = async () => {
  setIsLoadingLog(true);
  try {
    const content = await getScanLog(dateFolder, scanFolder);
    setLogContent(content);
    setShowLogPopup(true);
  } catch (error) {
    console.error('Error loading scan log:', error);
    setLogContent('Error loading scan log');
  } finally {
    setIsLoadingLog(false);
  }
};

const groupedFiles = groupFilesByType(files);
const scanDate = (dateFolder.split('-')[0]).replaceAll("_", "/");
const scanTime = (scanFolder.split('-')[1]).replaceAll("_", ":");;


  return (
    <Layout title={`Scan`} subtitle={`Date: ${scanDate} - Time: ${scanTime}`} backLink={`/date/${dateFolder}`}>
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
            <p>Are you sure you want to delete {selectedFiles.length} file(s)?</p>
            <p className="warning">This action cannot be undone!</p>
            <div className="confirm-actions">
              <button 
                onClick={() => setShowDeleteConfirm(false)}
                className="action-button"
              >
                Cancel
              </button>
              {/* Disable delete button for now -> Mobile App needs all images or none, not partial ?
              <button 
                onClick={confirmDelete}
                className="action-button delete-button"
              >
                Delete
              </button>*/} 
            </div>
          </div>
        </div>
      )}

      {showLogPopup && (
        <div className="log-popup">
          <div className="log-content">
            <div className="log-header">
              <h3>Scan Log</h3>
              <button onClick={() => setShowLogPopup(false)} className="close-button">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                  <path fillRule="evenodd" d="M5.47 5.47a.75.75 0 011.06 0L12 10.94l5.47-5.47a.75.75 0 111.06 1.06L13.06 12l5.47 5.47a.75.75 0 11-1.06 1.06L12 13.06l-5.47 5.47a.75.75 0 01-1.06-1.06L10.94 12 5.47 6.53a.75.75 0 010-1.06z" />
                </svg>
              </button>
            </div>
            <pre className="log-text">
              {isLoadingLog ? 'Loading...' : logContent}
            </pre>
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
          onClick={downloadAll}
          disabled={isLoading}
          className="action-button"
        >
          Download All ({files.length})
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
        <button
          onClick={handleShowLog}
          disabled={isLoadingLog}
          className="action-button log-button"
        >
          {isLoadingLog ? 'Loading Log...' : 'Scan Log'}
        </button>
        <div className="size-controls">
          <button 
            className="size-button"
            onClick={() => handleSizeChange('decrease')}
            title="Decrease size"
            disabled={imageSize === 'tiny'}
          >
            -
          </button>
          <button 
            className="size-button"
            onClick={() => handleSizeChange('increase')}
            title="Increase size"
            disabled={imageSize === 'huge'}
          >
            +
          </button>
        </div>
      </div>

      <div className={`file-grid size-${imageSize}`}>
        {Object.entries(groupedFiles).map(([type, groupFiles]) => (
          <div key={type} className="file-group">
            <h3>{type.toUpperCase()} Files</h3>
            <div className={`folder-grid size-${imageSize}`}>
              {groupFiles.map(file => (
                <div key={file.name} className="file-item">
                  <div className="file-checkbox">
                    <input
                      type="checkbox"
                      checked={selectedFiles.includes(file.name)}
                      onChange={() => handleSelectFile(file)}
                    />
                  </div>
                  <Link
                    to={`/date/${dateFolder}/scan/${scanFolder}/image/${file.name}`}
                    className="file-link"
                  >
                    <div className="file-thumbnail">
                      {isImage(file.name) ? (
                        <img
                          src={`${config.IMAGES_BASE_URL}/${dateFolder}/${scanFolder}/${file.name}`}
                          alt={file.name}
                        />
                      ) : (
                        getFileIcon(file.name)
                      )}
                    </div>
                    <p>{file.name}</p>
                  </Link>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default ScanView;