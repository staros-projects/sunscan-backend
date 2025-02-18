import React from 'react';
import './LoadingPopup.css';

const LoadingPopup = ({ message }) => {
  return (
    <div className="loading-popup-overlay">
      <div className="loading-popup">
        <div className="loading-spinner"></div>
        <p>{message}</p>
      </div>
    </div>
  );
};

export default LoadingPopup; 