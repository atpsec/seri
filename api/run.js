const MODAL_ENDPOINT = 'https://tpberg3tp--akis-workflow-web.modal.run';

function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
}

module.exports = async function handler(req, res) {
  setCors(res);

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'Method not allowed' });
  }

  try {
    const payload = typeof req.body === 'string' ? JSON.parse(req.body) : (req.body || {});
    const upstream = await fetch(`${MODAL_ENDPOINT}/run`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const body = await upstream.text();
    res.status(upstream.status);
    res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/json');

    try {
      return res.send(JSON.parse(body));
    } catch {
      return res.send(body);
    }
  } catch (error) {
    return res.status(502).json({
      ok: false,
      error: 'Workflow service unavailable',
      detail: error instanceof Error ? error.message : 'Unknown upstream error',
    });
  }
};
