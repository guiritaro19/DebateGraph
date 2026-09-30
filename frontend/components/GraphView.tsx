'use client';
import { useState } from 'react';
import { GitBranch, ChevronDown, ChevronUp } from 'lucide-react';
import type { Graph, Edge } from '../lib/types';
const labels:Record<string,string>={__start__:'START',__end__:'END',validate_debate:'validar debate',research_topic:'pesquisar tema',build_candidate_profiles:'construir perfis',generate_question:'pergunta ao oponente',candidate_answer:'resposta',candidate_rebuttal:'réplica',candidate_counter_rebuttal:'tréplica',candidate_agent:'subgrafo candidato',save_turn:'salvar mensagem',round_complete:'concluir rodada',round_pause:'checkpoint / pausa',complete:'finalizar sessão',search_web_per_phase:'pesquisar na internet',retrieve_candidate_context:'recuperar fontes',plan_argument:'construir argumento',generate_candidate_response:'gerar resposta',source_validator:'validar afirmações',regenerate:'regenerar · até 2×',conservative_response:'rebater pelo argumento'};
function Diagram({nodes,edges,current,onSelect}:{nodes:string[];edges:Edge[];current:string;onSelect:(node:string)=>void}){
 const visible=nodes.filter(n=>n!=='__start__'&&n!=='__end__');
 const ordered=['__start__',...visible,'__end__'];
 const positions=new Map(ordered.map((n,i)=>[n,{x:154,y:24+i*47}]));
 const height=ordered.length*47+16;
 return <svg className="graph-svg" viewBox={`0 0 316 ${height}`} role="img" aria-label="Grafo LangGraph compilado com arestas condicionais">
  <defs><marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0 0L6 3L0 6" fill="var(--line-bright)"/></marker></defs>
  {edges.map((edge:Edge,i)=>{const a=positions.get(edge.source),b=positions.get(edge.target);if(!a||!b)return null;const adjacent=Math.abs(a.y-b.y)<55;const lane=20+(i%4)*8;const d=adjacent?`M154 ${a.y+14} L154 ${b.y-14}`:`M246 ${a.y} C${316-lane} ${a.y},${316-lane} ${b.y},246 ${b.y}`;return <path key={i} d={d} fill="none" stroke="var(--line-bright)" strokeWidth="1.2" strokeDasharray={edge.conditional?'3 4':undefined} markerEnd="url(#arrow)"/>;})}
  {ordered.map(node=>{const p=positions.get(node)!;const active=current===node;const terminal=node.startsWith('__');return <g key={node} transform={`translate(${p.x},${p.y})`} className={active?'graph-node active':'graph-node'} role="button" tabIndex={0} aria-label={node} onClick={()=>onSelect(node)} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onSelect(node);}}}>
   <rect x={terminal?-38:-104} y="-14" width={terminal?76:208} height="28" rx="5" fill={active?'var(--amber-wash)':'var(--surface)'} stroke={active?'var(--amber)':'var(--line-bright)'}/>
   <circle cx={terminal?-25:-91} cy="0" r="2.5" fill={active?'var(--amber)':'var(--muted)'}/>
   <text x={terminal?5:5} y="4" textAnchor="middle" fill={active?'var(--amber)':'var(--text)'}>{labels[node]??node}</text>
  </g>;})}
 </svg>;
}
export default function GraphView({graph,current}:{graph:Graph|null;current:string}){
 const [sub,setSub]=useState(false),[selected,setSelected]=useState('');
 if(!graph)return <p className="muted">Aguardando o grafo do backend…</p>;
 const nested=['search_web_per_phase','retrieve_candidate_context','plan_argument','generate_candidate_response','source_validator','regenerate','conservative_response'].includes(current);
 return <div className="graph-view">
  <div className="panel-heading"><h3><GitBranch size={15}/> Fluxo real</h3><span className="mono">LANGGRAPH</span></div>
  <p className="graph-caption">Arestas obtidas do grafo compilado.<br/>Linhas tracejadas indicam condições.</p>
  <Diagram nodes={graph.nodes} edges={graph.edges} current={nested?'candidate_agent':current} onSelect={setSelected}/>
  <button className="subgraph-toggle" onClick={()=>setSub(!sub)} aria-expanded={sub}>Subgrafo do candidato {sub?<ChevronUp size={14}/>:<ChevronDown size={14}/>}</button>
  {(sub||nested)&&<Diagram nodes={graph.candidate_subgraph.nodes} edges={graph.candidate_subgraph.edges} current={current} onSelect={setSelected}/>}
  {selected&&<div className="node-detail"><span>Nó selecionado</span><code>{selected}</code></div>}
  <details className="mermaid"><summary>Ver definição Mermaid</summary><pre>{graph.mermaid}</pre></details>
 </div>;
}
