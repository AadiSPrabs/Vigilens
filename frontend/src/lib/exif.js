export function parseExifOrientation(view) {
  // Minimal JPEG EXIF parser
  if (view.getUint16(0) !== 0xFFD8) return 1
  let offset = 2
  while (offset < view.byteLength) {
    const marker = view.getUint16(offset)
    offset += 2
    if (marker === 0xFFE1) {
      const length = view.getUint16(offset)
      offset += 2
      const exifHeader = view.getUint32(offset)
      offset += 4
      if (exifHeader !== 0x45786966) break // Exif
      offset += 2 // 00 00
      const tiffStart = offset
      const endian = view.getUint16(offset)
      offset += 2
      const littleEndian = endian === 0x4949
      const readU16 = (o) => littleEndian ? view.getUint16(o, true) : view.getUint16(o)
      const readU32 = (o) => littleEndian ? view.getUint32(o, true) : view.getUint32(o)
      offset += 2 // 0x002A
      const firstIfdOffset = readU32(offset)
      offset = tiffStart + firstIfdOffset
      const numEntries = readU16(offset)
      offset += 2
      for (let i = 0; i < numEntries; i++) {
        const tag = readU16(offset)
        const type = readU16(offset + 2)
        const count = readU32(offset + 4)
        const valueOffset = offset + 8
        if (tag === 0x0112) { // Orientation
          if (type === 3) {
            return readU16(valueOffset)
          }
        }
        offset += 12
      }
      break
    } else if ((marker & 0xFF00) !== 0xFF00) break
    else if (marker === 0xFFDA) break // SOS
    else {
      const length = view.getUint16(offset)
      offset += length
    }
  }
  return 1
}

export async function bakeOrientation(file) {
  if (file.type !== 'image/jpeg') return file
  const buffer = await file.arrayBuffer()
  const view = new DataView(buffer)
  const orientation = parseExifOrientation(view)
  if (orientation === 1) return file
  if (orientation < 2 || orientation > 8) return file
  
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  const canvas = document.createElement('canvas')
  const ctx = canvas.getContext('2d')
  
  if (orientation >= 5 && orientation <= 8) {
    canvas.width = bitmap.height
    canvas.height = bitmap.width
  } else {
    canvas.width = bitmap.width
    canvas.height = bitmap.height
  }
  
  ctx.drawImage(bitmap, 0, 0)
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        // fallback to JPEG 0.92
        canvas.toBlob((blob2) => {
          resolve(new File([blob2], file.name.replace(/\.[^/.]+$/, '.jpg'), { type: 'image/jpeg' }))
        }, 'image/jpeg', 0.92)
        return
      }
      // Check size
      if (blob.size > 15000000) {
        canvas.toBlob((blob2) => {
          resolve(new File([blob2], file.name.replace(/\.[^/.]+$/, '.jpg'), { type: 'image/jpeg' }))
        }, 'image/jpeg', 0.92)
      } else {
        resolve(new File([blob], file.name.replace(/\.[^/.]+$/, '.png'), { type: 'image/png' }))
      }
    }, 'image/png')
  })
}
