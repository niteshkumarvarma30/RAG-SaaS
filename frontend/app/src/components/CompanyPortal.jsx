import { useState, useEffect } from 'react';
import { SignedIn, SignedOut, SignIn, SignUp, useUser, UserButton } from '@clerk/clerk-react';
import { Upload, FileText, CheckCircle, Clock, Trash2, AlertCircle } from 'lucide-react';

export default function CompanyPortal() {
  const { user } = useUser();
  const [file, setFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [documents, setDocuments] = useState([]);
  const [isFetching, setIsFetching] = useState(false);

  const fetchDocuments = async () => {
    if (!user) return;
    setIsFetching(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/documents/${user.id}`);
      if (res.ok) {
        const data = await res.json();
        setDocuments(data);
      }
    } catch (e) {
      console.error("Failed to fetch documents", e);
    } finally {
      setIsFetching(false);
    }
  };

  useEffect(() => {
    if (user) {
      fetchDocuments();
    }
  }, [user]);

  const handleUpload = async () => {
    if (!file || !user) return;
    setUploadStatus('Uploading...');
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('tenant_id', user.id);

    try {
      const res = await fetch('http://localhost:8000/api/v1/ingest', {
        method: 'POST',
        body: formData
      });
      
      if (res.ok) {
        setUploadStatus('Finished Uploading');
        setFile(null);
        fetchDocuments(); // Refresh list immediately
        setTimeout(() => setUploadStatus(''), 3000);
      } else {
        setUploadStatus('Upload Failed');
      }
    } catch (e) {
      setUploadStatus('Upload Failed');
    }
  };

  const handleDelete = async (documentId) => {
    if (!user) return;
    setUploadStatus('Deleting...');
    
    try {
      const res = await fetch(`http://localhost:8000/api/v1/documents/${user.id}/${documentId}`, {
        method: 'DELETE'
      });
      
      if (res.ok) {
        setUploadStatus('Deleted completely');
        fetchDocuments(); // Refresh list
        setTimeout(() => setUploadStatus(''), 3000);
      } else {
        setUploadStatus('Deletion Failed');
      }
    } catch (e) {
      setUploadStatus('Deletion Failed');
    }
  };

  return (
    <div className="portal-container">
      <header className="portal-header glass-panel">
        <h2>Company Admin Portal</h2>
        <SignedIn>
          <UserButton afterSignOutUrl="/" />
        </SignedIn>
      </header>

      <SignedOut>
        <div className="auth-container">
          <div className="auth-box">
            <h3>Sign In</h3>
            <SignIn fallbackRedirectUrl="/company" routing="hash" />
          </div>
          <div className="auth-box">
            <h3>Register Company</h3>
            <SignUp fallbackRedirectUrl="/company" routing="hash" />
          </div>
        </div>
      </SignedOut>

      <SignedIn>
        <div className="dashboard-content">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div className="info-card glass-panel">
              <h3>Your Company ID</h3>
              <p className="tenant-id">{user?.id}</p>
              <p className="hint" style={{ color: 'var(--text-muted)' }}>Share this ID with your employees so they can access the RAG platform.</p>
            </div>

            <div className="upload-card glass-panel">
              <h3>Knowledge Base Manager</h3>
              
              <div className="upload-zone" style={{ marginTop: '1.5rem' }}>
                <input 
                  type="file" 
                  accept=".pdf" 
                  onChange={(e) => setFile(e.target.files[0])} 
                  id="file-upload"
                  style={{ display: 'none' }}
                />
                <label htmlFor="file-upload" className="upload-label" style={{ padding: '2rem' }}>
                  <FileText size={28} />
                  <span>{file ? file.name : 'Select a PDF document...'}</span>
                </label>
                
                <button 
                  className="primary-btn upload-btn" 
                  onClick={handleUpload}
                  disabled={!file || uploadStatus === 'Uploading...' || uploadStatus === 'Deleting...'}
                >
                  <Upload size={18} /> Upload to Vector Database
                </button>
              </div>

              {uploadStatus && (
                <div className={`status-badge ${uploadStatus.includes('Finished') || uploadStatus.includes('Deleted completely') ? 'success' : 'pending'}`}>
                  {uploadStatus.includes('Finished') || uploadStatus.includes('Deleted completely') ? <CheckCircle size={16} /> : <Clock size={16} />}
                  <span>{uploadStatus}</span>
                </div>
              )}
            </div>
          </div>

          <div className="info-card glass-panel" style={{ display: 'flex', flexDirection: 'column' }}>
            <h3>Uploaded Documents</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem', fontSize: '0.9rem' }}>
              These documents form the isolated RAG context for your employees.
            </p>
            
            <div style={{ flexGrow: 1, overflowY: 'auto', maxHeight: '500px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {isFetching && documents.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: '2rem' }}>Loading documents...</p>
              ) : documents.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem 1rem', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
                  <AlertCircle size={32} style={{ margin: '0 auto 1rem', color: 'var(--text-muted)' }} />
                  <p style={{ color: 'var(--text-muted)' }}>No documents uploaded yet.</p>
                </div>
              ) : (
                documents.map(doc => (
                  <div key={doc.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1rem', background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', overflow: 'hidden' }}>
                      <FileText size={20} color="var(--accent)" />
                      <div style={{ overflow: 'hidden' }}>
                        <p style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '200px' }}>{doc.filename}</p>
                        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Status: {doc.status}</p>
                      </div>
                    </div>
                    <button 
                      onClick={() => handleDelete(doc.id)}
                      disabled={uploadStatus === 'Deleting...' || uploadStatus === 'Uploading...'}
                      style={{ background: 'rgba(239, 68, 68, 0.1)', color: '#ef4444', border: '1px solid rgba(239, 68, 68, 0.2)', padding: '0.5rem', borderRadius: '6px', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.2s' }}
                      onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'}
                      onMouseLeave={(e) => e.currentTarget.style.background = 'rgba(239, 68, 68, 0.1)'}
                      title="Delete Document"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </SignedIn>
    </div>
  );
}
