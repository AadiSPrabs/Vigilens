import React, { useState } from 'react'
import UploadZoneEditor from './components/UploadZoneEditor'

function App() {
  const [image, setImage] = useState(null)
  const [zones, setZones] = useState([])
  const [audit, setAudit] = useState(null)
  const [selectedId, setSelectedId] = useState(null)
  const [decisions, setDecisions] = useState({})
  const [filters, setFilters] = useState({ severity: 'all', zone: 'all' })
  const [sample, setSample] = useState(null)
  const [runWithoutZones, setRunWithoutZones] = useState(false)

  // Clear audit/decisions/selection/filters when image, sample or zones change
  React.useEffect(() => {
    setAudit(null)
    setDecisions({})
    setSelectedId(null)
    setFilters({ severity: 'all', zone: 'all' })
  }, [image, sample, zones])

  const handleAnalyse = () => {
    // Will be wired in Phase 2
    console.log('Analyse clicked - will be implemented in Phase 2')
  }

  return (
    <div className="app">
      <header className="topbar">
        <h1>Vigilens</h1>
        <span className="mode-badge">Mode: fixture</span>
      </header>

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
          <div className="card">
            <h2>Results</h2>
            <p style={{color: 'var(--text-muted)'}}>Results will appear here in Phase 2</p>
          </div>
        </div>
      </main>
    </div>
  )
}

export default App
