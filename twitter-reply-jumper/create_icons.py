import os
from PIL import Image, ImageDraw

def create_icon(size, filename):
    img = Image.new('RGB', (size, size), color = (29, 161, 242)) # Twitter Blue
    d = ImageDraw.Draw(img)
    # Draw a simple "T" or circle
    d.ellipse([size*0.2, size*0.2, size*0.8, size*0.8], fill=(255, 255, 255))
    img.save(filename)

base_dir = '/home/shou/桌面/x评论监控-docker/twitter-reply-jumper/images'
create_icon(16, os.path.join(base_dir, 'icon16.png'))
create_icon(48, os.path.join(base_dir, 'icon48.png'))
create_icon(128, os.path.join(base_dir, 'icon128.png'))
print("Icons created successfully")
