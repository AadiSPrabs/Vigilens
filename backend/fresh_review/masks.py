"""Versioned local integration proposal. Lossless masks, explicit non-assessment, no release."""
import hashlib
from PIL import Image
MAX_MASK_PIXELS=1_000_000

def encode_mask(mask,box,frame):
    if not isinstance(mask,Image.Image)or mask.mode!='L':raise ValueError('Binary L raster required')
    if not isinstance(frame,(list,tuple))or len(frame)!=2 or any(type(v)is not int or v<=0 for v in frame):raise ValueError('Integer original frame required')
    if not isinstance(box,(list,tuple))or len(box)!=4 or any(type(v)is not int for v in box):raise ValueError('Integer half-open source box required')
    x,y,r,b=box;w,h=frame
    if not 0<=x<r<=w or not 0<=y<b<=h or mask.size!=(r-x,b-y)or mask.width*mask.height>MAX_MASK_PIXELS:raise ValueError('Mask/source shape mismatch or quota')
    raw=mask.tobytes()
    if not set(raw)<={0,255}or 255 not in raw:raise ValueError('Nonempty binary mask required')
    counts=[];value=0;count=0
    for pixel in raw:
        bit=pixel//255
        if bit==value:count+=1
        else:counts.append(count);count=1;value=bit
    counts.append(count)
    return {'encoding':'binary_rle_row_major_v1','size':[mask.width,mask.height],'origin_pixels':[x,y],
            'box_half_open_pixels':list(box),'source_frame_size':list(frame),'counts':counts,
            'starts_with':0,'foreground_value':1,'pixel_sha256':hashlib.sha256(raw).hexdigest(),
            'coordinate_basis':'original_upright_source_pixels','lossless':True}

def decode_mask(data):
    if not isinstance(data,dict)or data.get('encoding')!='binary_rle_row_major_v1'or type(data.get('starts_with'))is not int or data.get('starts_with')!=0 or type(data.get('foreground_value'))is not int or data.get('foreground_value')!=1:raise ValueError('Unsupported mask encoding')
    size=data.get('size');counts=data.get('counts')
    if not isinstance(size,list)or len(size)!=2 or any(type(v)is not int or v<=0 for v in size)or size[0]*size[1]>MAX_MASK_PIXELS:raise ValueError('Invalid mask dimensions')
    if not isinstance(counts,list)or not 1<=len(counts)<=size[0]*size[1]+1 or any(type(v)is not int or v<0 for v in counts)or any(v==0 for v in counts[1:])or sum(counts)!=size[0]*size[1]:raise ValueError('Invalid run lengths')
    raw=b''.join(bytes([255 if i%2 else 0])*v for i,v in enumerate(counts))
    if hashlib.sha256(raw).hexdigest()!=data.get('pixel_sha256'):raise ValueError('Mask pixel identity changed')
    mask=Image.frombytes('L',tuple(size),raw)
    checked=encode_mask(mask,data.get('box_half_open_pixels'),data.get('source_frame_size'))
    if data!=checked:raise ValueError('Mask metadata or canonical encoding changed')
    return mask
