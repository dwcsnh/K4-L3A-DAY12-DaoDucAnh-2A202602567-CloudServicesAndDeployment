import { useState, useEffect, useRef } from 'react';
import Navbar from '../components/Navbar';

export default function ChatPage() {
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const messagesEndRef = useRef(null);

  const fetchSessions = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const res = await fetch('/api/chat/sessions', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setSessions(data);
        if (data.length > 0 && !activeSessionId) {
          setActiveSessionId(data[0].id);
        }
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchMessages = async (sessionId) => {
    if (!sessionId) return;
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/chat/sessions/${sessionId}/messages`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  useEffect(() => {
    if (activeSessionId) {
      fetchMessages(activeSessionId);
    } else {
      setMessages([]);
    }
  }, [activeSessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleNewSession = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/chat/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title: 'Hội thoại mới' }),
      });
      if (res.ok) {
        const newSession = await res.json();
        setSessions([newSession, ...sessions]);
        setActiveSessionId(newSession.id);
        setError('');
      }
    } catch (err) {
      setError('Lỗi khi tạo cuộc trò chuyện mới');
    }
  };

  const handleDeleteSession = async (e, sessionId) => {
    e.stopPropagation();
    if (!confirm('Xóa cuộc trò chuyện này?')) return;
    try {
      const token = localStorage.getItem('token');
      await fetch(`/api/chat/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      const updated = sessions.filter((s) => s.id !== sessionId);
      setSessions(updated);
      if (activeSessionId === sessionId) {
        setActiveSessionId(updated.length > 0 ? updated[0].id : null);
      }
    } catch (err) {
      setError('Lỗi khi xóa session');
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    let targetSessionId = activeSessionId;
    if (!targetSessionId) {
      // Auto create a session first
      try {
        const token = localStorage.getItem('token');
        const res = await fetch('/api/chat/sessions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ title: input.substring(0, 30) }),
        });
        const created = await res.json();
        targetSessionId = created.id;
        setSessions([created, ...sessions]);
        setActiveSessionId(created.id);
      } catch (err) {
        setError('Không tạo được phiên chat');
        return;
      }
    }

    const question = input.trim();
    setInput('');
    setError('');
    setLoading(true);

    // Optimistic user message
    const tempUserMsg = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: question,
      citations: [],
      created_at: Date.now() / 1000,
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/chat/sessions/${targetSessionId}/messages`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ content: question }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Không gửi được tin nhắn');
      }

      setMessages((prev) => [...prev.filter((m) => m.id !== tempUserMsg.id), data.user_message, data.assistant_message]);

      // Update user in localStorage
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const userObj = JSON.parse(userStr);
        userObj.usage_used = data.usage_used;
        localStorage.setItem('user', JSON.stringify(userObj));
      }

      fetchSessions();
    } catch (err) {
      setError(err.message);
      // Remove temp message on error
      setMessages((prev) => prev.filter((m) => m.id !== tempUserMsg.id));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Navbar />

      <div style={{ display: 'flex', flex: '1', overflow: 'hidden' }}>
        {/* Sidebar */}
        <aside
          style={{
            width: '280px',
            background: 'white',
            borderRight: '1px solid var(--border)',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <div style={{ padding: '16px', borderBottom: '1px solid var(--border)' }}>
            <button
              onClick={handleNewSession}
              className="btn-primary"
              style={{ width: '100%', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px' }}
            >
              <span>+ Cuộc trò chuyện mới</span>
            </button>
          </div>

          <div style={{ flex: '1', overflowY: 'auto', padding: '12px 8px' }}>
            {sessions.length === 0 ? (
              <p style={{ textAlign: 'center', color: '#94a3b8', fontSize: '13px', marginTop: '20px' }}>Chưa có phiên chat nào</p>
            ) : (
              sessions.map((s) => (
                <div
                  key={s.id}
                  onClick={() => setActiveSessionId(s.id)}
                  style={{
                    padding: '10px 14px',
                    borderRadius: '8px',
                    fontSize: '13px',
                    fontWeight: activeSessionId === s.id ? '600' : '400',
                    background: activeSessionId === s.id ? '#eff6ff' : 'transparent',
                    color: activeSessionId === s.id ? '#1d4ed8' : '#334155',
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '4px',
                  }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '190px' }}>
                    💬 {s.title}
                  </span>
                  <button
                    onClick={(e) => handleDeleteSession(e, s.id)}
                    style={{ background: 'none', color: '#94a3b8', fontSize: '14px', padding: '2px 4px' }}
                    title="Xóa phiên"
                  >
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Main Chat Thread */}
        <section style={{ flex: '1', display: 'flex', flexDirection: 'column', background: '#f8fafc' }}>
          {error && (
            <div style={{ background: '#fee2e2', color: '#b91c1c', padding: '10px 20px', fontSize: '13px', borderBottom: '1px solid #fecaca' }}>
              ⚠️ {error}
            </div>
          )}

          {/* Messages */}
          <div style={{ flex: '1', overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', marginTop: '80px', color: '#64748b' }}>
                <h3 style={{ fontSize: '20px', fontWeight: '700', marginBottom: '8px' }}>Trợ lý RAG Chatbot</h3>
                <p style={{ fontSize: '14px', maxWidth: '480px', margin: '0 auto' }}>
                  Hỏi bất kỳ câu hỏi nào. Chatbot sẽ tìm kiếm thông tin trong Knowledge Base của bạn và trích dẫn nguồn cụ thể.
                </p>
              </div>
            )}

            {messages.map((m) => {
              const isUser = m.role === 'user';
              return (
                <div
                  key={m.id}
                  style={{
                    display: 'flex',
                    justifyContent: isUser ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      maxWidth: '75%',
                      background: isUser ? '#2563eb' : 'white',
                      color: isUser ? 'white' : '#0f172a',
                      padding: '14px 18px',
                      borderRadius: isUser ? '16px 16px 2px 16px' : '16px 16px 16px 2px',
                      border: isUser ? 'none' : '1px solid var(--border)',
                      boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                      fontSize: '14px',
                      lineHeight: '1.6',
                    }}
                  >
                    <div style={{ whiteSpace: 'pre-wrap' }}>{m.content}</div>

                    {/* Citations block */}
                    {!isUser && m.citations && m.citations.length > 0 && (
                      <div
                        style={{
                          marginTop: '14px',
                          paddingTop: '10px',
                          borderTop: '1px solid #f1f5f9',
                          fontSize: '12px',
                        }}
                      >
                        <div style={{ fontWeight: '600', color: '#64748b', marginBottom: '6px' }}>📚 Nguồn trích dẫn:</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                          {m.citations.map((c, i) => (
                            <div
                              key={i}
                              style={{
                                background: '#f8fafc',
                                border: '1px solid #e2e8f0',
                                borderRadius: '6px',
                                padding: '8px 10px',
                              }}
                            >
                              <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '3px' }}>
                                <span className="badge badge-info" style={{ fontSize: '10px' }}>
                                  📄 {c.filename}
                                </span>
                                <span style={{ color: '#475569', fontWeight: '500' }}>{c.section}</span>
                              </div>
                              <p style={{ color: '#64748b', fontStyle: 'italic', margin: 0 }}>"{c.snippet}"</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {loading && (
              <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                <div style={{ background: 'white', padding: '12px 18px', borderRadius: '16px', border: '1px solid var(--border)', color: '#64748b', fontSize: '13px' }}>
                  🤖 Đang tìm kiếm trong KB và tạo câu trả lời kèm trích dẫn...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Box */}
          <div style={{ padding: '16px 24px', background: 'white', borderTop: '1px solid var(--border)' }}>
            <form onSubmit={handleSendMessage} style={{ display: 'flex', gap: '12px' }}>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Nhập câu hỏi của bạn về tài liệu đã upload..."
                style={{ flex: '1', padding: '12px 16px' }}
                disabled={loading}
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="btn-primary"
                style={{ padding: '12px 24px', opacity: loading || !input.trim() ? 0.6 : 1 }}
              >
                Gửi
              </button>
            </form>
          </div>
        </section>
      </div>
    </div>
  );
}
