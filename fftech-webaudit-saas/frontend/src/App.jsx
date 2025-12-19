import React, { useState } from 'react'

const API = import.meta.env.VITE_API_URL || '/audits'

export default function App(){
  const [url, setUrl] = useState('https://example.com')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const runAudit = async () => {
    setLoading(true)
    try {
      const res = await fetch('/audits', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) })
      const json = await res.json()
      setResult(json)
    } catch (e) { alert(e.message) }
    setLoading(false)
  }

  return (
    <>
      <div className="card">
        <h2>Run Website Audit</h2>
        <p>Enter a URL and click Audit. You will get an overall grade and metrics.</p>
        <input value={url} onChange={(e)=>setUrl(e.target.value)} placeholder="https://" />
        <button onClick={runAudit} disabled={loading}>{loading ? 'Auditing...' : 'Audit'}</button>
      </div>
      {result && (
        <div className="card">
          <h3>Result</h3>
          <pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </>
  )
}
