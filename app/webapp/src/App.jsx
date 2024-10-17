import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import DateView from './components/DateView';
import ScanView from './components/ScanView';
import ImageView from './components/ImageView';

function App() {
  return (
    <div className="App">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/date/:dateFolder" element={<DateView />} />
        <Route path="/date/:dateFolder/scan/:scanFolder" element={<ScanView />} />
        <Route path="/date/:dateFolder/scan/:scanFolder/image/:imageName" element={<ImageView />} />
      </Routes>
    </div>
  );
}

export default App;