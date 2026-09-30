export const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000';
export async function request<T>(path:string, options?:RequestInit):Promise<T> {
 const response=await fetch(API+path, options);
 if(!response.ok){const error=await response.json().catch(()=>({detail:response.statusText}));throw new Error(typeof error.detail==='string'?error.detail:JSON.stringify(error.detail));}
 return response.json();
}
