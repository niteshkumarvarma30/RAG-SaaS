import { Routes, Route } from 'react-router-dom';
import Landing from './components/Landing';
import CompanyPortal from './components/CompanyPortal';
import EmployeePortal from './components/EmployeePortal';
import './index.css';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/company/*" element={<CompanyPortal />} />
      <Route path="/employee/*" element={<EmployeePortal />} />
    </Routes>
  );
}

export default App;
