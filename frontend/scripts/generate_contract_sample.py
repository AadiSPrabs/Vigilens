#!/usr/bin/env python3
# Deterministic script to generate contract-sample.png
# 1280x720, upright, synthetic, no polygons/zone outlines baked in
from PIL import Image, ImageDraw
import os

# Create image
img = Image.new('RGB', (1280, 720), color='#dfe7ed')
draw = ImageDraw.Draw(img)

# Ground
draw.rectangle([0, 500, 1280, 720], fill='#8b7355')

# Label
draw.text((10, 10), "SYNTHETIC - contract test", fill='#1e3a8a')

# person-1 x 0.30-0.45 y 0.30-0.70, no helmet, vest on
# Map to pixels: x from 384-576, y from 216-504
cx, cy = 384+96, 216+140  # center
draw.ellipse([cx-30, cy-35, cx+30, cy+35], fill='#d4a574')  # head
draw.rectangle([cx-25, cy+35, cx+25, cy+115], fill='#2563eb')  # body
# vest on
draw.rectangle([cx-25, cy+35, cx+25, cy+75], fill='#f59e0b')
# no helmet - hair
draw.ellipse([cx-22, cy-38, cx+22, cy-10], fill='#8b4513')

# person-2 x 0.70-0.82 y 0.30-0.70, helmet and vest on
cx2, cy2 = 896+76, 216+140
draw.ellipse([cx2-28, cy2-33, cx2+28, cy2+33], fill='#c68642')
draw.rectangle([cx2-22, cy2+33, cx2+22, cy2+108], fill='#16a34a')
draw.rectangle([cx2-22, cy2+33, cx2+22, cy2+73], fill='#f59e0b')
# helmet on
draw.ellipse([cx2-26, cy2-48, cx2+26, cy2-20], fill='#fbbf24')
draw.rectangle([cx2-26, cy2-38, cx2+26, cy2-30], fill='#fbbf24')

# person-3 x 0.15-0.25 y 0.35-0.65, helmet on, vest partly hidden
cx3, cy3 = 192+64, 252+108
draw.ellipse([cx3-26, cy3-31, cx3+26, cy3+31], fill='#b8860b')
draw.rectangle([cx3-20, cy3+31, cx3+20, cy3+101], fill='#7c3aed')
# vest partly hidden
draw.rectangle([cx3-20, cy3+31, cx3+5, cy3+61], fill='#f59e0b')
# helmet on
draw.ellipse([cx3-24, cy3-44, cx3+24, cy3-18], fill='#fbbf24')

# person-4 x 0.50-0.58 y 0.10-0.40, helmet and vest on
cx4, cy4 = 640+51, 72+108
draw.ellipse([cx4-24, cy4-29, cx4+24, cy4+29], fill='#a0522d')
draw.rectangle([cx4-18, cy4+29, cx4+18, cy4+94], fill='#dc2626')
draw.rectangle([cx4-18, cy4+29, cx4+18, cy4+64], fill='#f59e0b')
draw.ellipse([cx4-22, cy4-42, cx4+22, cy4-16], fill='#fbbf24')

out_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'fixtures', 'contract', 'contract-sample.png')
img.save(out_path)
print('done')
