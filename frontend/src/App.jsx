import React, { useState, useRef, useEffect } from 'react'
import UploadZoneEditor from './components/UploadZoneEditor'
import AuditImage from './components/AuditImage'
import FindingsList from './components/FindingsList'
import Banner from './components/Banner'
import { analyzeImage, checkHealth } from './api/auditClient'

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
  const requestInFlightRef = useRef(false)
  const [idempotencyKey, setIdempotencyKey] = useState(null)
  const [healthBanner, setHealthBanner] = useState(null)
  const [uploadedNaturalSize, setUploadedNaturalSize] = useState(null)

  const isFixtureMode = (import.meta.env.VITE_AUDIT_MODE || 'fixture') === 'fixture'
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

  useEffect(() => {
    if (!isFixtureMode) {
      checkHealth(baseUrl).then(result => {
        if (!result.ok) {
          setHealthBanner('Backend not reachable')
        } else {
          const data = result.data
          if (data.mode === 'fixture_only' || data.real_analysis_enabled === false) {
            setHealthBanner('Backend is in fixture-only mode: no real analysis')
          } else if (data.fixture_configured === false) {
            setHealthBanner('No paired fixture configured')
          }
        }
      })
    }
  }, [])

  useEffect(() => {
    setAudit(null)
    setDecisions({})
    setSelectedId(null)
    setFilters({ severity: 'all', zone: 'all' })
    setError(null)
    setTimeoutMessage(false)
    setIdempotencyKey(crypto.randomUUID())
    if (image) {
      const img = new Image()
      img.src = URL.createObjectURL(image)
      img.onload = () => {
        setUploadedNaturalSize({ width: img.naturalWidth, height: img.naturalHeight })
      }
    } else {
      setUploadedNaturalSize(null)
    }
    if (abortController) {
      abortController.abort()
    }
  }, [image, sample, zones])

  const getSnapshot = () => {
    return JSON.stringify({ imageName: image?.name, imageSize: image?.size, zones, sampleId: sample?.id })
  }

  const handleAnalyse = async () => {
    if (requestInFlightRef.current || loading) return
    requestInFlightRef.current = true
    setLoading(true)
    setError(null)
    setAudit(null)
    setTimeoutMessage(false)
    const controller = new AbortController()
    setAbortController(controller)
    const snapshot = getSnapshot()
    currentSnapshotRef.current = snapshot
    const key = idempotencyKey || crypto.randomUUID()
    if (!idempotencyKey) setIdempotencyKey(key)
    
    const timeoutId = setTimeout(() => {
      setTimeoutMessage(true)
    }, 60000)
    
    try {
      const result = await analyzeImage({ file: image, zones, sampleId: sample?.id ?? null }, { signal: controller.signal, snapshot, idempotencyKey: key })
      clearTimeout(timeoutId)
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
      requestInFlightRef.current = false
    }
  }

  const handleTryAgain = () => {
    // Reuse same idempotency key
    handleAnalyse()
  }

  const handleCancel = () => {
    if (abortController) {
      abortController.abort()
    }
  }

  const showFixtureBanner = !!sample && !!audit && isFixtureMode
  const evidenceExportAllowed = audit && audit.evidence_export_allowed === true && audit.source !== 'fixture'

  return (
    <div className="app">
      <header className="topbar">
        <h1>Vigilens</h1>
        <span className="mode-badge">Mode: {isFixtureMode ? 'fixture' : 'backend'}</span>
      </header>
      {healthBanner && <div className="banner" style={{ background: '#f87171', color: '#7f1d1d' }}>{healthBanner}</div>}
      <Banner fromFixture={showFixtureBanner} fixtureNotice={audit?.fixture_notice} />
      
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
            loading={loading}
          />
        </div>
        <div>
          {loading && (
            <div className="card">
              <p>Analyzing...</p>
              {timeoutMessage && <p style={{ color: 'var(--medium)' }}>No response yet; the audit may still be running</p>}
              <button className="btn btn-secondary" onClick={handleCancel}>Cancel</button>
              {timeoutMessage && !requestInFlightRef.current && <button className="btn" onClick={handleTryAgain} style={{ marginLeft: '0.5rem' }}>Try again</button>}
            </div>
          )}
          {error && (
            <div className="card">
              <p style={{ color: 'var(--critical)' }}>{error}</p>
              {error !== 'Analysis cancelled' && !loading && <button className="btn" onClick={handleTryAgain}>Try again</button>}
            </div>
          )}
          {audit && !loading && (
            <>
              <AuditImage 
                audit={audit}
                selectedId={selectedId}
                onSelectPerson={setSelectedId}
                uploadedNaturalSize={uploadedNaturalSize}
              />
              <FindingsList 
                audit={audit}
                selectedId={selectedId}
                onSelectPerson={setSelectedId}
              />
              {showFixtureBanner && <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>Evidence export disabled</p>}
              {audit.fixture_loaded_at && <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>fixture loaded at: {audit.fixture_loaded_at}</p>}
              {audit.created_at && !audit.fixture_loaded_at && <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Created: {audit.created_at}</p>}
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
