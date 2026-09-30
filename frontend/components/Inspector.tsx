'use client';
import { useState } from 'react';
import { Code2, FileText, ArrowUpRight, Clock3, Zap } from 'lucide-react';
import GraphView from './GraphView';
import type { Graph, GraphState, NodeEvent } from '../lib/types';
export default function Inspector({graph,current,state,events}:{graph:Graph|null;current:string;state:GraphState;events:NodeEvent[]}){
 const [tab,setTab]=useState('graph');
 const docs=state.retrieved_context?.length?state.retrieved_context:state.research?.evidence??[];
 const total=events.reduce((sum,n)=>sum+n.tokens,0),time=events.reduce((sum,n)=>sum+("namespace" in n ? 0 : n.duration_ms),0);
 return <aside className="inspector"><div className="inspector-title"><Code2 size={16}/><h2>Por dentro do debate</h2><span className="dev-tag">DEV</span></div>
  <div className="inspector-tabs" role="tablist" aria-label="Inspeção"><button role="tab" aria-selected={tab==='graph'} onClick={()=>setTab('graph')}>Grafo</button><button role="tab" aria-selected={tab==='sources'} onClick={()=>setTab('sources')}>Fontes <span>{docs.length}</span></button><button role="tab" aria-selected={tab==='state'} onClick={()=>setTab('state')}>Estado</button></div>
  <div className="inspector-scroll">{tab==='graph'?<GraphView graph={graph} current={current}/>:tab==='sources'?<div className="evidence-list"><h3><FileText size={15}/> Contexto recuperado</h3><p className="muted">Consulta: {events.at(-1)?.retrieval_query??'Nenhuma consulta executada'}</p>{docs.length?docs.map((d,i)=><details key={d.chunk_id} open={i===0}><summary>{d.title}</summary><div className="evidence-meta"><span>Tier {d.tier}</span><span className="mono">cos {d.similarity.toFixed(3)}</span></div><p>{d.content}</p><a href={d.url} target="_blank" rel="noreferrer">Abrir fonte primária <ArrowUpRight size={12}/></a><code>{d.candidate_id} / {d.chunk_id.slice(0,8)}</code></details>):<p className="muted">As evidências aparecerão durante a pesquisa.</p>}</div>:<div className="state-panel"><h3>Estado persistido</h3><p className="muted">Mesmo ID para sessão e thread.</p><pre>{JSON.stringify(state,null,2)}</pre></div>}
  </div><div className="telemetry"><div><Zap size={13}/><span>Tokens</span><strong>{total.toLocaleString('pt-BR')}</strong></div><div><Clock3 size={13}/><span>Tempo nos nós</span><strong>{(time/1000).toFixed(1)}s</strong></div><p>{events.at(-1)?.model??'Modelo informado na execução'}</p></div>
 </aside>;
}
