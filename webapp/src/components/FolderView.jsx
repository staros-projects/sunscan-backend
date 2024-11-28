import React, { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getImagesInFolder, downloadImage } from '../api';
import Thumbnail from './Thumbnail';

// composant pour afficher les images contenues dans le dossier

function FolderView() {
  const { folderName } = useParams();
  const [images, setImages] = useState([]);

  useEffect(() => {
    getImagesInFolder(folderName).then((items)=>{
      // Sort by the name field
      const sortedItems = items.sort((a, b) => a.name.localeCompare(b.name));
      setImages(sortedItems)});
  }, [folderName]);

  return (
    <div className="folder-view" >
      <h2>Folder: {folderName}</h2>
      <Link to="/">Back to Dashboard</Link>
      <div className="image-grid">
        {images.map(image => (
          <div key={image.name} className="image-item">
            <Link to={`/image/${folderName}/${image.name}`}>
              <Thumbnail src={image.thumbnail} alt={image.name} />
            </Link>
            <button onClick={() => downloadImage(folderName, image.name)}>Download</button>
          </div>
        ))}
      </div>
    </div>
  );
}

export default FolderView;