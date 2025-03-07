import { config, devLog } from './config';

//const API_URL = 'http://sunscan.local:8000'; 
//const API_URL = 'http://localhost:8000'; 

export async function getDateFolders() {
  devLog('Fetching date folders');
  
  // Simulation de délai en dev si configuré
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }
  
  const response = await fetch(`${config.API_URL}/dates`);
  const data = await response.json();
  
  devLog('Date folders received:', data);
  return data;
}

export async function getSnapshots() {
  const response = await fetch(`${config.API_URL}/snapshots`);
  return response.json();
}


export async function deleteAllSnapshots() {
  const response = await fetch(`${config.API_URL}/sunscan/snapshots/delete/all/`);
  return response.json();
}

export function downloadSnapshot(imageName) {
  window.location.href = `${config.API_URL}/download/snapshot/${imageName}`;
}

export async function getScanFolders(dateFolder) {
  const response = await fetch(`${config.API_URL}/dates/${dateFolder}`);
  return response.json();
}

export async function getImagesInScan(dateFolder, scanFolder) {
  const response = await fetch(`${config.API_URL}/dates/${dateFolder}/scans/${scanFolder}`);
  return response.json();
}


export function downloadImage(dateFolder, scanFolder, imageName) {
  window.location.href = `${config.API_URL}/download/image/${dateFolder}/${scanFolder}/${imageName}`;
}

export function getImageUrl(dateFolder, scanFolder, imageName) {
  return `${config.IMAGES_BASE_URL}/${dateFolder}/${scanFolder}/${imageName}`;
}




export async function downloadScan(dateFolder) {
  devLog('Downloading single scan:', dateFolder);
  window.location.href = `${config.API_URL}/download/scan/${dateFolder}`;
  // On attend un peu pour s'assurer que le téléchargement démarre
  await new Promise(resolve => setTimeout(resolve, 500));
}



// télécharger plusieurs dossiers
export async function downloadMultipleScans(folderNames) {
  devLog('Downloading multiple scans:', folderNames);
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }

  const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/scans/multiple?${queryString}`;
  
  // On attend un peu pour s'assurer que le téléchargement démarre
  await new Promise(resolve => setTimeout(resolve, 500));
}








// télécharger un scan spécifique d'une date
export async function downloadDateScan(dateFolder, scanFolder) {
  devLog('Downloading date scan:', dateFolder, scanFolder);
  window.location.href = `${config.API_URL}/download/date/${dateFolder}/scan/${scanFolder}`;
  await new Promise(resolve => setTimeout(resolve, 500));
}




// Fonction pour télécharger plusieurs scans d'une date
export async function downloadMultipleDateScans(dateFolder, scanFolders) {
  devLog('Downloading multiple date scans:', dateFolder, scanFolders);
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }

  const queryString = scanFolders.map(name => `folders=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/date/${dateFolder}/scans/multiple?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}





// Fonction pour télécharger plusieurs images d'un scan
export async function downloadMultipleScanImages(dateFolder, scanFolder, imageNames) {
  devLog('Downloading multiple scan images:', dateFolder, scanFolder, imageNames);
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }

  const queryString = imageNames.map(name => `images=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/date/${dateFolder}/scan/${scanFolder}/images/multiple?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}


// supprimer des dossiers de scan
export async function deleteScanFolders(folderNames) {
  devLog('Deleting scan folders:', folderNames);
  
  try {
    const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
    const response = await fetch(`${config.API_URL}/scans?${queryString}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Failed to delete folders');
    }

    return await response.json();
  } catch (error) {
    devLog('Error in deleteScanFolders:', error);
    throw error;
  }
}


// supprimer des scans d'une date
export async function deleteDateScans(dateFolder, scanFolders) {
  devLog('Deleting date scans:', dateFolder, scanFolders);
  
  try {
    const queryString = scanFolders.map(name => `folders=${encodeURIComponent(name)}`).join('&');
    const response = await fetch(`${config.API_URL}/dates/${dateFolder}/scans?${queryString}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Failed to delete scans');
    }

    return await response.json();
  } catch (error) {
    devLog('Error in deleteDateScans:', error);
    throw error;
  }
}





// supprimer des images d'un scan
export async function deleteScanImages(dateFolder, scanFolder, imageNames) {
  devLog('Deleting scan images:', dateFolder, scanFolder, imageNames);
  
  try {
    const queryString = imageNames.map(name => `images=${encodeURIComponent(name)}`).join('&');
    const response = await fetch(`${config.API_URL}/dates/${dateFolder}/scans/${scanFolder}/images?${queryString}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Failed to delete images');
    }

    return await response.json();
  } catch (error) {
    devLog('Error in deleteScanImages:', error);
    throw error;
  }
}





