(function() {
    // Extract config from script tag
    const scriptTag = document.currentScript;
    const tenantId = scriptTag.getAttribute('data-tenant-id');
    const apiUrl = scriptTag.getAttribute('data-api-url') || 'http://localhost:8000/api/v1/chat';

    // Create host element for Shadow DOM
    const host = document.createElement('div');
    host.id = 'rag-saas-widget-host';
    document.body.appendChild(host);

    // Attach Shadow DOM (isolates CSS from host site)
    const shadow = host.attachShadow({ mode: 'open' });

    // Inject Styles (Modern Glassmorphism)
    const style = document.createElement('style');
    style.textContent = `
        .widget-container {
            position: fixed;
            bottom: 20px;
            right: 20px;
            z-index: 999999;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }

        /* FAB Button */
        .fab {
            width: 60px;
            height: 60px;
            border-radius: 50%;
            background: linear-gradient(135deg, #6e8efb, #a777e3);
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        }
        .fab:hover { transform: scale(1.1); }
        .fab svg { width: 30px; height: 30px; fill: white; }

        /* Chat Window */
        .chat-window {
            position: absolute;
            bottom: 80px;
            right: 0;
            width: 380px;
            height: 550px;
            background: rgba(255, 255, 255, 0.85);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border-radius: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            opacity: 0;
            pointer-events: none;
            transform: translateY(20px) scale(0.95);
            transform-origin: bottom right;
            transition: all 0.3s cubic-bezier(0.19, 1, 0.22, 1);
            border: 1px solid rgba(255,255,255,0.4);
        }

        .chat-window.open {
            opacity: 1;
            pointer-events: all;
            transform: translateY(0) scale(1);
        }

        /* Header */
        .header {
            background: linear-gradient(135deg, #6e8efb, #a777e3);
            color: white;
            padding: 20px;
            font-weight: 600;
            font-size: 16px;
            display: flex;
            align-items: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .header-dot {
            width: 8px;
            height: 8px;
            background-color: #4ade80;
            border-radius: 50%;
            margin-right: 10px;
            box-shadow: 0 0 10px #4ade80;
        }

        /* Messages Area */
        .messages {
            flex: 1;
            padding: 20px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 12px;
            background: rgba(249, 250, 251, 0.5);
        }

        .msg {
            max-width: 85%;
            padding: 12px 16px;
            border-radius: 18px;
            font-size: 14px;
            line-height: 1.5;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .msg.bot {
            background: white;
            color: #1f2937;
            align-self: flex-start;
            border-bottom-left-radius: 4px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.05);
            border: 1px solid #e5e7eb;
        }

        .msg.user {
            background: linear-gradient(135deg, #6e8efb, #a777e3);
            color: white;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
            box-shadow: 0 2px 8px rgba(110,142,251,0.3);
        }

        .loading {
            align-self: flex-start;
            padding: 12px 16px;
            background: white;
            border-radius: 18px;
            border-bottom-left-radius: 4px;
            border: 1px solid #e5e7eb;
            display: none;
        }
        .loading.visible { display: flex; gap: 4px; }
        .dot { width: 6px; height: 6px; background: #9ca3af; border-radius: 50%; animation: bounce 1.4s infinite ease-in-out both; }
        .dot:nth-child(1) { animation-delay: -0.32s; }
        .dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }

        /* Input Area */
        .input-area {
            padding: 15px;
            background: white;
            border-top: 1px solid rgba(229, 231, 235, 0.5);
            display: flex;
            gap: 10px;
        }

        input {
            flex: 1;
            padding: 12px 15px;
            border: 1px solid #e5e7eb;
            border-radius: 25px;
            outline: none;
            font-size: 14px;
            transition: border-color 0.2s;
            background: #f9fafb;
        }
        
        input:focus {
            border-color: #6e8efb;
            background: white;
        }

        button {
            background: linear-gradient(135deg, #6e8efb, #a777e3);
            color: white;
            border: none;
            width: 42px;
            height: 42px;
            border-radius: 50%;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: transform 0.2s;
        }
        
        button:hover { transform: scale(1.05); }
        button svg { width: 18px; height: 18px; fill: white; transform: translateX(1px); }
    `;

    // Widget HTML Structure
    const container = document.createElement('div');
    container.className = 'widget-container';
    container.innerHTML = `
        <div class="chat-window" id="chatWindow">
            <div class="header">
                <div class="header-dot"></div>
                AI Support Agent
            </div>
            <div class="messages" id="messages">
                <div class="msg bot">Hello! I'm an AI assistant fully trained on this company's documentation. How can I help you today?</div>
                <div class="loading" id="loadingIndicator">
                    <div class="dot"></div><div class="dot"></div><div class="dot"></div>
                </div>
            </div>
            <div class="input-area">
                <input type="text" id="userInput" placeholder="Ask a question..." autocomplete="off">
                <button id="sendBtn">
                    <svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                </button>
            </div>
        </div>
        <div class="fab" id="fabBtn">
            <svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/></svg>
        </div>
    `;

    shadow.appendChild(style);
    shadow.appendChild(container);

    // Logic
    const fabBtn = shadow.getElementById('fabBtn');
    const chatWindow = shadow.getElementById('chatWindow');
    const sendBtn = shadow.getElementById('sendBtn');
    const userInput = shadow.getElementById('userInput');
    const messages = shadow.getElementById('messages');
    const loadingIndicator = shadow.getElementById('loadingIndicator');

    let isOpen = false;

    fabBtn.addEventListener('click', () => {
        isOpen = !isOpen;
        if (isOpen) {
            chatWindow.classList.add('open');
            userInput.focus();
        } else {
            chatWindow.classList.remove('open');
        }
    });

    function addMessage(text, sender) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `msg ${sender}`;
        // Basic markdown bold/code support for the UI
        let formattedText = text.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
        formattedText = formattedText.replace(/`(.*?)`/g, '<code style="background:#eee;padding:2px 4px;border-radius:4px;">$1</code>');
        msgDiv.innerHTML = formattedText;
        messages.insertBefore(msgDiv, loadingIndicator);
        messages.scrollTop = messages.scrollHeight;
    }

    async function sendMessage() {
        const text = userInput.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        userInput.value = '';
        loadingIndicator.classList.add('visible');
        messages.scrollTop = messages.scrollHeight;

        try {
            const response = await fetch(apiUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tenant_id: tenantId, message: text })
            });
            
            const data = await response.json();
            loadingIndicator.classList.remove('visible');
            
            if (response.ok) {
                addMessage(data.answer, 'bot');
            } else {
                addMessage('Sorry, an error occurred on the server.', 'bot');
            }
        } catch (err) {
            loadingIndicator.classList.remove('visible');
            addMessage('Network error connecting to the AI backend.', 'bot');
        }
    }

    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
})();
