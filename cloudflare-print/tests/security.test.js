import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { verifyAccessJwt, browserIdentity, agentAuthorized } from '../src/security.js';
import { inspectUpload, safeTitle } from '../src/store.js';

const enc=new TextEncoder();
const b64=(buf)=>Buffer.from(buf).toString('base64url');
async function jwtFixture() {
  const keys=await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
  const jwk=await crypto.subtle.exportKey('jwk',keys.publicKey);jwk.kid='test-key';
  const team='https://test-team.cloudflareaccess.com';
  async function sign(claims,alg='RS256') {
    const head=b64(enc.encode(JSON.stringify({alg,kid:'test-key'})));
    const body=b64(enc.encode(JSON.stringify(claims)));
    const data=enc.encode(head+'.'+body);
    const sig=await crypto.subtle.sign('RSASSA-PKCS1-v1_5',keys.privateKey,data);
    return head+'.'+body+'.'+b64(sig);
  }
  const now=Date.now();
  const claims={iss:team,aud:['test-audience'],exp:Math.floor(now/1000)+180,sub:'user-1',email:'u@example.test'};
  return {env:{ACCESS_TEAM_DOMAIN:team,ACCESS_AUD:'test-audience',AGENT_TOKEN:'q'.repeat(40)},
          fetcher:async()=>({ok:true,json:async()=>({keys:[jwk]})}),sign,claims};
}

test('signed Cloudflare Access JWT accepted; identity extracted', async()=>{
  const f=await jwtFixture();
  const token=await f.sign(f.claims);
  assert.equal((await verifyAccessJwt(token,f.env,f.fetcher)).sub,'user-1');
  assert.equal((await browserIdentity(new Request('https://print.example.test/',{headers:{'CF-Access-Jwt-Assertion':token}}),f.env,f.fetcher)).email,'u@example.test');
});
test('expired, wrong audience, bad signature and none algorithm refused',async()=>{
  const f=await jwtFixture();
  for(const claims of [{...f.claims,exp:1},{...f.claims,aud:['wrong']},{...f.claims,iss:'https://wrong.cloudflareaccess.com'}]){
    await assert.rejects(verifyAccessJwt(await f.sign(claims),f.env,f.fetcher));
  }
  await assert.rejects(verifyAccessJwt(await f.sign(f.claims,'none'),f.env,f.fetcher));
  const valid=await f.sign(f.claims);
  await assert.rejects(verifyAccessJwt(valid.slice(0,-2)+'xy',f.env,f.fetcher));
});
test('agent bearer token required and distinct from browser token',async()=>{
  const env={AGENT_TOKEN:'r'.repeat(40)};
  assert.equal(await agentAuthorized(new Request('https://x.test/',{headers:{Authorization:'Bearer '+env.AGENT_TOKEN}}),env),true);
  assert.equal(await agentAuthorized(new Request('https://x.test/',{headers:{Authorization:'Bearer wrong'}}),env),false);
  assert.equal(await agentAuthorized(new Request('https://x.test/'),env),false);
});
test('upload validation rejects invalid PDF, oversize, dangerous format',async()=>{
  const valid=await inspectUpload(new Request('https://x.test/',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({format:'text/plain',title:'hello',content:'日本語'})}));
  assert.equal(valid.type,'text/plain');assert.equal(valid.content.length,9);
  await assert.rejects(inspectUpload(new Request('https://x.test/',{method:'POST',headers:{'content-type':'application/pdf'},body:'not a PDF'})));
  await assert.rejects(inspectUpload(new Request('https://x.test/',{method:'POST',headers:{'content-type':'text/html'},body:'<script>bad</script>'})));
  await assert.rejects(inspectUpload(new Request('https://x.test/',{method:'POST',headers:{'content-type':'application/pdf'},body:new Uint8Array(1048577)})));
  assert.equal(safeTitle('A\nB'),'A B');
});
