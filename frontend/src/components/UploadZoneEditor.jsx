import React, { useState, useRef, useEffect } from 'react'
import { clientToNormalised, polygonArea, selfIntersects } from '../lib/geometry'
import { saveZones, loadZones } from '../lib/storage'
import { samples } from '../fixtures'
import { contractSample } from '../fixtures/contract'
import { canAnalyse } from '../lib/canAnalyse'
import { zonesEqual } from '../lib/geometry'
import { preCheckFile } from '../lib/validation'
import { bakeOrientation } from '../lib/exif'

export default function UploadZoneEditor({ 
  image, setImage, zones, setZones, sample, setSample, 
  runWithoutZones, setRunWithoutZones, onAnalyse, loading 
}) {
  const [dragOver, setDragOver] = useState(false)
  const [drawing, setDrawing] = useState(false)
  const [currentPoints, setCurrentPoints] = useState([])
  const [zoneName, setZoneName] = useState('Zone 1')
  const [zoneHazard, setZoneHazard] = useState(false)
  const imgRef = useRef(null)
  const [zoneIdCounter, setZoneIdCounter] = useState(1)
  const [fileError, setFileError] = useState(null)
  const [zoneError, setZoneError] = useState(null)
  const lastPointRef = useRef(null)
  const isBackendMode = (import.meta.env.VITE_AUDIT_MODE || 'fixture') === 'backend'
  const [keyboardMode, setKeyboardMode] = useState(false)
  const [centerPoint, setCenterPoint] = useState({ x: 0.5, y: 0.5 })

  useEffect(() => {
    if (zones && zones.length > 0 && runWithoutZones) {
      setRunWithoutZones(false)
    }
  }, [zones])

  useEffect(() => {
    if (zones && zones.length > 0) {
      const maxNum = zones.reduce((max, z) => {
        const match = z.id.match(/zone-(\d+)/)
        return match ? Math.max(max, parseInt(match[1])) : max
      }, 0)
      setZoneIdCounter(maxNum + 1)
    }
  }, [zones])

  const handleFile = async (file) => {
    setFileError(null)
    if (!file) return
    const check = preCheckFile(file)
    if (!check.ok) {
      setFileError(check.message)
      return
    }
    const processedFile = await bakeOrientation(file)
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(processedFile.type)) {
      setFileError('Invalid file type')
      return
    }
    setSample(null)
    setImage(processedFile)
    setZones([])
    setCurrentPoints([])
    setDrawing(false)
    const saved = loadZones(processedFile)
    if (saved && Array.isArray(saved)) {
      setZones(saved)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }

  const handleSampleSelect = (s) => {
    setSample(s)
    fetch(s.imageSrc)
      .then(r => r.blob())
      .then(blob => {
        const type = s.id === 'contract-test' ? 'image/png' : (blob.type || 'image/png')
        const file = new File([blob], s.id + '.png', { type })
        setImage(file)
        setZones(s.presetZones.map(z => ({ ...z, points: z.points.map(p => ({...p})) })))
        setCurrentPoints([])
        setDrawing(false)
      })
  }

  const addPoint = (norm) => {
    if (!drawing) return
    if (lastPointRef.current) {
      const dx = norm.x - lastPointRef.current.x
      const dy = norm.y - lastPointRef.current.y
      if (Math.sqrt(dx*dx + dy*dy) < 0.002) return
    }
    if (currentPoints.some(p => Math.abs(p.x-norm.x)<1e-9 && Math.abs(p.y-norm.y)<1e-9)) return
    if (norm.x < 0 || norm.x > 1 || norm.y < 0 || norm.y > 1) return
    lastPointRef.current = norm
    setCurrentPoints([...currentPoints, norm])
  }

  const handleImageClick = (e) => {
    if (!drawing || !imgRef.current) return
    const norm = clientToNormalised(e, imgRef.current)
    if (!norm) return
    addPoint(norm)
  }

  const handleKeyboardAddPoint = () => {
    if (!drawing) setDrawing(true)
    addPoint(centerPoint)
  }

  const handleKeyboardNudge = (dx, dy) => {
    setCenterPoint(prev => ({
      x: Math.max(0, Math.min(1, prev.x + dx)),
      y: Math.max(0, Math.min(1, prev.y + dy))
    }))
  }

  const finishZone = () => {
    setZoneError(null)
    if ((zones || []).length >= 20) {
      setZoneError('Too many zones. Maximum is 20.')
      return
    }
    if (currentPoints.length < 3) {
      setZoneError('Need at least 3 points')
      return
    }
    if (currentPoints.length > 100) {
      setZoneError('Too many points per polygon. Maximum is 100.')
      return
    }
    if (currentPoints.length > 0 && currentPoints.some((p,i) => i>0 && Math.abs(p.x-currentPoints[0].x)<1e-9 && Math.abs(p.y-currentPoints[0].y)<1e-9)) {
      setZoneError('Duplicate/closing vertex not allowed')
      return
    }
    if (polygonArea(currentPoints) === 0) {
      setZoneError('Zero-area polygon is not allowed')
      return
    }
    if (selfIntersects(currentPoints)) {
      setZoneError('Self-intersecting polygon is not allowed')
      return
    }
    if (zoneName.length < 1 || zoneName.length > 200) {
      setZoneError('Zone name must be 1-200 chars')
      return
    }
    const newZoneId = `zone-${zoneIdCounter}`
    if (newZoneId.length > 128) {
      setZoneError('Zone id too long')
      return
    }
    const newZone = {
      id: newZoneId,
      name: zoneName,
      hazard: zoneHazard,
      points: currentPoints
    }
    const zonesJson = JSON.stringify([...(zones||[]), newZone])
    if (zonesJson.length > 100000) {
      setZoneError('Zones JSON too large')
      return
    }
    const newZones = [...(zones || []), newZone]
    setZones(newZones)
    setCurrentPoints([])
    setDrawing(false)
    setKeyboardMode(false)
    lastPointRef.current = null
    setZoneIdCounter(zoneIdCounter + 1)
    setZoneName(`Zone ${zoneIdCounter + 1}`)
    setZoneHazard(false)
    if (!sample && image) {
      saveZones(image, newZones)
    }
  }

  const undoPoint = () => {
    if (currentPoints.length > 0) {
      setCurrentPoints(currentPoints.slice(0, -1))
      lastPointRef.current = currentPoints.length > 1 ? currentPoints[currentPoints.length - 2] : null
    }
  }

  const clearPoints = () => {
    setCurrentPoints([])
    lastPointRef.current = null
  }

  const deleteZone = (zoneId) => {
    const newZones = (zones || []).filter(z => z.id !== zoneId)
    setZones(newZones)
    if (!sample && image) {
      saveZones(image, newZones)
    }
  }

  const updateZone = (zoneId, updates) => {
    const newZones = (zones || []).map(z => z.id === zoneId ? { ...z, ...updates } : z)
    setZones(newZones)
    if (!sample && image) {
      saveZones(image, newZones)
    }
  }

  const resetToPreset = () => {
    if (sample && sample.presetZones) {
      setZones(sample.presetZones.map(z => ({ ...z, points: z.points.map(p => ({...p})) })))
      setCurrentPoints([])
      setDrawing(false)
    }
  }

  const isSampleZonesEdited = () => {
    if (!sample) return false
    return !zonesEqual(zones || [], sample.presetZones || [])
  }

  const canRun = canAnalyse({ image, zones, runWithoutZones, sample }) && !loading
  const displaySamples = isBackendMode ? [...samples, contractSample] : samples

  return (
    <div className="card">
      <h2>Upload & Zone Editor</h2>
      
      <div className="sample-picker">
        <span>Try a sample:</span>
        {displaySamples.map(s => (
          <button 
            key={s.id}
            className={`sample-btn ${sample?.id === s.id ? 'active' : ''}`}
            onClick={() => handleSampleSelect(s)}
          >
            {s.id === 'contract-test' ? 'Contract test (backend pairing)' : s.id}
          </button>
        ))}
      </div>

      <div 
        className={`upload-area ${dragOver ? 'dragover' : ''}`}
        onDrop={handleDrop}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
      >
        <p>Drag and drop an image here, or</p>
        <input 
          type="file" 
          accept="image/jpeg,image/png,image/webp"
          onChange={(e) => handleFile(e.target.files[0])}
        />
        <p><small>jpg, png, webp • Max 15 MB</small></p>
        {fileError && <p style={{ color: 'var(--critical)' }}>{fileError}</p>}
      </div>

      {image && (
        <div className="zone-editor">
          <p style={{ fontSize: '0.8rem', color: 'var(--medium)' }}>Preview only, not evidence</p>
          <div className="zone-canvas-wrapper">
            <img 
              ref={imgRef}
              src={URL.createObjectURL(image)} 
              alt="Site image for zone drawing"
              onClick={handleImageClick}
            />
            <svg 
              className={`zone-svg ${drawing ? 'drawing' : ''}`}
              viewBox="0 0 1 1" 
              preserveAspectRatio="none"
              role="img"
              aria-label="Zone overlay"
            >
              <defs>
                <pattern
                  id="hazard-pattern"
                  patternUnits="userSpaceOnUse"
                  width="0.04"
                  height="0.04"
                  patternTransform="rotate(45)"
                >
                  <rect width="0.04" height="0.04" fill="#000000" opacity="0.12" />
                  <line x1="0" y1="0" x2="0" y2="0.04" stroke="#f59e0b" strokeWidth="0.002" opacity="0.25" />
                  <line x1="0.02" y1="0" x2="0.02" y2="0.04" stroke="#000000" strokeWidth="0.002" opacity="0.25" />
                </pattern>
                <pattern
                  id="restricted-pattern"
                  patternUnits="userSpaceOnUse"
                  width="0.04"
                  height="0.04"
                  patternTransform="rotate(45)"
                >
                  <rect width="0.04" height="0.04" fill="#000000" opacity="0.1" />
                  <line x1="0" y1="0" x2="0" y2="0.04" stroke="#94a3b8" strokeWidth="0.002" opacity="0.2" />
                  <line x1="0.02" y1="0" x2="0.02" y2="0.04" stroke="#000000" strokeWidth="0.002" opacity="0.2" />
                </pattern>
              </defs>
              {(zones || []).map(zone => (
                <polygon
                  key={zone.id}
                  className={`zone-polygon ${zone.hazard ? 'hazard' : ''}`}
                  points={zone.points.map(p => `${p.x},${p.y}`).join(' ')}
                  fill={zone.hazard ? 'url(#hazard-pattern)' : 'url(#restricted-pattern)'}
                  stroke={zone.hazard ? '#ff334b' : '#94a3b8'}
                  strokeWidth="0.002"
                  strokeLinejoin="round"
                  tabIndex={0}
                  role="button"
                  aria-label={`Zone ${zone.name}, ${zone.hazard ? 'hazard' : 'safe'}`}
                />
              ))}
              {drawing && currentPoints.length > 0 && (
                <g>
                  <polyline
                    className="zone-preview"
                    points={currentPoints.map(p => `${p.x},${p.y}`).join(' ')}
                  />
                  {currentPoints.map((p, i) => (
                    <circle key={i} cx={p.x} cy={p.y} r="0.003" fill="#3b82f6" />
                  ))}
                </g>
              )}
              {keyboardMode && drawing && (
                <circle cx={centerPoint.x} cy={centerPoint.y} r="0.004" fill="#fbbf24" stroke="#000" strokeWidth="0.001" />
              )}
            </svg>
          </div>

          <div className="controls">
            <button className="btn btn-secondary" onClick={() => { setDrawing(!drawing); setCurrentPoints([]); lastPointRef.current = null; setZoneError(null); setKeyboardMode(false) }}>
              {drawing ? 'Cancel Drawing' : 'Draw Zone'}
            </button>
            {drawing && (
              <>
                <button className="btn btn-secondary" onClick={undoPoint}>Undo Last Point</button>
                <button className="btn btn-secondary" onClick={clearPoints}>Clear Points</button>
                <button className="btn" onClick={finishZone}>Finish Zone</button>
                <button className="btn btn-secondary" onClick={() => setKeyboardMode(!keyboardMode)}>
                  {keyboardMode ? 'Mouse Mode' : 'Keyboard Mode'}
                </button>
              </>
            )}
          </div>

          {keyboardMode && drawing && (
            <div className="card" style={{ marginTop: '0.5rem' }}>
              <button className="btn" onClick={handleKeyboardAddPoint}>Add point at centre</button>
              <div style={{ marginTop: '0.5rem' }}>
                <button onClick={() => handleKeyboardNudge(0, -0.01)} aria-label="Nudge up">↑</button>
                <button onClick={() => handleKeyboardNudge(0, 0.01)} aria-label="Nudge down">↓</button>
                <button onClick={() => handleKeyboardNudge(-0.01, 0)} aria-label="Nudge left">←</button>
                <button onClick={() => handleKeyboardNudge(0.01, 0)} aria-label="Nudge right">→</button>
              </div>
              <p><small>Use arrow keys to nudge, add point at centre</small></p>
            </div>
          )}

          {zoneError && <p style={{ color: 'var(--critical)' }}>{zoneError}</p>}

          {drawing && (
            <div className="card" style={{marginTop: '0.5rem'}}>
              <div style={{display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap'}}>
                <input 
                  type="text" 
                  value={zoneName} 
                  onChange={(e) => setZoneName(e.target.value)}
                  placeholder="Zone name (required)"
                  maxLength={200}
                />
                <label>
                  <input 
                    type="checkbox" 
                    checked={zoneHazard} 
                    onChange={(e) => setZoneHazard(e.target.checked)}
                  />
                  Hazard zone
                </label>
              </div>
              <p><small>Click on the image to add points. Need at least 3 points.</small></p>
            </div>
          )}

          <div className="zone-list">
            <h3>Zones</h3>
            {(zones || []).map(zone => (
              <div key={zone.id} className="zone-item">
                <input 
                  type="text" 
                  value={zone.name}
                  onChange={(e) => updateZone(zone.id, { name: e.target.value })}
                  maxLength={200}
                />
                <label>
                  <input 
                    type="checkbox" 
                    checked={zone.hazard}
                    onChange={(e) => updateZone(zone.id, { hazard: e.target.checked })}
                  />
                  Hazard
                </label>
                <button className="btn btn-danger" onClick={() => deleteZone(zone.id)}>Delete</button>
              </div>
            ))}
          </div>

          <label style={{display: 'block', marginTop: '0.5rem'}}>
            <input 
              type="checkbox" 
              checked={runWithoutZones}
              onChange={(e) => setRunWithoutZones(e.target.checked)}
            />
            Run without zones
          </label>

          {sample && isSampleZonesEdited() && (
            <div className="warning">
              <p>Sample results were made for the preset zones. Reset to sample zones to analyse.</p>
              <button className="btn btn-secondary" onClick={resetToPreset}>Reset to sample zones</button>
            </div>
          )}

          <button 
            className="btn" 
            style={{marginTop: '1rem'}}
            disabled={!canRun}
            onClick={onAnalyse}
          >
            Analyse
          </button>
        </div>
      )}
    </div>
  )
}
