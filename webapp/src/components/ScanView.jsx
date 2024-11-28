import React, { useState, useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getImagesInScan, downloadScan } from '../api';
import Layout from './Layout';

// Fonction pour détecter les types d'images (par extension)
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


const groupedFiles = groupFilesByType(files);



  return (
    <Layout title={`Scan: ${scanFolder}`} backLink={`/date/${dateFolder}`}>
      <button onClick={() => downloadScan(dateFolder, scanFolder)} className="download-button">
        Download Scan
      </button>
      <div className="file-grid">
      {Object.entries(groupedFiles).map(([type, groupFiles]) => (
        <div key={type} className="file-group">
          <h3>{type.toUpperCase()} Files</h3>
          {groupFiles.map(file => (
            <Link
              to={`/date/${dateFolder}/scan/${scanFolder}/image/${file.name}`}
              key={file.name}
              className="file-item"
            >
              <div className="file-thumbnail">
                {isImage(file.name) ? (
                  <img
                    src={`http://sunscan.local:8000/images/${dateFolder}/${scanFolder}/${file.name}`}
                    alt={file.name}
                  />
                ) : (
                  getFileIcon(file.name)
                )}
              </div>
              <p>{file.name}</p>
            </Link>
          ))}
        </div>
      ))}
      </div>
    </Layout>
  );
};

export default ScanView;