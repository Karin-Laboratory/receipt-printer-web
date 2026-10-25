const decoder = new TextDecoder();
const encoder = new TextEncoder();

export function decodeJwtPart(value) {
  if (!/^[A-Za-z0-9_-]+$/.test(value)) throw new Error('invalid JWT encoding');
  const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
  const bytes = Uint8Array.from(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')), c => c.charCodeAt(0));
  return bytes;
}

export async function verifyAccessJwt(token, env, fetcher = fetch, now = Date.now()) {
  if (!token || typeof token !== 'string' || token.length > 8192) throw new Error('missing access JWT');
  const parts = token.split('.');
  if (parts.length !== 3) throw new Error('invalid JWT structure');
  const header = JSON.parse(decoder.decode(decodeJwtPart(parts[0])));
  const claims = JSON.parse(decoder.decode(decodeJwtPart(parts[1])));
  if (header.alg !== 'RS256' || !header.kid || typeof header.kid !== 'string') throw new Error('unsupported JWT header');
  const team = String(env.ACCESS_TEAM_DOMAIN || '');
  if (!/^https:\/\/[a-z0-9-]+\.cloudflareaccess\.com$/i.test(team)) throw new Error('invalid Access team domain');
  const audience = String(env.ACCESS_AUD || '');
  if (!audience || claims.iss !== team || ![].concat(claims.aud || []).includes(audience) ||
      !claims.sub || !Number.isFinite(claims.exp) || claims.exp * 1000 <= now ||
      (claims.nbf && claims.nbf * 1000 > now + 30000)) throw new Error('invalid JWT claims');
  const certs = await fetcher(team + '/cdn-cgi/access/certs');
  if (!certs.ok) throw new Error('cannot obtain signing keys');
  const jwks = await certs.json();
  const jwk = (jwks.keys || []).find(k => k.kid === header.kid && k.kty === 'RSA' && (!k.alg || k.alg === 'RS256'));
  if (!jwk) throw new Error('unrecognized signing key');
  const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const signature = decodeJwtPart(parts[2]);
  const valid = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, signature, encoder.encode(parts[0] + '.' + parts[1]));
  if (!valid) throw new Error('invalid JWT signature');
  return { sub: claims.sub, email: typeof claims.email === 'string' ? claims.email : '' };
}

export async function browserIdentity(req, env, fetcher = fetch) {
  const bearer = req.headers.get('Authorization') || '';
  const token = bearer.startsWith('Bearer ') ? bearer.slice(7) : req.headers.get('CF-Access-Jwt-Assertion');
  return verifyAccessJwt(token, env, fetcher);
}

export async function agentAuthorized(req, env) {
  const supplied = req.headers.get('Authorization');
  const expected = String(env.AGENT_TOKEN || '');
  if (!expected || expected.length < 32 || !supplied || !supplied.startsWith('Bearer ')) return false;
  const candidate = supplied.slice(7);
  const a = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(candidate)));
  const b = new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(expected)));
  let mismatch = candidate.length === expected.length ? 0 : 1;
  for (let i = 0; i < a.length; i++) mismatch |= a[i] ^ b[i];
  return mismatch === 0;
}

export async function sha256Hex(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))).map(v => v.toString(16).padStart(2, '0')).join('');
}

export function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' }
  });
}

export function deny() {
  return jsonResponse({ error: 'unauthorized' }, 401);
}
