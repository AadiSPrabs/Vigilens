import pytest
from PIL import Image
from pipeline import Frame
from geometry import RasterTransform,binary_mask_to_source,inclusive_box_to_crop
from core import AuditError

def test_resize_crop_points():
 t=RasterTransform(Frame(100,80,'synthetic'),(10,20,40,20),20,10)
 assert t.point_to_source(0,0)==(10,20) and t.point_to_source(19,9)==(48,38)
def test_last_pixel_inclusive_not_lost():
 f=Frame(100,80,'synthetic');assert inclusive_box_to_crop((99,79,99,79),f)==(99,79,1,1)
 t=RasterTransform(f,(99,79,1,1),1,1)
 m=Image.new('L',(1,1),255);out=binary_mask_to_source(m,t)
 assert out.getpixel((99,79))==255 and sum(out.get_flattened_data())==255

def test_upsampling_no_frame_offset():
 f=Frame(100,80,'synthetic');t=RasterTransform(f,(10,20,40,20),20,10)
 m=Image.new('L',(20,10),0);m.putpixel((0,0),255)
 out=binary_mask_to_source(m,t)
 assert out.getbbox()==(10,20,12,22) and sum(out.get_flattened_data())==4*255

def test_wrong_width_height_cannot_transpose():
 t=RasterTransform(Frame(100,80,'f'),(10,20,40,20),20,10)
 with pytest.raises(AuditError):binary_mask_to_source(Image.new('L',(10,20),255),t)

def test_nonbinary_no_threshold_guess():
 t=RasterTransform(Frame(2,2,'f'),(0,0,2,2),2,2)
 with pytest.raises(AuditError):binary_mask_to_source(Image.new('L',(2,2),127),t)

@pytest.mark.parametrize('box',[(-1,0,1,1),(0,0,100,80),(1,1,0,0),(True,0,1,1)])
def test_invalid_inclusive_box(box):
 with pytest.raises(AuditError):inclusive_box_to_crop(box,Frame(100,80,'f'))

def test_orientation_not_silently_transformed():
 t=RasterTransform(Frame(80,100,'f',6),(0,0,80,100),80,100)
 with pytest.raises(AuditError):t.validate()

def test_pixel_edges_not_normalized_endpoint():
 t=RasterTransform(Frame(100,80,'f'),(0,0,100,80),100,80)
 with pytest.raises(AuditError):t.point_to_source(100,80)