export const getScanLog = async (dateFolder, scanFolder) => {
  try {
    const response = await fetch(`${config.API_URL}/dates/${dateFolder}/scans/${scanFolder}/log`);
    if (!response.ok) {
      throw new Error('Failed to fetch scan log');
    }
    return await response.text();
  } catch (error) {
    console.error('Error fetching scan log:', error);
    throw error;
  }
};












// ----------------  Stacking  ---------------- //
export async function getStackingFolders() {
  devLog('Fetching stacking folders');
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }
  
  const response = await fetch(`${config.API_URL}/stacking`);
  return response.json();
}


export async function getStackingImages(stackingFolder) {
  devLog('Fetching stacking images:', stackingFolder);
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }
  
  const response = await fetch(`${config.API_URL}/stacking/${stackingFolder}`);
  return response.json();
}

// download
export async function downloadStackingFile(stackingFolder, fileName) {
  devLog('Downloading stacking file:', stackingFolder, fileName);
  window.location.href = `${config.API_URL}/download/stacking/${stackingFolder}/${fileName}`;
  await new Promise(resolve => setTimeout(resolve, 500));
}



export async function downloadMultipleStackingFiles(stackingFolder, fileNames) {
  devLog('Downloading multiple stacking files:', stackingFolder, fileNames);
  
  const queryString = fileNames.map(name => `files=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/stacking/multiple/${stackingFolder}/?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}




export async function downloadMultipleStackingFolders(folderNames) {
  devLog('Downloading multiple stacking folders:', folderNames);
  
  const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/stacking/folders?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}











export async function deleteStackingFolders(folderNames) {
  devLog('Deleting stacking folders:', folderNames);
  
  try {
    const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
    const response = await fetch(`${config.API_URL}/stacking/selection?${queryString}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Failed to delete folders');
    }

    return response.json();
  } catch (error) {
    devLog('Error in deleteStackingFolders:', error);
    throw error;
  }
}




// ---------------- Animations ---------------- //
export async function getAnimationFolders() {
  devLog('Fetching animation folders');
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }
  
  const response = await fetch(`${config.API_URL}/animations`);
  return response.json();
}

export async function getAnimationImages(animationFolder) {
  devLog('Fetching animation images:', animationFolder);
  
  if (config.isDev && config.dev.delaySimulation > 0) {
    await new Promise(resolve => setTimeout(resolve, config.dev.delaySimulation));
  }
  
  const response = await fetch(`${config.API_URL}/animations/${animationFolder}`);
  return response.json();
}

// Fonctions de téléchargement
export async function downloadAnimationFile(animationFolder, fileName) {
  devLog('Downloading animation file:', animationFolder, fileName);
  window.location.href = `${config.API_URL}/download/animations/${animationFolder}/${fileName}`;
  await new Promise(resolve => setTimeout(resolve, 500));
}

export async function downloadMultipleAnimationFiles(animationFolder, fileNames) {
  devLog('Downloading multiple animation files:', animationFolder, fileNames);
  
  const queryString = fileNames.map(name => `files=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/animations/multiple/${animationFolder}/?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}

// suppression
export async function deleteAnimationFolders(folderNames) {
  devLog('Deleting animation folders:', folderNames);
  
  try {
    const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
    const response = await fetch(`${config.API_URL}/animations/selection?${queryString}`, {
      method: 'DELETE',
      headers: {
        'Content-Type': 'application/json',
      }
    });

    if (!response.ok) {
      throw new Error('Failed to delete folders');
    }

    return response.json();
  } catch (error) {
    devLog('Error in deleteAnimationFolders:', error);
    throw error;
  }
}

export async function downloadMultipleAnimationFolders(folderNames) {
  devLog('Downloading multiple animation folders:', folderNames);
  
  const queryString = folderNames.map(name => `folders=${encodeURIComponent(name)}`).join('&');
  window.location.href = `${config.API_URL}/download/animations/folders?${queryString}`;
  
  await new Promise(resolve => setTimeout(resolve, 500));
}

export const getSunscanStats = async () => {
  try {
    const response = await fetch(`${config.API_URL}/sunscan/stats`);
    if (!response.ok) {
      throw new Error('Failed to fetch sunscan stats');
    }
    return await response.json();
  } catch (error) {
    console.error('Error fetching sunscan stats:', error);
    throw error;
  }
};
