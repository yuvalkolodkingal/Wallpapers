#!/usr/bin/env python3
"""Build the repository contact sheet from its small preview images."""
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[1]
items=json.loads((ROOT/'metadata/collection.json').read_text())['wallpapers']
font=ImageFont.load_default(size=18)
heading=ImageFont.load_default(size=30)
canvas=Image.new('RGB',(1536,100+326*((len(items)+2)//3)), '#141719')
draw=ImageDraw.Draw(canvas)
draw.text((18,16),'WALLPAPERS / YUVAL KOLODKIN-GAL',font=heading,fill='#eef0e9')
draw.text((18,61),'Original photography · 18 selections · Four matching desktop themes',font=font,fill='#a8b1a7')
for i,item in enumerate(items):
 x=i%3*512+8;y=100+i//3*326
 with Image.open(ROOT/item['preview']) as im:
  im=im.resize((496,279),Image.Resampling.LANCZOS);canvas.paste(im,(x,y))
 draw.text((x,y+291),item['title'],font=font,fill='#e8ece5')
canvas.save(ROOT/'previews/collection.jpg',quality=92,optimize=True)
