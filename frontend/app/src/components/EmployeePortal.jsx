import { useState } from 'react';
import { SignedIn, SignedOut, SignIn, useUser, UserButton } from '@clerk/clerk-react';
import { Building2, ArrowRight } from 'lucide-react';
import Chat from './Chat';

export default function EmployeePortal() {
  const [companyIdInput, setCompanyIdInput] = useState('');
  const [activeCompanyId, setActiveCompanyId] = useState('');

  if (!activeCompanyId) {
    return (
      <div className="portal-container">
        <div className="company-auth-card glass-panel">
          <Building2 size={48} className="logo-icon" />
          <h2>Join Company Workspace</h2>
          <p>Please enter the Company ID provided by your administrator to access the enterprise Knowledge Graph.</p>
          
          <div className="input-wrapper" style={{ marginTop: '2rem' }}>
            <input 
              type="text" 
              className="chat-input" 
              placeholder="Enter Company ID..."
              value={companyIdInput}
              onChange={(e) => setCompanyIdInput(e.target.value)}
            />
            <button 
              className="primary-btn" 
              onClick={() => setActiveCompanyId(companyIdInput)}
              disabled={!companyIdInput.trim()}
            >
              Continue <ArrowRight size={18} style={{ marginLeft: '0.5rem' }} />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="portal-container">
      <SignedOut>
        <div className="auth-container">
          <div className="auth-box">
            <h3>Employee Sign In</h3>
            <SignIn redirectUrl="/employee" routing="hash" />
          </div>
        </div>
      </SignedOut>

      <SignedIn>
        <Chat tenantId={activeCompanyId} />
      </SignedIn>
    </div>
  );
}
