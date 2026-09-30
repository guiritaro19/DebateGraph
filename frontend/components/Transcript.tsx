'use client';
import { useEffect, useRef } from 'react';
import { FileText, ShieldCheck, MessageSquare, ArrowUpRight } from 'lucide-react';
import type { Candidate, Message, Source } from '../lib/types';
const phases:Record<string,string>={QUESTION:'Pergunta',ANSWER:'Resposta',REBUTTAL:'Réplica',COUNTER_REBUTTAL:'Tréplica'};
export default function Transcript({messages,candidates,sources,running,current}:{messages:Message[];candidates:Candidate[];sources:Source[];running:boolean;current:string}){
 const container=useRef<HTMLDivElement>(null);
 const follow=useRef(true);
 useEffect(()=>{const el=container.current;if(el&&follow.current)el.scrollTop=el.scrollHeight;},[messages]);
 return <div ref={container} onScroll={()=>{const el=container.current;if(el)follow.current=el.scrollHeight-el.scrollTop-el.clientHeight<80;}} className="transcript" aria-live="polite" aria-relevant="additions">
  {messages.length===0?<div className="empty-transcript"><div className="empty-symbol"><MessageSquare size={34} strokeWidth={1.3}/></div><h2>Um debate.<br/><span>Todas as evidências.</span></h2><p>Escolha dois participantes e um tema.<br/>Acompanhe cada resposta, fonte e decisão do grafo.</p><div className="empty-flow"><span>Pesquisar</span><i/><span>Simular</span><i/><span>Validar</span></div><p className="empty-note">Compare argumentos e confira as fontes de cada afirmação.</p></div>:
  messages.map((m,i)=>{const c=candidates.find(c=>c.id===m.candidate_id);return <article className="message" key={m.id}>
   <div className="message-marker"><span className="avatar">{c?.short_name.slice(0,2).toUpperCase()??'DG'}</span><div className="message-rail"/></div>
   <div className="message-body"><header><div><strong>{c?.short_name??m.candidate_id}</strong><span className="party">{c?.party}</span></div><time dateTime={m.timestamp}>{new Date(m.timestamp).toLocaleTimeString('pt-BR',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}</time></header>
    <div className="phase-row"><span>{phases[m.phase]??m.phase}</span><span className="mono">{String(i+1).padStart(2,'0')}</span></div>
    <p className="simulation-label">{m.label}</p>
    <p className="message-content">{m.content||'Transmitindo resposta validada…'}</p>
    {m.phase!=='QUESTION'&&<div className="validation-line"><ShieldCheck size={13}/>{m.citations.length?'Evidências verificadas':'Argumentação e provocação · sem novos fatos'}</div>}
    <details className="message-sources"><summary><FileText size={13}/>{m.citations.length} fonte{m.citations.length===1?'':'s'} consultada{m.citations.length===1?'':'s'}</summary><div className="source-disclosures">{m.citations.length?m.citations.map((citation,j)=>{const s=sources.find(s=>s.id===citation.source_id);return <div key={j}><a href={s?.url??'#'} target="_blank" rel="noreferrer">{s?.title??citation.source_id}<ArrowUpRight size={12}/></a><p>{s?.publisher} {s?.election_year?`· Eleição ${s.election_year}`:''}</p>{citation.quote&&<blockquote>{citation.quote}</blockquote>}</div>}):<p className="muted">Esta fala desenvolve um argumento conceitual sem novas afirmações factuais.</p>}</div></details>
   </div>
  </article>})}
  {running&&<div className="running-line"><span className="pulse-dot"/>{current==='search_web_per_phase'?'Pesquisando novas fontes na internet':current==='retrieve_candidate_context'?'Consultando as fontes':current==='source_validator'?'Conferindo as afirmações':'Preparando a próxima fala'}…</div>}
  <div/>
 </div>;
}

