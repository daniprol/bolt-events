/**
 * A2A Playground JavaScript
 * Handles SSE streaming, UI interactions, and conversation management
 */

(function() {
    'use strict';

    // ============================================
    // State Management
    // ============================================
    const state = {
        currentConversationId: null,
        conversations: [],
        isStreaming: false,
        currentEventSource: null,
        lastEventId: null,
    };

    // ============================================
    // DOM Elements
    // ============================================
    const elements = {
        conversationList: null,
        searchInput: null,
        newChatBtn: null,
        messagesContainer: null,
        welcomeScreen: null,
        chatInput: null,
        sendBtn: null,
        themeToggle: null,
    };

    // ============================================
    // API Functions
    // ============================================
    const API = {
        async getConversations() {
            const response = await fetch('/agent/conversations/');
            const data = await response.json();
            return data.conversations || [];
        },

        async createConversation() {
            const response = await fetch('/agent/conversations/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            const data = await response.json();
            return data;
        },

        async getConversation(contextId) {
            const response = await fetch(`/agent/conversations/${contextId}/`);
            if (!response.ok) return null;
            return await response.json();
        },

        async deleteConversation(contextId) {
            await fetch(`/agent/conversations/${contextId}/`, {
                method: 'DELETE',
            });
        },

        async sendMessage(contextId, message) {
            const response = await fetch('/agent/rpc/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'tasks/sendSubscribe',
                    params: {
                        contextId: contextId,
                        message: {
                            role: 'user',
                            parts: [{ type: 'text', text: message }],
                        },
                    },
                    id: Date.now(),
                }),
            });
            const data = await response.json();
            return data.result;
        },

        async getTask(taskId) {
            const response = await fetch('/agent/rpc/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'tasks/get',
                    params: { id: taskId },
                    id: Date.now(),
                }),
            });
            const data = await response.json();
            return data.result;
        },

        async getAgentCard() {
            try {
                const response = await fetch('/agent/card/');
                return await response.json();
            } catch (e) {
                return {
                    name: 'A2A Agent',
                    description: 'AI Assistant',
                    capabilities: { streaming: true }
                };
            }
        },
    };

    // ============================================
    // SSE Streaming
    // ============================================
    function connectToStream(taskId, onMessage, onComplete) {
        disconnectFromStream();

        const url = `/agent/rpc/${taskId}/stream/`;
        const eventSource = new EventSource(url);
        state.currentEventSource = eventSource;

        eventSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                state.lastEventId = event.lastEventId;
                onMessage(data);
            } catch (e) {
                console.error('Failed to parse SSE message:', e);
            }
        };

        eventSource.onerror = (error) => {
            console.log('SSE error:', error);
            disconnectFromStream();
            if (onComplete) onComplete();
        };

        eventSource.addEventListener('task.completed', (event) => {
            disconnectFromStream();
            if (onComplete) onComplete();
        });

        eventSource.addEventListener('task.failed', (event) => {
            disconnectFromStream();
            if (onComplete) onComplete();
        });
    }

    function disconnectFromStream() {
        if (state.currentEventSource) {
            state.currentEventSource.close();
            state.currentEventSource = null;
        }
    }

    // ============================================
    // UI Rendering
    // ============================================
    function renderConversations(conversations) {
        state.conversations = conversations;
        
        if (!elements.conversationList) return;

        const filter = (elements.searchInput?.value || '').toLowerCase();
        const filtered = conversations.filter(c => 
            !filter || (c.title || '').toLowerCase().includes(filter)
        );

        if (filtered.length === 0) {
            elements.conversationList.innerHTML = `
                <div class="text-center py-8 text-gray-400 dark:text-gray-500 text-sm">
                    ${conversations.length === 0 ? 'No conversations yet' : 'No matches found'}
                </div>
            `;
            return;
        }

        elements.conversationList.innerHTML = filtered.map(conv => `
            <button 
                class="conversation-item w-full text-left p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-dark-700 transition-colors ${state.currentConversationId === conv.context_id ? 'bg-gray-200 dark:bg-dark-700' : ''}"
                data-context-id="${conv.context_id}"
            >
                <div class="flex items-center gap-2">
                    <svg class="w-4 h-4 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
                    </svg>
                    <span class="flex-1 truncate text-sm text-gray-700 dark:text-gray-200">${conv.title || 'New Conversation'}</span>
                    ${conv.is_streaming ? `
                        <span class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                    ` : ''}
                    <button 
                        class="delete-btn p-1 hover:bg-red-100 dark:hover:bg-red-900/30 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                        data-context-id="${conv.context_id}"
                        title="Delete conversation"
                    >
                        <svg class="w-3.5 h-3.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                        </svg>
                    </button>
                </div>
            </button>
        `).join('');

        // Add click handlers
        elements.conversationList.querySelectorAll('.conversation-item').forEach(item => {
            item.addEventListener('click', (e) => {
                if (!e.target.closest('.delete-btn')) {
                    selectConversation(item.dataset.contextId);
                }
            });
        });

        elements.conversationList.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await deleteConversation(btn.dataset.contextId);
            });
        });
    }

    function showWelcomeScreen() {
        if (elements.welcomeScreen) elements.welcomeScreen.classList.remove('hidden');
        if (elements.messagesContainer) elements.messagesContainer.classList.add('hidden');
    }

    function showMessagesContainer() {
        if (elements.welcomeScreen) elements.welcomeScreen.classList.add('hidden');
        if (elements.messagesContainer) elements.messagesContainer.classList.remove('hidden');
    }

    function renderMessages(messages) {
        if (!elements.messagesContainer) return;
        
        elements.messagesContainer.innerHTML = '';
        
        messages.forEach(msg => {
            appendMessage(msg.role, msg.parts);
        });
    }

    function appendMessage(role, parts) {
        if (!elements.messagesContainer) return;
        
        const isUser = role === 'user';
        const template = document.getElementById(isUser ? 'user-message-template' : 'agent-message-template');
        const clone = template.content.cloneNode(true);
        
        // Set message content
        const contentEl = clone.querySelector('.message-content');
        if (contentEl && parts) {
            const text = extractTextFromParts(parts);
            contentEl.textContent = text;
        }
        
        elements.messagesContainer.appendChild(clone);
        scrollToBottom();
    }

    function appendLoadingMessage() {
        if (!elements.messagesContainer) return;
        
        const template = document.getElementById('loading-template');
        const clone = template.content.cloneNode(true);
        elements.messagesContainer.appendChild(clone);
        scrollToBottom();
        return elements.messagesContainer.lastElementChild;
    }

    function removeLoadingMessage() {
        const loading = elements.messagesContainer?.querySelector('.loading-message');
        if (loading) loading.remove();
    }

    function updateLastAgentMessage(parts) {
        if (!elements.messagesContainer) return;
        
        const lastAgentMsg = [...elements.messagesContainer.children].reverse()
            .find(el => el.querySelector('.agent-avatar'));
        
        if (lastAgentMsg) {
            const contentEl = lastAgentMsg.querySelector('.message-content');
            if (contentEl && parts) {
                const text = extractTextFromParts(parts);
                contentEl.textContent += text;
            }
            // Hide thinking indicator
            const thinking = lastAgentMsg.querySelector('.thinking-block');
            if (thinking) thinking.classList.add('hidden');
        }
    }

    function appendToolCall(toolName, toolInput) {
        if (!elements.messagesContainer) return;
        
        const lastAgentMsg = [...elements.messagesContainer.children].reverse()
            .find(el => el.querySelector('.agent-avatar'));
        
        if (lastAgentMsg) {
            let toolCalls = lastAgentMsg.querySelector('.tool-calls');
            if (!toolCalls) {
                toolCalls = document.createElement('div');
                toolCalls.className = 'tool-calls mt-2 space-y-2';
                lastAgentMsg.querySelector('.rounded-2xl').after(toolCalls);
            }
            toolCalls.classList.remove('hidden');
            
            const template = document.getElementById('tool-call-template');
            const clone = template.content.cloneNode(true);
            clone.querySelector('.tool-name').textContent = toolName;
            clone.querySelector('pre').textContent = JSON.stringify(toolInput, null, 2);
            toolCalls.appendChild(clone);
        }
    }

    function appendToolResult(result) {
        if (!elements.messagesContainer) return;
        
        const lastToolCall = [...elements.messagesContainer.querySelectorAll('.tool-calls .bg-yellow-50')].pop();
        if (lastToolCall) {
            const template = document.getElementById('tool-result-template');
            const clone = template.content.cloneNode(true);
            clone.querySelector('pre').textContent = JSON.stringify(result, null, 2);
            lastToolCall.after(clone);
        }
    }

    function appendArtifact(name, content) {
        if (!elements.messagesContainer) return;
        
        const lastAgentMsg = [...elements.messagesContainer.children].reverse()
            .find(el => el.querySelector('.agent-avatar'));
        
        if (lastAgentMsg) {
            let artifacts = lastAgentMsg.querySelector('.artifacts');
            if (!artifacts) {
                artifacts = document.createElement('div');
                artifacts.className = 'artifacts mt-2 space-y-2';
                lastAgentMsg.appendChild(artifacts);
            }
            artifacts.classList.remove('hidden');
            
            const template = document.getElementById('artifact-template');
            const clone = template.content.cloneNode(true);
            if (name) clone.querySelector('.artifact-name').textContent = name;
            clone.querySelector('.artifact-content').textContent = JSON.stringify(content, null, 2);
            artifacts.appendChild(clone);
        }
    }

    function extractTextFromParts(parts) {
        if (!parts) return '';
        return parts.map(part => {
            if (part.type === 'text') return part.text || '';
            if (part.text) return part.text;
            return JSON.stringify(part);
        }).join('');
    }

    function scrollToBottom() {
        const container = elements.messagesContainer?.parentElement;
        if (container) {
            container.scrollTop = container.scrollHeight;
        }
    }

    // ============================================
    // Actions
    // ============================================
    async function loadConversations() {
        const conversations = await API.getConversations();
        renderConversations(conversations);
    }

    async function selectConversation(contextId) {
        state.currentConversationId = contextId;
        
        // Update UI
        renderConversations(state.conversations);
        
        // Load conversation
        const conv = await API.getConversation(contextId);
        if (!conv) return;
        
        showMessagesContainer();
        
        // Render existing messages
        const messages = conv.messages || [];
        renderMessages(messages);
        
        // If streaming, connect to stream
        if (conv.is_streaming && conv.tasks?.length > 0) {
            const lastTask = conv.tasks[0];
            connectToStream(lastTask.id, handleStreamEvent, () => {
                state.isStreaming = false;
                loadConversations(); // Refresh to update streaming status
            });
        }
    }

    async function createNewConversation() {
        disconnectFromStream();
        
        const conv = await API.createConversation();
        await loadConversations();
        selectConversation(conv.context_id);
    }

    async function deleteConversation(contextId) {
        disconnectFromStream();
        
        await API.deleteConversation(contextId);
        
        if (state.currentConversationId === contextId) {
            state.currentConversationId = null;
            showWelcomeScreen();
        }
        
        await loadConversations();
    }

    async function sendMessage(message) {
        if (!state.currentConversationId || !message.trim()) return;
        
        // Add user message to UI
        appendMessage('user', [{ type: 'text', text: message }]);
        
        // Show loading
        state.isStreaming = true;
        const loadingEl = appendLoadingMessage();
        
        try {
            // Send to API with streaming
            const result = await API.sendMessage(state.currentConversationId, message);
            
            // Connect to stream
            if (result?.task?.id) {
                connectToStream(result.task.id, 
                    (event) => handleStreamEvent(event, loadingEl),
                    () => {
                        state.isStreaming = false;
                        loadConversations();
                    }
                );
            }
        } catch (error) {
            console.error('Failed to send message:', error);
            state.isStreaming = false;
            if (loadingEl) loadingEl.remove();
        }
    }

    function handleStreamEvent(event, loadingEl) {
        const eventType = event.type || event.message?.type;
        
        // Remove loading indicator on first message
        if (loadingEl && ['task.message', 'task.completed', 'task.failed'].includes(eventType)) {
            loadingEl.remove();
        }
        
        switch (eventType) {
            case 'task.working':
                // Show thinking
                break;
                
            case 'task.message':
                const message = event.message || event;
                updateLastAgentMessage(message.parts || message.message?.parts);
                break;
                
            case 'tool-call':
                appendToolCall(event.toolName, event.input);
                break;
                
            case 'tool-call-result':
                appendToolResult(event.result);
                break;
                
            case 'task.artifact':
                const artifact = event.artifact;
                appendArtifact(artifact?.name, artifact?.parts);
                break;
                
            case 'task.completed':
            case 'task.failed':
                state.isStreaming = false;
                break;
        }
    }

    // ============================================
    // Theme Management
    // ============================================
    function initTheme() {
        const savedTheme = localStorage.getItem('theme') || 
            (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        
        if (savedTheme === 'dark') {
            document.documentElement.classList.add('dark');
        } else {
            document.documentElement.classList.remove('dark');
        }
    }

    function toggleTheme() {
        const isDark = document.documentElement.classList.toggle('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
    }

    // ============================================
    // Event Handlers
    // ============================================
    function setupEventListeners() {
        // New chat button
        elements.newChatBtn?.addEventListener('click', createNewConversation);
        
        // Search
        elements.searchInput?.addEventListener('input', () => {
            renderConversations(state.conversations);
        });
        
        // Theme toggle
        elements.themeToggle?.addEventListener('click', toggleTheme);
        
        // Chat input
        elements.chatInput?.addEventListener('input', (e) => {
            // Auto-resize
            e.target.style.height = 'auto';
            e.target.style.height = Math.min(e.target.scrollHeight, 200) + 'px';
            
            // Enable/disable send button
            elements.sendBtn.disabled = !e.target.value.trim();
        });
        
        elements.chatInput?.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                const message = elements.chatInput.value.trim();
                if (message && !state.isStreaming) {
                    elements.chatInput.value = '';
                    elements.chatInput.style.height = 'auto';
                    sendMessage(message);
                }
            }
        });
        
        elements.sendBtn?.addEventListener('click', () => {
            const message = elements.chatInput.value.trim();
            if (message && !state.isStreaming) {
                elements.chatInput.value = '';
                elements.chatInput.style.height = 'auto';
                sendMessage(message);
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Cmd/Ctrl + K to search
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                elements.searchInput?.focus();
            }
            
            // Cmd/Ctrl + N for new chat
            if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
                e.preventDefault();
                createNewConversation();
            }
        });
    }

    // ============================================
    // Initialization
    // ============================================
    async function init() {
        // Cache DOM elements
        elements.conversationList = document.getElementById('conversation-list');
        elements.searchInput = document.getElementById('search-conversations');
        elements.newChatBtn = document.getElementById('new-chat-btn');
        elements.messagesContainer = document.getElementById('messages-container');
        elements.welcomeScreen = document.getElementById('welcome-screen');
        elements.chatInput = document.getElementById('chat-input');
        elements.sendBtn = document.getElementById('send-btn');
        elements.themeToggle = document.getElementById('theme-toggle');
        
        // Initialize theme
        initTheme();
        
        // Setup events
        setupEventListeners();
        
        // Load initial data
        await loadConversations();
        
        // Show welcome screen initially
        showWelcomeScreen();
    }

    // Start when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
