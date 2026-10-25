import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { createDraft, confirmDraft, getOwnerJob, listOwnerJobs, cancelOwnerJob,
         claimNext, leasedContent, ackCapture, purgeExpired } from '../src/store.js';

class MemoryD1 {
  constructor(){this.jobs=[];}
  prepare(sql) {
    const db=this;
    return {bind(...args) {
      return {
        async run(){return this.first()},
        async first(){
          const records=db.jobs;
          if(sql.startsWith('INSERT INTO jobs')){
            const [id,owner,client_key,title,content_type,bytes,digest,object_key,approval_hash,created_at,updated_at,expires_at]=args;
            if(client_key&&records.some(r=>r.owner===owner&&r.client_key===client_key))throw Error('UNIQUE constraint');
            records.push({id,owner,client_key,title,content_type,bytes,digest,object_key,approval_hash,created_at,updated_at,expires_at,state:'draft',attempts:0,lease_id:null,lease_until:null});
            return {success:true};
          }
          if(sql.includes('WHERE owner=? AND client_key=?'))return records.find(r=>r.owner===args[0]&&r.client_key===args[1])||null;
          if(sql.startsWith('UPDATE jobs SET state=\'queued\'')){
            const [now,expiry,id,owner,deadline,digest]=args;
            const row=records.find(r=>r.id===id&&r.owner===owner&&r.state==='draft'&&r.expires_at>deadline&&r.approval_hash===digest);
            if(!row)return null;Object.assign(row,{state:'queued',updated_at:now,expires_at:expiry,approval_hash:null});return {...row};
          }
          if(sql.startsWith('UPDATE jobs SET state=\'cancelled\'')){
            const [now,id,owner]=args;
            const row=records.find(r=>r.id===id&&r.owner===owner&&['draft','queued'].includes(r.state));
            if(!row)return null;Object.assign(row,{state:'cancelled',updated_at:now});return {...row};
          }
          if(sql.startsWith('SELECT object_key,content_type,digest')) {
            const [id,lease,now]=args;
            return records.find(r=>r.id===id&&r.lease_id===lease&&r.state==='leased'&&r.lease_until>now)||null;
          }
          if(sql.startsWith('UPDATE jobs SET state=\'uncertain\'')){
            const [now,expiry]=args;for(const r of records)if(r.state==='leased'&&r.lease_until<expiry){r.state='uncertain';r.updated_at=now;}return {success:true};
          }
          if(sql.startsWith('UPDATE jobs SET state=\'leased\'')){
            const [lease,until,now,minExpiry]=args;
            const row=records.filter(r=>r.state==='queued'&&r.expires_at>minExpiry).sort((a,b)=>a.created_at-b.created_at)[0];
            if(!row)return null;Object.assign(row,{state:'leased',lease_id:lease,lease_until:until,updated_at:now,attempts:row.attempts+1});return {...row};
          }
          if(sql.startsWith('UPDATE jobs SET state=\'captured\'')){
            const [now,id,lease,digest,validAt]=args;
            const row=records.find(r=>r.id===id&&r.state==='leased'&&r.lease_id===lease&&r.digest===digest&&r.lease_until>validAt);
            if(!row)return null;Object.assign(row,{state:'captured',lease_until:null,lease_id:null,updated_at:now});return {...row};
          }
          if(sql.startsWith('DELETE FROM jobs')){const at=records.findIndex(r=>r.id===args[0]&&r.state!=='leased');if(at!==-1)records.splice(at,1);return {success:true};}
          if(sql.includes('WHERE owner=? AND id=?'))return records.find(r=>r.owner===args[0]&&r.id===args[1])||null;
          throw Error('Unexpected SQL: '+sql);
        },
        async all(){
          if(sql.includes('WHERE owner=? ORDER BY'))return {results:db.jobs.filter(r=>r.owner===args[0]).sort((a,b)=>b.created_at-a.created_at).slice(0,30)};
          if(sql.includes('WHERE expires_at<?'))return {results:db.jobs.filter(r=>r.expires_at<args[0]&&r.state!=='leased').slice(0,100)};
          throw Error('Unexpected SQL all');
        }
      };
    }};
  }
}
class MemoryR2 {
  constructor(){this.data=new Map();}
  async put(k,v){this.data.set(k,Uint8Array.from(v));}
  async get(k){const b=this.data.get(k);return b?{body:new Blob([b]),bytes:b}:null;}
  async delete(k){this.data.delete(k);}
}
const env=()=>({DB:new MemoryD1(),DOCUMENTS:new MemoryR2()});
function request(content='hello',key='client-12345678'){
 return new Request('https://print.test/api/prepare',{method:'POST',headers:{'content-type':'application/json','idempotency-key':key},body:JSON.stringify({content,format:'text/plain',title:'Test'})});
}
test('draft remains unprintable until one valid confirmation',async()=>{
 const e=env(), now=10000;
 const staged=await createDraft(e,'alice',request(),now);
 assert.equal(staged.job.state,'draft');
 assert.equal(await claimNext(e,now+1),null);
 assert.equal(await confirmDraft(e,'bob',staged.job.id,staged.approval_token,now+1),null);
 assert.equal(await confirmDraft(e,'alice',staged.job.id,'incorrect',now+1),null);
 const queued=await confirmDraft(e,'alice',staged.job.id,staged.approval_token,now+1);
 assert.equal(queued.state,'queued');
 assert.equal(await confirmDraft(e,'alice',staged.job.id,staged.approval_token,now+2),null);
 assert.equal((await listOwnerJobs(e,'alice')).length,1);
 assert.equal((await listOwnerJobs(e,'bob')).length,0);
});
test('idempotent prepare, atomic single claim, hash-bound ack',async()=>{
 const e=env(), now=20000;
 const first=await createDraft(e,'alice',request(),now);
 const repeated=await createDraft(e,'alice',request(),now+1);
 assert.equal(repeated.already_exists,true);
 assert.equal(repeated.job.id,first.job.id);
 await confirmDraft(e,'alice',first.job.id,first.approval_token,now+10);
 const claims=await Promise.all([claimNext(e,now+20),claimNext(e,now+20)]);
 assert.equal(claims.filter(Boolean).length,1);
 const lease=claims.find(Boolean);
 assert.equal(lease.attempts,1);
 assert.equal(await leasedContent(e,lease.id,'bad-lease',now+25),null);
 const payload=await leasedContent(e,lease.id,lease.lease_id,now+25);
 assert.ok(payload);
 assert.equal(await ackCapture(e,lease.id,lease.lease_id,'0'.repeat(64),now+30),null);
 assert.equal((await ackCapture(e,lease.id,lease.lease_id,lease.digest,now+30)).state,'captured');
 assert.equal(await ackCapture(e,lease.id,lease.lease_id,lease.digest,now+31),null);
 assert.equal((await getOwnerJob(e,'alice',lease.id)).state,'captured');
 assert.equal(await cancelOwnerJob(e,'alice',lease.id,now+40),null);
});
test('expired lease becomes uncertain and never auto-requeued',async()=>{
 const e=env(),now=2000,staged=await createDraft(e,'alice',request(),now);
 await confirmDraft(e,'alice',staged.job.id,staged.approval_token,now+1);
 const lease=await claimNext(e,now+2);
 assert.ok(lease);
 assert.equal(await claimNext(e,now+120003),null);
 assert.equal((await getOwnerJob(e,'alice',lease.id)).state,'uncertain');
 assert.equal(await ackCapture(e,lease.id,lease.lease_id,lease.digest,now+120003),null);
});
test('cancelled jobs never claim; cleanup destroys stored source',async()=>{
 const e=env(),now=3000,staged=await createDraft(e,'alice',request(),now);
 assert.equal((await cancelOwnerJob(e,'alice',staged.job.id,now+1)).state,'cancelled');
 assert.equal(await claimNext(e,now+2),null);
 assert.equal(await purgeExpired(e,now+16*60*1000),1);
 assert.equal(e.DOCUMENTS.data.size,0);
 assert.equal((await listOwnerJobs(e,'alice')).length,0);
});
