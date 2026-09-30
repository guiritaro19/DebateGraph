/** Development-only portable PostgreSQL. Binary cache/data never enter Git. */
import { downloadBinaries } from '@boomship/postgres-vector-embedded';
import { Client } from 'pg';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import fs from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const exec=promisify(execFile);
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const runtime=path.join(root,'runtime');
const binaries=path.join(runtime,'postgres-binaries');
const data=path.join(runtime,'postgres-data');
const port=5433;
const exe=name=>path.join(binaries,'bin',name+(process.platform==='win32'?'.exe':''));
const run=(name,args)=>exec(exe(name),args,{windowsHide:true,timeout:60000});
const action=process.argv[2]??'start';
await fs.mkdir(runtime,{recursive:true});
if(action==='install'||action==='start'){
 await downloadBinaries({targetDir:binaries,variant:'lite'});
 if(action==='install'){console.log('PostgreSQL + pgvector downloaded.');process.exit(0);}
 try{await fs.access(path.join(data,'PG_VERSION'));}catch{
  const passwordFile=path.join(runtime,'.postgres-password');
  await fs.writeFile(passwordFile,'debategraph',{mode:0o600});
  try{await run('initdb',['-D',data,'-U','debategraph','--pwfile',passwordFile,'--auth-host=scram-sha-256','--auth-local=trust','--encoding=UTF8','--locale=C']);}
  finally{await fs.unlink(passwordFile);}
 }
 const status=await run('pg_ctl',['status','-D',data]).then(()=>true,()=>false);
 if(!status)await run('pg_ctl',['start','-D',data,'-l',path.join(runtime,'postgres.log'),'-o',`-h 127.0.0.1 -p ${port}`,'-w']);
 const options={host:'127.0.0.1',port,user:'debategraph',password:'debategraph'};
 const client=new Client({...options,database:'postgres'});await client.connect();
 const exists=await client.query("SELECT 1 FROM pg_database WHERE datname='debategraph'");
 if(!exists.rowCount)await client.query('CREATE DATABASE debategraph');
 await client.end();
 const db=new Client({...options,database:'debategraph'});await db.connect();
 await db.query('CREATE EXTENSION IF NOT EXISTS vector');
 const version=await db.query("SELECT version(),extversion FROM pg_extension WHERE extname='vector'");
 await db.end();console.log(`PostgreSQL listening on 127.0.0.1:${port}; pgvector ${version.rows[0].extversion}`);
}else if(action==='stop'){
 await run('pg_ctl',['stop','-D',data,'-m','fast','-w']);console.log('PostgreSQL stopped. Data preserved.');
}else if(action==='status'){
 console.log((await run('pg_ctl',['status','-D',data])).stdout);
}else throw new Error('Use: node tools/postgres.mjs install|start|stop|status');
