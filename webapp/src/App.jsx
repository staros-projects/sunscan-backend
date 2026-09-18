import { Navigate, Route, Routes } from 'react-router-dom';
import Browser from './components/Browser';
import { FeedbackProvider } from './components/Feedback';
import { StatsProvider } from './components/Shell';

export default function App() {
  return (
    <StatsProvider>
      <FeedbackProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/scans" replace />} />
          <Route path="/:section/*" element={<Browser />} />
        </Routes>
      </FeedbackProvider>
    </StatsProvider>
  );
}
