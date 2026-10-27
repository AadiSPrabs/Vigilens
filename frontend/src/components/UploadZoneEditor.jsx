import React, { useState, useRef, useEffect } from 'react'
import { clientToNormalised, polygonArea, selfIntersects } from '../lib/geometry'
import { saveZones, loadZones } from '../lib/storage'
import { samples } from '../fixtures'
import { canAnalyse } from '../lib/canAnalyse'
import { zonesEqual } from '../lib/geometry'
import { preCheckFile } from '../lib/validation'

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

  const handleFile = (file) => {
    setFileError(null)
    if (!file) return
    const check = preCheckFile(file)
    if (!check.ok) {
      setFileError(check.message)
      return
    }
    setSample(null)
    setImage(file)
    setZones([])
    setCurrentPoints([])
    setDrawing(false)
    const saved = loadZones(file)
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
        const file = new File([blob], s.id + '.png', { type: blob.type || 'image/png' })
        setImage(file)
        setZones(s.presetZones.map(z => ({ ...z, points: z.points.map(p => ({...p})) })))
        setCurrentPoints([])
        setDrawing(false)
      })
  }

  const handleImageClick = (e) => {
    if (!drawing || !imgRef.current) return
    const norm = clientToNormalised(e, imgRef.current)
    if (!norm) return
    setCurrentPoints([...currentPoints, norm])
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
    if (polygonArea(currentPoints) === 0) {
      setZoneError('Zero-area polygon is not allowed')
      return
    }
    if (selfIntersects(currentPoints)) {
      setZoneError('Self-intersecting polygon is not allowed')
      return
    }
    const newZone = {
      id: `zone-${zoneIdCounter}`,
      name: zoneName || `Zone ${zoneIdCounter}`,
      hazard: zoneHazard,
      points: currentPoints
    }
    const newZones = [...(zones || []), newZone]
    setZones(newZones)
    setCurrentPoints([])
    setDrawing(false)
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
    }
  }

  const clearPoints = () => {
    setCurrentPoints([])
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

  return (
    <div className="card">
      <h2>Upload & Zone Editor</h2>
      
      <div className="sample-picker">
        <span>Try a sample:</span>
        {samples.map(s => (
          <button 
            key={s.id}
            className={`sample-btn ${sample?.id === s.id ? 'active' : ''}`}
            onClick={() => handleSampleSelect(s)}
          >
            {s.id}
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
              {(zones || []).map(zone => (
                <polygon
                  key={zone.id}
                  className={`zone-polygon ${zone.hazard ? 'hazard' : ''}`}
                  points={zone.points.map(p => `${p.x},${p.y}`).join(' ')}
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
            </svg>
          </div>

          <div className="controls">
            <button className="btn btn-secondary" onClick={() => { setDrawing(!drawing); setCurrentPoints([]); setZoneError(null) }}>
              {drawing ? 'Cancel Drawing' : 'Draw Zone'}
            </button>
            {drawing && (
              <>
                <button className="btn btn-secondary" onClick={undoPoint}>Undo Last Point</button>
                <button className="btn btn-secondary" onClick={clearPoints}>Clear Points</button>
                <button className="btn" onClick={finishZone}>Finish Zone</button>
              </>
            )}
          </div>

          {zoneError && <p style={{ color: 'var(--critical)' }}>{zoneError}</p>}

          {drawing && (
            <div className="card" style={{marginTop: '0.5rem'}}>
              <div style={{display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap'}}>
                <input 
                  type="text" 
                  value={zoneName} 
                  onChange={(e) => setZoneName(e.target.value)}
                  placeholder="Zone name (required)"
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
