import { useState, useEffect, useRef } from 'react';
import { Send, Database, Bot, User, Brain } from 'lucide-react';
import { UserButton, useUser } from '@clerk/clerk-react';

const API_BASE = 'http://localhost:8000/api/v1';

export default function Chat({ tenantId }) {
  const { user } = useUser();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [workflowStatus, setWorkflowStatus] = useState('');
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, workflowStatus]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = { role: 'user', content: input };
    const currentChatHistory = [...messages];
    
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setWorkflowStatus('Connecting to CognitRAG.ai...');

    try {
      const response = await fetch(`${API_BASE}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tenant_id: tenantId,
          user_id: user.id, // Clerk User ID
          message: userMessage.content,
          chat_history: currentChatHistory
        })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      let done = false;
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.replace('data: ', ''));
                if (data.status === 'done') {
                  setMessages(prev => [...prev, { role: 'assistant', content: data.answer, context: data.context }]);
                  setWorkflowStatus('');
                } else {
                  setWorkflowStatus(data.status);
                }
              } catch (err) {
                console.error("Failed to parse SSE", err);
              }
            }
          }
        }
      }
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Sorry, I encountered a network error while connecting to CognitRAG.ai backend.' }]);
      setWorkflowStatus('');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-container glass-panel" style={{ width: '100%', maxWidth: '1200px', margin: '0 auto', height: '90vh' }}>
      <header className="chat-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <Brain className="logo-icon" size={32} />
          <div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>CognitRAG.ai Assistant</h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginTop: '0.25rem' }}>Connected to Company: {tenantId}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="memory-badge">
            <Database size={16} />
            <span>Isolated Environment</span>
          </div>
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)', marginTop: '4rem' }}>
            <Bot size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>Send a message to start querying your enterprise knowledge graph.</p>
          </div>
        )}
        
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className={`avatar ${msg.role}`}>
              {msg.role === 'user' ? <User size={20} color="white" /> : <Bot size={20} color="white" />}
            </div>
            <div className="message-bubble">
              {msg.content.split('\n').map((line, j) => (
                <p key={j} style={{ minHeight: '1.2rem' }}>{line}</p>
              ))}
            </div>
          </div>
        ))}
        
        {isLoading && workflowStatus && (
          <div className="message bot">
            <div className="avatar bot"><Bot size={20} color="white" /></div>
            <div className="message-bubble workflow-indicator">
              <span className="workflow-spinner"></span>
              <span className="workflow-text">{workflowStatus}</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-area" onSubmit={handleSendMessage}>
        <div className="input-wrapper">
          <input
            type="text"
            className="chat-input"
            placeholder="Ask CognitRAG.ai anything..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button type="submit" className="send-btn" disabled={isLoading || !input.trim()}>
            <Send size={18} />
          </button>
        </div>
      </form>
    </div>
  );
}
