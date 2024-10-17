import React from 'react';

// composant pour afficher une image miniature

function Thumbnail({ src, alt }) {
  return <img src={src} alt={alt} style={{ width: '100px', height: '100px', objectFit: 'cover' }} />;
}

export default Thumbnail;