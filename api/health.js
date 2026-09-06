const MODAL_ENDPOINT = 'https://tpberg3tp--akis-workflow-web.modal.run';

module.exports = async function handler(_req, res) {
  try {
    const upstream = await fetch(`${MODAL_ENDPOINT}/health`);
    const body = await upstream.text();
    res.status(upstream.status);
    res.setHeader('Content-Type', upstream.headers.get('content-type') || 'application/json');
    return res.send(body);
  } catch (error) {
    return res.status(502).json({
      status: 'error',
      error: error instanceof Error ? error.message : 'Unknown upstream error',
    });
  }
};
