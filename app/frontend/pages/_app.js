import '../styles/globals.css';
import Head from 'next/head';

export default function App({ Component, pageProps }) {
  return (
    <>
      <Head>
        <title>RAG Chatbot — Quản lý Knowledge Base & Hỏi Đáp AI</title>
        <meta name="description" content="RAG Chatbot với Knowledge Base đa định dạng PDF, TXT, DOCX kèm trích dẫn nguồn." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>
      <Component {...pageProps} />
    </>
  );
}
