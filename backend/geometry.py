"""Explicit upright source/crop/resize transforms for local decoded mask tests.
Not a SAM encoded-mask parser and not a contour/polygon extractor.
"""
from dataclasses import dataclass
import math
from PIL import Image
from core import fail,MAX_DIM,MAX_PIXELS
from pipeline import Frame

@dataclass(frozen=True)
class RasterTransform:
    frame:Frame
    crop:tuple
    raster_width:int
    raster_height:int
    def validate(self):
        self.frame.validate()
        if any(type(v) is not int or not 0<v<=MAX_DIM for v in (self.raster_width,self.raster_height)) or self.raster_width*self.raster_height>MAX_PIXELS:fail('INVALID_RASTER_SIZE','Mask test raster exceeds bounds.')
        if not isinstance(self.crop,(tuple,list)) or len(self.crop)!=4 or any(type(v) is not int for v in self.crop):fail('INVALID_CROP','Explicit integer source-pixel crop required.')
        x,y,w,h=self.crop
        if x<0 or y<0 or w<=0 or h<=0 or x+w>self.frame.width or y+h>self.frame.height:fail('INVALID_CROP','Crop outside upright source frame.')
    def point_to_source(self,x,y):
        self.validate()
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (x,y)) or not 0<=x<self.raster_width or not 0<=y<self.raster_height:fail('INVALID_RASTER_POINT','Pixel coordinate outside test raster.')
        x0,y0,w,h=self.crop
        # Top-left pixel coordinate. Pixel footprint mapping is separate below.
        return (x0+x*w/self.raster_width,y0+y*h/self.raster_height)

def binary_mask_to_source(mask,transform):
    """Nearest-neighbour synthetic mask placement, with explicit resize provenance.
Output is a boolean coverage test image, never privacy clearance or evidence.
"""
    transform.validate()
    if not isinstance(mask,Image.Image) or mask.mode!='L' or mask.size!=(transform.raster_width,transform.raster_height):fail('MASK_FRAME_MISMATCH','Use a matching 8-bit test raster.')
    values=set(mask.get_flattened_data())
    if not values<=set((0,255)):fail('NONBINARY_MASK','Only explicit 0/255 decoded test masks accepted.')
    x,y,w,h=transform.crop
    out=Image.new('L',(transform.frame.width,transform.frame.height),0)
    resized=mask.resize((w,h),Image.Resampling.NEAREST)
    out.paste(resized,(x,y))
    return out

def inclusive_box_to_crop(box,frame):
    """Official SAM output box upper coordinates are inclusive source pixels.
Convert to integer half-open crop width/height without dropping last row/column.
"""
    frame.validate()
    if not isinstance(box,(tuple,list)) or len(box)!=4 or any(type(v) is not int for v in box):fail('INVALID_BOX','Integer inclusive box required.')
    x1,y1,x2,y2=box
    if not 0<=x1<=x2<frame.width or not 0<=y1<=y2<frame.height:fail('INVALID_BOX','Inclusive box outside source frame.')
    return x1,y1,x2-x1+1,y2-y1+1
