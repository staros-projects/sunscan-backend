import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getAnimationImages, downloadAnimationFile, downloadMultipleAnimationFiles } from '../api';
import Layout from './Layout';
import { devLog, config } from '../config';
import './Dashboard.css';

const AnimationsView = () => {
  const { dateFolder, animationFolder } = useParams();
  const [images, setImages] = useState([]);
  const [selectedImages, setSelectedImages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [downloadStatus, setDownloadStatus] = useState('');

  useEffect(() => {
    devLog('Fetching animation images for folder:', animationFolder);
    getAnimationImages(animationFolder).then((items) => {
      devLog('Received items:', items);
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setImages(sortedItems);
    }).catch(error => {
      devLog('Error fetching images:', error);
    });
  }, [animationFolder]);

  const handleSelectImage = (image) => {
    setSelectedImages(prev => {
      if (prev.includes(image.name)) {
        return prev.filter(f => f !== image.name);
      }
      return [...prev, image.name];
    });
  };

  const handleSelectAll = () => {
    if (selectedImages.length === images.length) {
      setSelectedImages([]);
    } else {
      setSelectedImages(images.map(image => image.name));
    }
  };

  const downloadSelected = async () => {
    if (selectedImages.length === 0) return;
    
    setIsLoading(true);
    setDownloadStatus('Preparing download...');
    
    try {
      if (selectedImages.length === 1) {
        await downloadAnimationFile(animationFolder, selectedImages[0]);
      } else {
        await downloadMultipleAnimationFiles(animationFolder, selectedImages);
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


  const animationsDate = (animationFolder.split('_')[0]).replaceAll("-", "/");
  const animationsTime = (animationFolder.split('_')[1]).replaceAll("-", ":");
  
    return (
      <Layout title={`Animations`} subtitle={`Date: ${animationsDate} - Time: ${animationsTime}`} backLink="/animations">
      {isLoading && downloadStatus && (
        <div className="waiting-popup">
          <div className="waiting-message">
            <div className="loading-spinner"></div>
            <p>{downloadStatus}</p>
          </div>
        </div>
      )}

      <div className="dashboard-actions">
        <button 
          onClick={downloadSelected} 
          disabled={selectedImages.length === 0 || isLoading}
          className="action-button"
        >
          Download Selected ({selectedImages.length})
        </button>
        <button 
          onClick={handleSelectAll}
          className="action-button"
        >
          {selectedImages.length === images.length ? 'Unselect All' : 'Select All'}
        </button>
      </div>

      <div className="animations-view-grid">
        {images.map(image => (
          <div key={image.name} className="animations-view-item">
            <div className="folder-checkbox">
              <input
                type="checkbox"
                checked={selectedImages.includes(image.name)}
                onChange={() => handleSelectImage(image)}
              />
            </div>
            <div className="folder-link">
              <div className="folder-icon">
                <img 
                  src={`${config.API_URL}${image.thumbnail}`}
                  alt={image.name}
                  className="image-thumbnail"
                />
              </div>
              <p>{image.name}</p>
            </div>
          </div>
        ))}
      </div>
    </Layout>
  );
};

export default AnimationsView; 