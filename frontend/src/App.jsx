import React, { useState, useRef } from 'react'
import UploadZoneEditor from './components/UploadZoneEditor'
import AuditImage from './components/AuditImage'
import FindingsList from './components/FindingsList'
import Banner from './components/Banner'
import { analyzeImage } from './api/auditClient'

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
  const [timeoutMessage, setTimeoutMessage] = useState(false)
  const currentSnapshotRef = useRef(null)

  React.useEffect(() => {
    setAudit(null)
    setDecisions({})
    setSelectedId(null)
    setFilters({ severity: 'all', zone: 'all' })
    setError(null)
    setTimeoutMessage(false)
    if (abortController) {
      abortController.abort()
    }
  }, [image, sample, zones])

  const getSnapshot = () => {
    return JSON.stringify({ imageName: image?.name, imageSize: image?.size, zones, sampleId: sample?.id })
  }

  const handleAnalyse = async () => {
    setLoading(true)
    setError(null)
    setAudit(null)
    setTimeoutMessage(false)
    const controller = new AbortController()
    setAbortController(controller)
    const snapshot = getSnapshot()
    currentSnapshotRef.current = snapshot
    
    const timeoutId = setTimeout(() => {
      setTimeoutMessage(true)
    }, 60000)
    
    try {
      const result = await analyzeImage({ file: image, zones, sampleId: sample?.id ?? null }, { signal: controller.signal, snapshot })
      clearTimeout(timeoutId)
      // Discard if snapshot no longer matches
      if (currentSnapshotRef.current !== snapshot) {
        return
      }
      setAudit(result.audit || result)
    } catch (err) {
      clearTimeout(timeoutId)
      if (currentSnapshotRef.current !== snapshot) {
        return
      }
      if (err.name === 'AbortError') {
        setError('Analysis cancelled')
      } else {
        setError(err.message)
      }
    } finally {
      clearTimeout(timeoutId)
      setLoading(false)
      setAbortController(null)
    }
  }

  const handleCancel = () => {
    if (abortController) {
      abortController.abort()
    }
  }

  const isFromFixture = !!sample && !!audit

  return (
    <div className="app">
      <header className="topbar">
        <h1>Vigilens</h1>
        <span className="mode-badge">Mode: fixture</span>
      </header>
      <Banner fromFixture={isFromFixture} />
      
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
              {timeoutMessage && <p style={{ color: 'var(--medium)' }}>No response yet; the audit may still be running</p>}
              <button className="btn btn-secondary" onClick={handleCancel}>Cancel</button>
              {timeoutMessage && <button className="btn" onClick={handleAnalyse} style={{ marginLeft: '0.5rem' }}>Try again</button>}
            </div>
          )}
          {error && (
            <div className="card">
              <p style={{ color: 'var(--critical)' }}>{error}</p>
              {error !== 'Analysis cancelled' && <button className="btn" onClick={handleAnalyse}>Retry</button>}
            </div>
          )}
          {audit && !loading && (
            <>
              <AuditImage 
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
