import { sha256Hex } from './security.js';

const textEncoder = new TextEncoder();
const MAX_SIZE = 1024 * 1024;
const ALLOWED = new Set(['text/plain', 'text/markdown', 'application/pdf', 'image/png', 'image/jpeg']);
const PUBLIC_COLUMNS = 'id, title, content_type, bytes, state, created_at, updated_at, expires_at, lease_until, attempts';

function randomId() { return crypto.randomUUID(); }
export function safeTitle(title) { return String(title || 'Untitled').replace(/[\x00-\x1f\x7f]/g, ' ').slice(0, 120); }
function asPublic(row) {
  if (!row) return null;
  return Object.fromEntries(['id','title','content_type','bytes','state','created_at','updated_at','expires_at','lease_until','attempts'].map(k => [k, row[k] ?? null]));
}
export async function inspectUpload(req) {
  let type = (req.headers.get('content-type') || '').split(';')[0].toLowerCase();
  let title = safeTitle(req.headers.get('x-document-title'));
  let content;
  if (type === 'application/json') {
    const input = await req.json();
    if (!input || !['text/plain','text/markdown'].includes(input.format) || typeof input.content !== 'string') throw new Error('unsupported content');
    content = textEncoder.encode(input.content);
    type = input.format;
    title = safeTitle(input.title);
  } else if (ALLOWED.has(type)) {
    content = new Uint8Array(await req.arrayBuffer());
  } else throw new Error('unsupported media type');
  if (!content.length || content.length > MAX_SIZE) throw new Error('document size invalid');
  if (type === 'application/pdf' && new TextDecoder().decode(content.subarray(0, 5)) !== '%PDF-') throw new Error('invalid PDF');
  if (type === 'image/png' && ![137,80,78,71,13,10,26,10].every((v,i)=>content[i]===v)) throw new Error('invalid PNG');
  if (type === 'image/jpeg' && !(content[0]===255 && content[1]===216 && content[2]===255)) throw new Error('invalid JPEG');
  return { type, title, content };
}

export async function createDraft(env, owner, req, clock = Date.now()) {
  const key = req.headers.get('idempotency-key');
  if (key && !/^[A-Za-z0-9_-]{8,100}$/.test(key)) throw new Error('invalid idempotency key');
  if (key) {
    const previous = await env.DB.prepare('SELECT ' + PUBLIC_COLUMNS + ' FROM jobs WHERE owner=? AND client_key=?').bind(owner, key).first();
    if (previous) return { job: asPublic(previous), already_exists: true, approval_token: null };
  }
  const { type, title, content } = await inspectUpload(req);
  const id = randomId(), token = randomId() + randomId(), object = 'jobs/' + id;
  const digest = await sha256Hex(content);
  const approvalDigest = await sha256Hex(textEncoder.encode(token));
  const expires = clock + 15 * 60 * 1000;
  await env.DOCUMENTS.put(object, content, { httpMetadata: { contentType: type } });
  try {
    await env.DB.prepare('INSERT INTO jobs (id,owner,client_key,title,content_type,bytes,digest,object_key,approval_hash,state,created_at,updated_at,expires_at,attempts) VALUES(?,?,?,?,?,?,?,?,?,\'draft\',?,?,?,0)')
      .bind(id,owner,key,title,type,content.length,digest,object,approvalDigest,clock,clock,expires).run();
  } catch (err) {
    await env.DOCUMENTS.delete(object);
    if (key) {
      const previous = await env.DB.prepare('SELECT ' + PUBLIC_COLUMNS + ' FROM jobs WHERE owner=? AND client_key=?').bind(owner, key).first();
      if (previous) return { job: asPublic(previous), already_exists: true, approval_token: null };
    }
    throw err;
  }
  return { job: {id,title,content_type:type,bytes:content.length,state:'draft',created_at:clock,updated_at:clock,expires_at:expires,lease_until:null,attempts:0},
    approval_token:token, already_exists:false };
}

export async function confirmDraft(env, owner, id, token, clock = Date.now()) {
  if (typeof token !== 'string' || token.length > 256) return null;
  const digest = await sha256Hex(textEncoder.encode(token));
  const row = await env.DB.prepare('UPDATE jobs SET state=\'queued\',updated_at=?,expires_at=?,approval_hash=NULL WHERE id=? AND owner=? AND state=\'draft\' AND expires_at>? AND approval_hash=? RETURNING ' + PUBLIC_COLUMNS)
       .bind(clock, clock + 24*60*60*1000, id, owner, clock, digest).first();
  return asPublic(row);
}

export async function getOwnerJob(env, owner, id) {
  return asPublic(await env.DB.prepare('SELECT ' + PUBLIC_COLUMNS + ' FROM jobs WHERE owner=? AND id=?').bind(owner,id).first());
}
export async function listOwnerJobs(env, owner) {
  const result = await env.DB.prepare('SELECT ' + PUBLIC_COLUMNS + ' FROM jobs WHERE owner=? ORDER BY created_at DESC LIMIT 30').bind(owner).all();
  return (result.results || []).map(asPublic);
}
export async function cancelOwnerJob(env, owner, id, clock = Date.now()) {
  const row = await env.DB.prepare('UPDATE jobs SET state=\'cancelled\',updated_at=? WHERE id=? AND owner=? AND state IN (\'draft\',\'queued\') RETURNING ' + PUBLIC_COLUMNS).bind(clock,id,owner).first();
  return asPublic(row);
}
export async function markExpiredLeases(env, clock = Date.now()) {
  await env.DB.prepare('UPDATE jobs SET state=\'uncertain\',updated_at=? WHERE state=\'leased\' AND lease_until<?').bind(clock,clock).run();
}
export async function claimNext(env, clock = Date.now()) {
  await markExpiredLeases(env, clock);
  const lease = randomId();
  const row = await env.DB.prepare('UPDATE jobs SET state=\'leased\',lease_id=?,lease_until=?,updated_at=?,attempts=attempts+1 WHERE id=(SELECT id FROM jobs WHERE state=\'queued\' AND expires_at>? ORDER BY created_at LIMIT 1) AND state=\'queued\' RETURNING id,title,content_type,bytes,digest,lease_until,attempts')
    .bind(lease,clock+120000,clock,clock).first();
  if (!row) return null;
  return {...row, lease_id:lease};
}
export async function leasedContent(env, id, lease, clock = Date.now()) {
  const row = await env.DB.prepare('SELECT object_key,content_type,digest FROM jobs WHERE id=? AND lease_id=? AND state=\'leased\' AND lease_until>?')
    .bind(id,lease,clock).first();
  if (!row) return null;
  const item = await env.DOCUMENTS.get(row.object_key);
  return item ? { item, digest:row.digest, content_type:row.content_type } : null;
}
export async function ackCapture(env, id, lease, digest, clock = Date.now()) {
  return await env.DB.prepare('UPDATE jobs SET state=\'captured\',lease_id=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_id=? AND digest=? AND state=\'leased\' AND lease_until>? RETURNING id,state,updated_at')
    .bind(clock,id,lease,digest,clock).first();
}
export async function purgeExpired(env, clock = Date.now()) {
  await markExpiredLeases(env, clock);
  const rows = await env.DB.prepare('SELECT id,object_key FROM jobs WHERE expires_at<? AND state NOT IN (\'leased\') LIMIT 100').bind(clock).all();
  let count = 0;
  for (const row of rows.results || []) {
    await env.DOCUMENTS.delete(row.object_key);
    await env.DB.prepare('DELETE FROM jobs WHERE id=? AND state!=?').bind(row.id,'leased').run();
    count++;
  }
  return count;
}
