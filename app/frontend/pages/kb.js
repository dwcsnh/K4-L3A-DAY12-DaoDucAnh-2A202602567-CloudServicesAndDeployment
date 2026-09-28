import { useState, useEffect } from 'react';
import Navbar from '../components/Navbar';

export default function KBPage() {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [detailModal, setDetailModal] = useState(null);

  const fetchFiles = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;
      const res = await fetch('/api/kb/files', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setFiles(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const ext = file.name.split('.').pop().toLowerCase();
    if (!['pdf', 'txt', 'docx'].includes(ext)) {
      setError(`File "${file.name}" không hợp lệ. Chỉ chấp nhận các định dạng: .pdf, .txt, .docx`);
      setSelectedFile(null);
      e.target.value = '';
      return;
    }

    setError('');
    setSelectedFile(file);
  };

  const handleUpload = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    setUploading(true);
    setError('');
    setSuccess('');

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const token = localStorage.getItem('token');
      const res = await fetch('/api/kb/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Upload thất bại');
      }

      setSuccess(`Tải lên và chuyển đổi file "${data.filename}" sang Markdown thành công! (${data.chunks_count} đoạn)`);
      setSelectedFile(null);
      const fileInput = document.getElementById('file-upload-input');
      if (fileInput) fileInput.value = '';
      fetchFiles();
    } catch (err) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (fileId, filename) => {
    if (!confirm(`Bạn có chắc muốn xóa file "${filename}"?`)) return;

    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/kb/files/${fileId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        setSuccess(`Đã xóa file "${filename}"`);
        fetchFiles();
      }
    } catch (err) {
      setError('Lỗi khi xóa tài liệu');
    }
  };

  const handleViewDetail = async (fileId) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/kb/files/${fileId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const detail = await res.json();
        setDetailModal(detail);
      }
    } catch (err) {
      setError('Không thể tải chi tiết file');
    }
  };

  const handleDownload = async (fileId, filename) => {
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`/api/kb/files/${fileId}/download`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Không tải được file');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setError('Lỗi khi tải file về máy');
    }
  };

  const formatSize = (bytes) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div>
      <Navbar />

      <main style={{ maxWidth: '1000px', margin: '30px auto', padding: '0 20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <h1 style={{ fontSize: '24px', fontWeight: '700' }}>Quản lý Knowledge Base</h1>
            <p style={{ color: '#64748b', fontSize: '14px', marginTop: '4px' }}>
              Tải lên tài liệu PDF, TXT, DOCX để chatbot AI học và trích dẫn thông tin
            </p>
          </div>
        </div>

        {error && (
          <div style={{ background: '#fee2e2', color: '#dc2626', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px' }}>
            ⚠️ {error}
          </div>
        )}

        {success && (
          <div style={{ background: '#dcfce7', color: '#16a34a', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px' }}>
            ✅ {success}
          </div>
        )}

        {/* Upload Form Box */}
        <div style={{ background: 'white', padding: '24px', borderRadius: '12px', border: '1px solid var(--border)', marginBottom: '30px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '14px' }}>Tải lên tài liệu mới</h2>
          <form onSubmit={handleUpload} style={{ display: 'flex', gap: '14px', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              id="file-upload-input"
              type="file"
              accept=".pdf,.txt,.docx"
              onChange={handleFileChange}
              style={{ flex: '1', minWidth: '240px' }}
            />
            <button
              type="submit"
              disabled={!selectedFile || uploading}
              className="btn-primary"
              style={{ opacity: !selectedFile || uploading ? 0.6 : 1 }}
            >
              {uploading ? 'Đang Ingest & Chuyển sang MD...' : 'Tải lên & Xử lý'}
            </button>
          </form>
          <p style={{ fontSize: '12px', color: '#64748b', marginTop: '8px' }}>
            * Định dạng được hỗ trợ: <strong>.pdf</strong>, <strong>.txt</strong>, <strong>.docx</strong>. Hệ thống sẽ tự động chuyển đổi sang Markdown và phân đoạn (chunking).
          </p>
        </div>

        {/* File List */}
        <div style={{ background: 'white', borderRadius: '12px', border: '1px solid var(--border)', overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h2 style={{ fontSize: '16px', fontWeight: '600' }}>Danh sách tài liệu đã upload ({files.length})</h2>
          </div>

          {loading ? (
            <p style={{ padding: '30px', textAlign: 'center', color: '#64748b' }}>Đang tải danh sách tài liệu...</p>
          ) : files.length === 0 ? (
            <div style={{ padding: '50px 20px', textAlign: 'center', color: '#64748b' }}>
              <p style={{ fontSize: '16px', marginBottom: '8px' }}>Chưa có tài liệu nào trong Knowledge Base</p>
              <p style={{ fontSize: '13px' }}>Hãy tải lên tài liệu PDF, TXT hoặc DOCX ở trên để bắt đầu hỏi đáp!</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '14px' }}>
              <thead>
                <tr style={{ background: '#f8fafc', borderBottom: '1px solid var(--border)' }}>
                  <th style={{ padding: '12px 20px' }}>Tên file</th>
                  <th style={{ padding: '12px 16px' }}>Định dạng</th>
                  <th style={{ padding: '12px 16px' }}>Dung lượng</th>
                  <th style={{ padding: '12px 16px' }}>Số đoạn (Chunks)</th>
                  <th style={{ padding: '12px 20px', textAlign: 'right' }}>Hành động</th>
                </tr>
              </thead>
              <tbody>
                {files.map((file) => (
                  <tr key={file.id} style={{ borderBottom: '1px solid var(--border)' }}>
                    <td style={{ padding: '14px 20px', fontWeight: '500' }}>📄 {file.filename}</td>
                    <td style={{ padding: '14px 16px' }}>
                      <span className={`badge badge-${file.file_type}`}>{file.file_type.toUpperCase()}</span>
                    </td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>{formatSize(file.size_bytes)}</td>
                    <td style={{ padding: '14px 16px', color: '#64748b' }}>{file.chunks_count} đoạn</td>
                    <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                        <button onClick={() => handleViewDetail(file.id)} className="btn-secondary" style={{ fontSize: '12px' }}>
                          Chi tiết
                        </button>
                        <button onClick={() => handleDownload(file.id, file.filename)} className="btn-secondary" style={{ fontSize: '12px' }}>
                          Tải về
                        </button>
                        <button onClick={() => handleDelete(file.id, file.filename)} className="btn-danger" style={{ fontSize: '12px' }}>
                          Xóa
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Modal: View Details */}
        {detailModal && (
          <div className="modal-overlay" onClick={() => setDetailModal(null)}>
            <div className="modal-content" onClick={(e) => e.stopPropagation()}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', borderBottom: '1px solid var(--border)', paddingBottom: '12px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: '700' }}>📄 {detailModal.filename}</h3>
                <button onClick={() => setDetailModal(null)} className="btn-secondary" style={{ padding: '4px 8px' }}>
                  ✕
                </button>
              </div>

              <div style={{ display: 'flex', gap: '10px', marginBottom: '16px' }}>
                <span className={`badge badge-${detailModal.file_type}`}>{detailModal.file_type.toUpperCase()}</span>
                <span className="badge badge-info">{detailModal.chunks_count} Chunks RAG</span>
                <span className="badge badge-warning">{formatSize(detailModal.size_bytes)}</span>
              </div>

              <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>Nội dung Markdown đã chuyển đổi:</h4>
              <pre
                style={{
                  background: '#f8fafc',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  padding: '14px',
                  fontSize: '13px',
                  maxHeight: '300px',
                  overflowY: 'auto',
                  whiteSpace: 'pre-wrap',
                  marginBottom: '20px',
                }}
              >
                {detailModal.markdown_content || '(Không có nội dung)'}
              </pre>

              <h4 style={{ fontSize: '14px', fontWeight: '600', marginBottom: '8px' }}>Các đoạn RAG (Chunks):</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '250px', overflowY: 'auto' }}>
                {detailModal.chunks.map((c, idx) => (
                  <div key={idx} style={{ padding: '10px', background: '#f1f5f9', borderRadius: '6px', fontSize: '12px' }}>
                    <strong style={{ color: '#2563eb' }}>{c.section}:</strong> {c.content}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
