import React from 'react';
import { useParams } from 'react-router-dom';
import { downloadImage } from '../api';
import Layout from './Layout';

// composant pour afficher une image en grand

const ImageView = () => {
  const { dateFolder, scanFolder, imageName } = useParams();
  const imageUrl = `http://sunscan.local:8000/images/${dateFolder}/${scanFolder}/${imageName}`;

  return (
    <Layout title={`Image: ${imageName}`} backLink={`/date/${dateFolder}/scan/${scanFolder}`}>
      <div className="image-view-container">
        <button onClick={() => downloadImage(dateFolder, scanFolder, imageName)} className="download-button">
          Download Image
        </button>
        <div className="image-container">
          <img src={imageUrl} alt={imageName} />
        </div>
      </div>
    </Layout>
  );
};

export default ImageView;