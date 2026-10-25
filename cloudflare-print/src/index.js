import { browserIdentity, agentAuthorized, jsonResponse, deny } from './security.js';
import { UI } from './ui.js';
import { createDraft, confirmDraft, getOwnerJob, listOwnerJobs, cancelOwnerJob,
         claimNext, leasedContent, ackCapture, purgeExpired } from './store.js';

function validId(id) { return /^[0-9a-f]{8}-[0-9a-f-]{27,28}$/.test(id); }
function respondError(error) {
  if (error instanceof SyntaxError || /invalid|unsupported|size|too large|document|missing|media/i.test(error.message || '')) {
    return jsonResponse({ error: error.message }, 400);
  }
  return jsonResponse({ error: 'internal error' }, 500);
}
function mustHaveOrigin(req, url) {
  const origin = req.headers.get('origin');
  const fetchSite = req.headers.get('sec-fetch-site');
  return origin === url.origin && (!fetchSite || ['same-origin', 'none'].includes(fetchSite));
}
function noStoreHeaders(extra={}) { return { 'cache-control':'no-store', 'x-content-type-options':'nosniff', ...extra }; }
const TOOLS = [
  { name:'prepare_print', description:'Stage a text receipt for printing. NEVER prints. Owner must open the approval URL and confirm in the Cloudflare UI.', inputSchema:{type:'object',properties:{content:{type:'string'},title:{type:'string'},format:{type:'string',enum:['text/plain','text/markdown']}},required:['content']} },
  { name:'get_print_status', description:'Read own queued/captured/uncertain job status. Captured does not mean paper printed.', inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id']} },
  { name:'cancel_queued_print', description:'Cancel own job before it is claimed. Requires user authorization; leased or captured jobs cannot be cancelled.', inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id']} }
];
function mcpReply(id, result) { return jsonResponse({jsonrpc:'2.0',id,result}); }
function mcpError(id,code,message) { return jsonResponse({jsonrpc:'2.0',id,error:{code,message}}); }
function toolResult(value) {return {content:[{type:'text',text:JSON.stringify(value)}]};}

async function mcp(req, env, owner, url) {
  const payload = await req.json();
  if (!payload || payload.jsonrpc !== '2.0' || typeof payload.method !== 'string') return mcpError(payload?.id??null,-32600,'Invalid Request');
  if (payload.method === 'notifications/initialized') return new Response(null,{status:202});
  if (payload.method === 'initialize') return mcpReply(payload.id,{
    protocolVersion:'2025-06-18',capabilities:{tools:{listChanged:false}},serverInfo:{name:'Karin Print Capture',version:'0.1.0'}
  });
  if (payload.method === 'ping') return mcpReply(payload.id,{});
  if (payload.method === 'tools/list') return mcpReply(payload.id,{tools:TOOLS});
  if (payload.method !== 'tools/call') return mcpError(payload.id,-32601,'Method not found');
  const name = payload.params?.name, args=payload.params?.arguments||{};
  try {
    if (name === 'prepare_print') {
      if (typeof args.content !== 'string') throw new Error('content required');
      const request=new Request(url.origin+'/api/prepare',{
        method:'POST',headers:{'content-type':'application/json'},
        body:JSON.stringify({content:args.content,format:args.format||'text/plain',title:args.title||'ChatGPT draft'})
      });
      const staged=await createDraft(env,owner,request);
      const fragment=new URLSearchParams({draft:staged.job.id,approval:staged.approval_token||''}).toString();
      return mcpReply(payload.id,toolResult({
        job:staged.job,approval_url:url.origin+'/#'+fragment,
        notice:'No print was sent. Open the approval URL in your authenticated browser and explicitly confirm. Capture-only offline backend.'
      }));
    }
    if (!validId(args.job_id||'')) throw new Error('invalid job ID');
    if (name === 'get_print_status') {
      const result=await getOwnerJob(env,owner,args.job_id);
      return mcpReply(payload.id,toolResult(result||{error:'not found'}));
    }
    if (name === 'cancel_queued_print') {
      const result=await cancelOwnerJob(env,owner,args.job_id);
      return mcpReply(payload.id,toolResult(result||{error:'not queued or not found'}));
    }
    return mcpError(payload.id,-32602,'Unknown tool');
  } catch(e) {
    return mcpReply(payload.id,{isError:true, content:[{type:'text',text:'Request rejected: '+String(e.message||'invalid').slice(0,180)}]});
  }
}

export async function handle(req, env, fetcher=fetch) {
  const url=new URL(req.url), path=url.pathname;
  if (path==='/healthz' && req.method==='GET') return jsonResponse({service:'karin-print',mode:'capture-only',real_printer:false});
  if (!env.DB || !env.DOCUMENTS) return jsonResponse({error:'storage bindings missing'},503);

  if (path.startsWith('/api/agent/')) {
    if (!await agentAuthorized(req,env)) return deny();
    if (path==='/api/agent/claim' && req.method==='POST') {
      const job=await claimNext(env);
      return jsonResponse({job});
    }
    const contentMatch=path.match(/^\/api\/agent\/jobs\/([^/]+)\/content$/);
    if (contentMatch && req.method==='GET' && validId(contentMatch[1])) {
      const item=await leasedContent(env,contentMatch[1],req.headers.get('x-lease-token')||'');
      if (!item) return jsonResponse({error:'lease expired or missing'},409);
      return new Response(item.item.body,{headers:noStoreHeaders({
        'content-type':item.content_type,'x-content-sha256':item.digest
      })});
    }
    const ackMatch=path.match(/^\/api\/agent\/jobs\/([^/]+)\/ack$/);
    if (ackMatch && req.method==='POST' && validId(ackMatch[1])) {
      const { digest }=await req.json();
      if (!/^[a-f0-9]{64}$/.test(digest||'')) return jsonResponse({error:'bad digest'},400);
      const ack=await ackCapture(env,ackMatch[1],req.headers.get('x-lease-token')||'',digest);
      return ack ? jsonResponse({job:ack}) : jsonResponse({error:'ack rejected; do not replay'},409);
    }
    return jsonResponse({error:'not found'},404);
  }

  let identity;
  try { identity=await browserIdentity(req,env,fetcher); }
  catch { return deny(); }
  const owner=identity.sub;

  if ((req.method==='POST'||req.method==='DELETE'||req.method==='PATCH') &&
      path!=='/mcp' && !mustHaveOrigin(req,url)) return jsonResponse({error:'origin not allowed'},403);
  try {
    if (path==='/' && req.method==='GET') {
      return new Response(UI,{headers:noStoreHeaders({'content-type':'text/html; charset=utf-8',
        'content-security-policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})});
    }
    if (path==='/mcp' && req.method==='POST') {
      // OAuth discovery/authorization still requires a separately verified custom MCP client setup.
      if (!req.headers.get('authorization')?.startsWith('Bearer ')) return deny();
      return mcp(req,env,owner,url);
    }
    if (path==='/api/prepare' && req.method==='POST') return jsonResponse(await createDraft(env,owner,req),201);
    if (path==='/api/jobs' && req.method==='GET') return jsonResponse({jobs:await listOwnerJobs(env,owner)});
    const match=path.match(/^\/api\/jobs\/([^/]+)(?:\/(confirm|cancel|preview))?$/);
    if (match && validId(match[1])) {
      const id=match[1],action=match[2];
      if (!action && req.method==='GET') {
        const job=await getOwnerJob(env,owner,id);
        return job ? jsonResponse({job}) : jsonResponse({error:'not found'},404);
      }
      if (action==='confirm' && req.method==='POST') {
        const body=await req.json();
        const job=await confirmDraft(env,owner,id,body.approval_token);
        return job ? jsonResponse({job}) : jsonResponse({error:'invalid/expired approval'},409);
      }
      if (action==='cancel' && req.method==='POST') {
        const job=await cancelOwnerJob(env,owner,id);
        return job ? jsonResponse({job}) : jsonResponse({error:'cannot cancel'},409);
      }
      if (action==='preview' && req.method==='GET') {
        const row=await env.DB.prepare('SELECT object_key,content_type,title FROM jobs WHERE owner=? AND id=?').bind(owner,id).first();
        if (!row) return jsonResponse({error:'not found'},404);
        const object=await env.DOCUMENTS.get(row.object_key);
        if (!object) return jsonResponse({error:'expired'},404);
        return new Response(object.body,{headers:noStoreHeaders({
          'content-type':row.content_type,
          'content-security-policy':"default-src 'none'; sandbox",
          'content-disposition':"inline; filename=\"preview\""
        })});
      }
    }
    return jsonResponse({error:'not found'},404);
  } catch(error) { return respondError(error); }
}
export default {
  fetch(req,env) {return handle(req,env);},
  async scheduled(_event,env) { await purgeExpired(env); }
};
