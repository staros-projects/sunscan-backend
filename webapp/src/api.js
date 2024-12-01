const API_URL = 'http://sunscan.local:8000'; //todo : set config avec api en dev/prod

export async function getDateFolders() {
  const response = await fetch(`${API_URL}/dates`);
  return response.json();
}

export async function getSnapshots() {
  const response = await fetch(`${API_URL}/snapshots`);
  return response.json();
}


export async function deleteAllSnapshots() {
  const response = await fetch(`${API_URL}/sunscan/snapshots/delete/all/`);
  return response.json();
}

export function downloadSnapshot(imageName) {
  window.location.href = `${API_URL}/download/snapshot/${imageName}`;
}

export async function getScanFolders(dateFolder) {
  const response = await fetch(`${API_URL}/dates/${dateFolder}`);
  return response.json();
}

export async function getImagesInScan(dateFolder, scanFolder) {
  const response = await fetch(`${API_URL}/dates/${dateFolder}/scans/${scanFolder}`);
  return response.json();
}

export function downloadScan(dateFolder, scanFolder) {
  window.location.href = `${API_URL}/download/scan/${dateFolder}/${scanFolder}`;
}

export function downloadImage(dateFolder, scanFolder, imageName) {
  window.location.href = `${API_URL}/download/image/${dateFolder}/${scanFolder}/${imageName}`;
}