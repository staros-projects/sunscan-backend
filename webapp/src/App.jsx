import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Dashboard from './components/Dashboard';
import ScansDashboard from './components/ScansDashboard';
import SnapshotsDashboard from './components/SnapshotsDashboard';
import DateView from './components/DateView';
import ScanView from './components/ScanView';
import ImageView from './components/ImageView';
import StackingDashboard from './components/StackingDashboard';
import AnimationsDashboard from './components/AnimationsDashboard';
import StackingView from './components/StackingView';
import AnimationsView from './components/AnimationsView';

function App() {
  return (
    <div className="App">
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/scans" element={<ScansDashboard />} />
        <Route path="/snapshots" element={<SnapshotsDashboard />} />
        <Route path="/stacking" element={<StackingDashboard />} />
        <Route path="/animations" element={<AnimationsDashboard />} />
        <Route path="/date/:dateFolder" element={<DateView />} />
        <Route path="/date/:dateFolder/scan/:scanFolder" element={<ScanView />} />
        <Route path="/date/:dateFolder/scan/:scanFolder/image/:imageName" element={<ImageView />} />
        <Route path="/stacking/:dateFolder/:stackingFolder" element={<StackingView />} />
        <Route path="/stacking/:dateFolder/:stackingFolder/image/:imageName" element={<ImageView />} />
        <Route path="/animations/:dateFolder/:animationFolder" element={<AnimationsView />} />
        <Route path="/animations/:dateFolder/:animationFolder/image/:imageName" element={<ImageView />} />
      </Routes>
    </div>
  );
}

export default App;