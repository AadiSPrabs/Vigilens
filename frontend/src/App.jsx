import React, { useState, useRef, useEffect } from 'react'
import UploadZoneEditor from './components/UploadZoneEditor'
import AuditImage from './components/AuditImage'
import FindingsList from './components/FindingsList'
import HazardLog from './components/HazardLog'
import Banner from './components/Banner'
import ThemeToggle from './components/ThemeToggle'
import { AlertIcon, CameraFrameIcon } from './components/Icons'
import { analyzeImage, checkHealth } from './api/auditClient'
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
  const [timeoutMessage, setTimeoutMessage] = useState(false)
  const currentSnapshotRef = useRef(null)
  const requestInFlightRef = useRef(false)
  const [idempotencyKey, setIdempotencyKey] = useState(null)
  const [healthBanner, setHealthBanner] = useState(null)
  const [uploadedNaturalSize, setUploadedNaturalSize] = useState(null)
  const [announce, setAnnounce] = useState('')
  const [activeTab, setActiveTab] = useState('findings')

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
    setAnnounce('Analysis starting')
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
      setAnnounce('Analysis complete')
    } catch (err) {
      clearTimeout(timeoutId)
      if (currentSnapshotRef.current !== snapshot) {
        return
      }
      if (err.name === 'AbortError') {
        setError('Analysis cancelled')
      } else {
        setError(err.message)
        setAnnounce('Analysis error')
      }
    } finally {
      clearTimeout(timeoutId)
      setLoading(false)
      setAbortController(null)
      requestInFlightRef.current = false
    }
  }

  const handleTryAgain = () => {
    handleAnalyse()
  }

  const handleCancel = () => {
    if (abortController) {
      abortController.abort()
    }
  }

  const handlePrint = () => {
    if (typeof window !== 'undefined') window.print()
  }

  const showFixtureBanner = !!sample && !!audit && isFixtureMode
  const evidence = audit ? resolveEvidence(audit) : null
  const evidenceUnavailable = !!audit && !!evidence && !evidence.ok
  const showAuditImage = !!audit && !loading && !!evidence?.ok
  const allFindings = audit && Array.isArray(audit.persons)
    ? audit.persons.flatMap(person => Array.isArray(person.findings) ? person.findings : [])
    : []
  const totalFindings = allFindings.length
  const criticalFindings = allFindings.filter(finding => finding.kind !== 'uncertainty' && finding.severity === 'Critical').length

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          <h1>Vigilens</h1>
        </div>
        <div className="topbar-actions">
          <span className="mode-badge">{isFixtureMode ? 'Fixture mode' : 'Backend'}</span>
          <ThemeToggle />
          {audit && !loading && (
            <button
              type="button"
              className="btn btn-ghost topbar-action"
              onClick={handlePrint}
              aria-label="Export audit report"
            >
              Export PDF
            </button>
          )}
        </div>
      </header>
      <div className="banner-stack">
        <Banner fromFixture={showFixtureBanner} fixtureNotice={audit?.fixture_notice} />
        {healthBanner && (
          <div className="notice notice--danger" role="status" aria-live="polite">
            <AlertIcon size={16} className="notice__icon" />
            <span className="notice__text">{healthBanner}</span>
          </div>
        )}
      </div>
      <div aria-live="polite" aria-atomic="true" className="sr-only">{announce}</div>

      {audit && !loading && (
        <div className="print-header">
          <h1>VIGILENS | SITE SAFETY AUDIT REPORT</h1>
          <div className="print-meta">
            <span>Audit ID: {audit.audit_id || audit.id || 'Not provided'}</span>
            <span>
              {audit.fixture_loaded_at
                ? `Fixture loaded at: ${audit.fixture_loaded_at}`
                : `Loaded at: ${audit.created_at || 'Not provided'}`}
            </span>
          </div>
        </div>
      )}
      
      <main className="main">
        <section className="workspace" aria-label="Image workspace">
          {!audit && !loading && (
            <div className="canvas-stage">
              <div className="stage-frame stage-frame--empty">
                <CameraFrameIcon size={72} className="stage-empty__icon" />
                <p className="stage-empty__text">Choose a sample or upload a site image to begin.</p>
              </div>
            </div>
          )}
          {showAuditImage && (
            <div className="canvas-stage">
              <AuditImage
                audit={audit}
                selectedId={selectedId}
                onSelectPerson={setSelectedId}
                uploadedNaturalSize={uploadedNaturalSize}
              />
            </div>
          )}
          <div className="editor-stage">
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
        </section>

        <aside className="inspector" aria-label="Inspector">
          <div className="inspector-header">
            <div className="inspector-heading">
              <span className="inspector-kicker">Audit Summary</span>
              {audit && !loading ? (
                <div className="inspector-summary">
                  <span>{totalFindings} findings</span>
                  <span className="summary-sep" aria-hidden="true">·</span>
                  <span>{criticalFindings} Critical</span>
                </div>
              ) : (
                <span className="inspector-summary muted">No audit loaded</span>
              )}
              {evidenceUnavailable && !loading && (
                <span className="evidence-pill">Masked evidence unavailable</span>
              )}
            </div>
            {audit && !loading && (
              <button
                type="button"
                className="btn btn-secondary inspector-print"
                onClick={handlePrint}
                aria-label="Print or export PDF"
              >
                Print / Export PDF
              </button>
            )}
          </div>

          {audit && !loading && (
            <div className="segmented" role="tablist" aria-label="Inspector views">
              <button
                type="button"
                role="tab"
                id="tab-findings"
                aria-selected={activeTab === 'findings'}
                aria-controls="panel-findings"
                className={`segmented-btn ${activeTab === 'findings' ? 'active' : ''}`}
                onClick={() => setActiveTab('findings')}
              >
                Findings ({totalFindings})
              </button>
              <button
                type="button"
                role="tab"
                id="tab-log"
                aria-selected={activeTab === 'log'}
                aria-controls="panel-log"
                className={`segmented-btn ${activeTab === 'log' ? 'active' : ''}`}
                onClick={() => setActiveTab('log')}
              >
                Hazard Log
              </button>
            </div>
          )}

          <div className="inspector-body">
            {loading && (
              <div className="state-panel inspector-message loading-panel" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" />
                <p>Analyzing...</p>
                {timeoutMessage && <p className="inspector-warning">No response yet; the audit may still be running</p>}
                <div className="inspector-actions">
                  <button className="btn btn-secondary" onClick={handleCancel}>Cancel</button>
                  {timeoutMessage && !requestInFlightRef.current && (
                    <button className="btn btn-secondary" onClick={handleTryAgain}>Try again</button>
                  )}
                </div>
              </div>
            )}
            {error && (
              <div className="state-panel state-panel--danger inspector-message" role="alert">
                <p>{error}</p>
                {error !== 'Analysis cancelled' && !loading && (
                  <div className="inspector-actions">
                    <button className="btn btn-secondary" onClick={handleTryAgain}>Try again</button>
                  </div>
                )}
              </div>
            )}
            {audit && !loading && (
              <>
                <div
                  role="tabpanel"
                  id="panel-findings"
                  aria-labelledby="tab-findings"
                  hidden={activeTab !== 'findings'}
                >
                  <FindingsList
                    audit={audit}
                    selectedId={selectedId}
                    onSelectPerson={setSelectedId}
                    decisions={decisions}
                    setDecisions={setDecisions}
                    filters={filters}
                    setFilters={setFilters}
                    showHeader={false}
                  />
                </div>
                <div
                  role="tabpanel"
                  id="panel-log"
                  aria-labelledby="tab-log"
                  hidden={activeTab !== 'log'}
                >
                  <HazardLog
                    audit={audit}
                    selectedId={selectedId}
                    onSelectPerson={setSelectedId}
                    decisions={decisions}
                  />
                </div>
                {showFixtureBanner && <p className="inspector-meta">Evidence export disabled</p>}
                {audit.fixture_loaded_at && <p className="inspector-meta">Fixture loaded at: {audit.fixture_loaded_at}</p>}
                {audit.created_at && !audit.fixture_loaded_at && <p className="inspector-meta">Created: {audit.created_at}</p>}
              </>
            )}
            {!audit && !loading && !error && (
              <div className="state-panel inspector-empty">
                <h2>Results</h2>
                <p>Run analysis to see results</p>
              </div>
            )}
          </div>
        </aside>
      </main>
      <div className="print-footer">
        Prototype audit for human review - not a compliance certification.
      </div>
    </div>
  )
}

export default App
