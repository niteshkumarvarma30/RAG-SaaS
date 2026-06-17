import { useNavigate } from 'react-router-dom';
import { Building2, UserCircle, Brain } from 'lucide-react';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="landing-container">
      <div className="landing-header">
        <Brain className="logo-icon" size={48} />
        <h1>Welcome to CognitRAG.ai</h1>
        <p>Corrective Cognitive Graph RAG Platform</p>
      </div>
      
      <div className="landing-cards">
        <div className="role-card glass-panel" onClick={() => navigate('/company')}>
          <Building2 size={48} />
          <h2>Company Portal</h2>
          <p>Register your tenant, upload proprietary documents, and manage employee access.</p>
          <button className="primary-btn">Enter as Tenant</button>
        </div>

        <div className="role-card glass-panel" onClick={() => navigate('/employee')}>
          <UserCircle size={48} />
          <h2>Employee Portal</h2>
          <p>Login with your Company ID to query your enterprise knowledge graph.</p>
          <button className="primary-btn">Enter as Employee</button>
        </div>
      </div>
    </div>
  );
}
