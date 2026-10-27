import React, { useState } from 'react'
import UploadZoneEditor from './components/UploadZoneEditor'
import AuditImage from './components/AuditImage'
import FindingsList from './components/FindingsList'
import Banner from './components/Banner'
import { analyzeImage } from './api/auditClient'
import { resolveEvidence } from './lib/evidence'

function App() {
  const [image, setImage] = useState(null)
  const [zones, setZones] = useState([])
  const [audit, setAudit] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [filters, setFilters] = useState({ severity: 'all', zone: 'all' })
  const [sample, setSample] = useState(null)
  const [runWithoutZones, setRunWithoutZones] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [abortController, setAbortController] = useState(null)

  React.useEffect(() => {
    setAudit(null)
    setDecisions({})
    setSelectedId(null)
    setFilters({ severity: 'all', zone: 'all' })
    setError(null)
  }, [image, sample, zones])

  const handleAnalyse = async () => {
    setLoading(true)
    setError(null)
    setAudit(null)
    const controller = new AbortController()
    setAbortController(controller)
    try {
      const result = await analyzeImage({ file: image, zones, sampleId: sample?.id ?? null }, { signal: controller.signal })
      setAudit(result)
    } catch (err) {
      if (err.name === 'AbortError') {
        setError('Analysis cancelled')
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
      setAbortController(null)
    }
  }

  const handleCancel = () => {
    if (abortController) {
      abortController.abort()
    }
  }

  const isFromFixture = !!sample

  return (
    <div className="app">
      <header className="topbar">
        <h1>Vigilens</h1>
        <span className="mode-badge">Mode: fixture</span>
      </header>
      <Banner fromFixture={isFromFixture && audit} />
      
      <main className="main">
        <div>
          <UploadZoneEditor
            image={image}
            setImage={setImage}
            zones={zones}
            setZones={setZones}
            sample={sample}
            setSample={setSample}
            runWithoutZones={runWithoutZones}
            setRunWithoutZones={setRunWithoutZones}
            onAnalyse={handleAnalyse}
          />
        </div>
        <div>
          {loading && (
            <div className="card">
              <p>Analyzing...</p>
              <button className="btn btn-secondary" onClick={handleCancel}>Cancel</button>
            </div>
          )}
          {error && (
            <div className="card">
              <p style={{ color: 'var(--critical)' }}>Error: {error}</p>
              <button className="btn" onClick={handleAnalyse}>Retry</button>
            </div>
          )}
          {audit && !loading && (
            <>
              <AuditImage 
                imageSrc={resolveEvidence(audit, image ? URL.createObjectURL(image) : '').src}
                audit={audit}
                selectedId={selectedId}
                onSelectPerson={setSelectedId}
              />
              <FindingsList 
                audit={audit}
                selectedId={selectedId}
                onSelectPerson={setSelectedId}
              />
            </>
          )}
          {!audit && !loading && !error && (
            <div className="card">
              <h2>Results</h2>
              <p style={{color: 'var(--text-muted)'}}>Run analysis to see results</p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
