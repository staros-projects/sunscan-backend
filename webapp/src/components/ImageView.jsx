import React, { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { downloadImage } from '../api';
import Layout from './Layout';
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import { config } from '../config';

// composant pour afficher une image en grand

const ImageView = () => {
  const { dateFolder, scanFolder, imageName } = useParams();
  const navigate = useNavigate();
  const [rotation, setRotation] = useState(0);

  //  date pour le header
  const scanDate = scanFolder.split('_')[0].replaceAll("-", "/");
  const scanTime = scanFolder.split('_')[1].replaceAll("-", ":");

  // URL de l'image
  const imageUrl = `${config.IMAGES_BASE_URL}/${dateFolder}/${scanFolder}/${imageName}`;

  // Vérification du type de fichier
  const isViewable = useMemo(() => {
    const fileExtension = imageName.toLowerCase().split('.').pop();
    const nonViewableExtensions = ['txt', 'ser', 'fits'];
    return !nonViewableExtensions.includes(fileExtension);
  }, [imageName]);

  const handleRotate = (direction) => {
    setRotation(prev => prev + (direction === 'left' ? -90 : 90));
  };

  return (
    <Layout 
      title={`Image`} 
      subtitle={`Filename: ${imageName}`}
      backLink={`/date/${dateFolder}/scan/${scanFolder}`}
    >
      <div className="image-view-controls">
        {isViewable ? (
          <TransformWrapper
            initialScale={1}
            minScale={0.5}
            maxScale={4}
            centerOnInit={true}
          >
            {({ zoomIn, zoomOut, resetTransform }) => (
              <>
                <div className="image-controls">
                  <button onClick={() => zoomIn()} className="control-button">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="control-icon">
                      <path fillRule="evenodd" d="M12 3.75a.75.75 0 01.75.75v6.75h6.75a.75.75 0 010 1.5h-6.75v6.75a.75.75 0 01-1.5 0v-6.75H4.5a.75.75 0 010-1.5h6.75V4.5a.75.75 0 01.75-.75z" />
                    </svg>
                  </button>
                  <button onClick={() => zoomOut()} className="control-button">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="control-icon">
                      <path fillRule="evenodd" d="M3.75 12a.75.75 0 01.75-.75h15a.75.75 0 010 1.5h-15a.75.75 0 01-.75-.75z" />
                    </svg>
                  </button>
                  <button onClick={() => resetTransform()} className="control-button">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="control-icon">
                      <path fillRule="evenodd" d="M4.755 10.059a7.5 7.5 0 0112.548-3.364l1.903 1.903h-3.183a.75.75 0 100 1.5h4.992a.75.75 0 00.75-.75V4.356a.75.75 0 00-1.5 0v3.18l-1.9-1.9A9 9 0 003.306 9.67a.75.75 0 101.45.388zm15.408 3.352a.75.75 0 00-.919.53 7.5 7.5 0 01-12.548 3.364l-1.902-1.903h3.183a.75.75 0 000-1.5H2.984a.75.75 0 00-.75.75v4.992a.75.75 0 001.5 0v-3.18l1.9 1.9a9 9 0 0015.059-4.035.75.75 0 00-.53-.918z" />
                    </svg>
                  </button>
                  <button onClick={() => handleRotate('left')} className="control-button">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="control-icon">
                      <path fillRule="evenodd" d="M9.53 2.47a.75.75 0 010 1.06L4.81 8.25H15a6.75 6.75 0 010 13.5h-3a.75.75 0 010-1.5h3a5.25 5.25 0 100-10.5H4.81l4.72 4.72a.75.75 0 11-1.06 1.06l-6-6a.75.75 0 010-1.06l6-6a.75.75 0 011.06 0z" />
                    </svg>
                  </button>
                  <button onClick={() => handleRotate('right')} className="control-button">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="control-icon">
                      <path fillRule="evenodd" d="M14.47 2.47a.75.75 0 011.06 0l6 6a.75.75 0 010 1.06l-6 6a.75.75 0 11-1.06-1.06l4.72-4.72H9a5.25 5.25 0 100 10.5h3a.75.75 0 010 1.5H9a6.75 6.75 0 010-13.5h10.19l-4.72-4.72a.75.75 0 010-1.06z" />
                    </svg>
                  </button>
                </div>
                <TransformComponent>
                  <img 
                    src={imageUrl}
                    alt={imageName}
                    style={{ transform: `rotate(${rotation}deg)` }}
                    className="image-view"
                  />
                </TransformComponent>
              </>
            )}
          </TransformWrapper>
        ) : (
          <div className="non-viewable-message">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="warning-icon">
              <path fillRule="evenodd" d="M2.25 12c0-5.385 4.365-9.75 9.75-9.75s9.75 4.365 9.75 9.75-4.365 9.75-9.75 9.75S2.25 17.385 2.25 12zM12 8.25a.75.75 0 01.75.75v3.75a.75.75 0 01-1.5 0V9a.75.75 0 01.75-.75zm0 8.25a.75.75 0 100-1.5.75.75 0 000 1.5z" />
            </svg>
            <p>Visualization not possible for this filetype</p>
            <p className="file-extension">(.{imageName.split('.').pop()})</p>
          </div>
        )}
      </div>
    </Layout>
  );
};

export default ImageView;