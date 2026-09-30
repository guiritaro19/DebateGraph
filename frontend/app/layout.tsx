import type { Metadata } from 'next';
import '@fontsource/geist/400.css';
import '@fontsource/geist/500.css';
import '@fontsource/geist/600.css';
import '@fontsource/geist-mono/400.css';
import './globals.css';
export const metadata: Metadata = { title: 'DebateGraph · laboratório de debates', description: 'Simulações com evidências públicas. Um laboratório aberto de LangGraph e RAG.' };
export default function Layout({ children }: Readonly<{children:React.ReactNode}>) {
 return <html lang="pt-BR"><body>{children}</body></html>;
}
