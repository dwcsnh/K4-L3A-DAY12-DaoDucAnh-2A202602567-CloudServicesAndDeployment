import Link from 'next/link';
import { useRouter } from 'next/router';
import { useEffect, useState } from 'react';

export default function Navbar() {
  const router = useRouter();
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('token');
    const storedUser = localStorage.getItem('user');
    if (!token && router.pathname !== '/login' && router.pathname !== '/register') {
      router.push('/login');
    } else if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, [router.pathname]);

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    router.push('/login');
  };

  return (
    <nav className="navbar">
      <div className="nav-brand">
        <span>🤖 RAG Chatbot</span>
      </div>

      <div className="nav-links">
        <Link href="/kb" className={`nav-link ${router.pathname === '/kb' ? 'active' : ''}`}>
          📁 Quản lý KB
        </Link>
        <Link href="/chat" className={`nav-link ${router.pathname === '/chat' ? 'active' : ''}`}>
          💬 Chatbot AI
        </Link>
      </div>

      {user ? (
        <div className="user-status">
          <span className="badge badge-info">👤 {user.username}</span>
          <span className="badge badge-warning">
            Hạn mức: {user.usage_used}/{user.usage_limit}
          </span>
          <button onClick={handleLogout} className="btn-secondary" style={{ padding: '4px 10px', fontSize: '13px' }}>
            Đăng xuất
          </button>
        </div>
      ) : (
        <div className="user-status">
          <Link href="/login" className="btn-primary" style={{ padding: '6px 14px', fontSize: '13px' }}>
            Đăng nhập
          </Link>
        </div>
      )}
    </nav>
  );
}
