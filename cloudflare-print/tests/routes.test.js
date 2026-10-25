import test from 'node:test';
import assert from 'node:assert/strict';
import { handle } from '../src/index.js';

function fbytes(buf){return Buffer.from(buf).toString('base64url');}
async function context(){
  const keypair=await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
  const publicKey=await crypto.subtle.exportKey('jwk',keypair.publicKey);
  publicKey.kid='route-key';
  const env={ACCESS_TEAM_DOMAIN:'https://myteam.cloudflareaccess.com',ACCESS_AUD:'app-aud',AGENT_TOKEN:'s'.repeat(40),DB:{},DOCUMENTS:{}};
  const fetcher=async()=>({ok:true,json:async()=>({keys:[publicKey]})});
  const payload={iss:env.ACCESS_TEAM_DOMAIN,aud:[env.ACCESS_AUD],exp:Math.floor(Date.now()/1000)+120,sub:'signed-owner'};
  const header=fbytes(JSON.stringify({alg:'RS256',kid:'route-key'}));
  const claims=fbytes(JSON.stringify(payload));
  const signature=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',keypair.privateKey,new TextEncoder().encode(header+'.'+claims));
  return {env,fetcher,token:header+'.'+claims+'.'+fbytes(signature)};
}
test('health indicates capture-only; unsigned private UI is denied',async()=>{
  assert.equal((await (await handle(new Request('https://print.test/healthz'),{})).json()).real_printer,false);
  const c=await context();
  assert.equal((await handle(new Request('https://print.test/'),c.env,c.fetcher)).status,401);
  const spoof=new Request('https://print.test/',{headers:{'CF-Access-Jwt-Assertion':'not-a-signed-token'}});
  assert.equal((await handle(spoof,c.env,c.fetcher)).status,401);
});
test('signed owner can open responsive UI, private route enforces origin',async()=>{
  const c=await context();
  const headers={'CF-Access-Jwt-Assertion':c.token};
  const page=await handle(new Request('https://print.test/',{headers}),c.env,c.fetcher);
  assert.equal(page.status,200);
  assert.match(await page.text(),/Karin Print/);
  const noOrigin=await handle(new Request('https://print.test/api/prepare',{method:'POST',headers:{...headers,'content-type':'application/json'},body:'{}'}),c.env,c.fetcher);
  assert.equal(noOrigin.status,403);
  const crossOrigin=await handle(new Request('https://print.test/api/prepare',{method:'POST',headers:{...headers,origin:'https://evil.test','content-type':'application/json'},body:'{}'}),c.env,c.fetcher);
  assert.equal(crossOrigin.status,403);
});
test('MCP tools can be listed only with validated bearer Access JWT',async()=>{
  const c=await context();
  const params={method:'POST',headers:{Authorization:'Bearer '+c.token,'content-type':'application/json'},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/list'})};
  const result=await handle(new Request('https://print.test/mcp',params),c.env,c.fetcher);
  assert.equal(result.status,200);
  const tools=(await result.json()).result.tools;
  assert.deepEqual(tools.map(x=>x.name),['prepare_print','get_print_status','cancel_queued_print']);
  assert.equal(tools.some(t=>t.name==='confirm_print'),false);
  const broken=await handle(new Request('https://print.test/mcp',{...params,headers:{'content-type':'application/json'}}),c.env,c.fetcher);
  assert.equal(broken.status,401);
});
test('agent claim endpoint never accepts browser identity as agent credential',async()=>{
  const c=await context();
  const r=await handle(new Request('https://print.test/api/agent/claim',{method:'POST',headers:{Authorization:'Bearer '+c.token}}),c.env,c.fetcher);
  assert.equal(r.status,401);
});
