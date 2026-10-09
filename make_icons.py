import os
from PIL import Image, ImageDraw, ImageFont

ICONS_DIR = os.path.join(os.path.dirname(__file__), "dashboard", "frontend", "icons")
os.makedirs(ICONS_DIR, exist_ok=True)

def generate_icon(size, filename):
    # Apple style rounded rectangle
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    radius = int(size * 0.22)
    # Background gradient or solid Apple Blue
    bg_color = (0, 113, 227, 255) # Apple Blue
    draw.rounded_rectangle([0, 0, size, size], radius=radius, fill=bg_color)
    
    # White ring / border subtle
    border_color = (255, 255, 255, 40)
    draw.rounded_rectangle([2, 2, size - 2, size - 2], radius=radius, outline=border_color, width=max(2, size // 64))
    
    # Draw letter 'P' in center
    # Simulating simple geometric 'P'
    p_x = int(size * 0.35)
    p_y = int(size * 0.22)
    p_w = int(size * 0.32)
    p_h = int(size * 0.56)
    stroke = max(4, int(size * 0.09))
    
    # Vertical line of P
    draw.rectangle([p_x, p_y, p_x + stroke, p_y + p_h], fill=(255, 255, 255, 255))
    
    # Top arc of P
    loop_h = int(p_h * 0.58)
    draw.rounded_rectangle([p_x, p_y, p_x + p_w, p_y + loop_h], radius=int(loop_h * 0.45), fill=(255, 255, 255, 255))
    inner_pad = stroke
    if p_w > inner_pad * 2 and loop_h > inner_pad * 2:
        draw.rounded_rectangle([p_x + inner_pad, p_y + inner_pad, p_x + p_w - inner_pad, p_y + loop_h - inner_pad],
                               radius=int((loop_h - inner_pad*2) * 0.45), fill=bg_color)
        draw.rectangle([p_x, p_y + inner_pad, p_x + inner_pad, p_y + loop_h - inner_pad], fill=bg_color)
        draw.rectangle([p_x, p_y, p_x + stroke, p_y + p_h], fill=(255, 255, 255, 255))

    # Dot accent (IoT green dot)
    dot_r = max(3, int(size * 0.05))
    dot_x = int(size * 0.76)
    dot_y = int(size * 0.25)
    draw.ellipse([dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r], fill=(52, 199, 89, 255)) # Apple Green

    out_path = os.path.join(ICONS_DIR, filename)
    img.save(out_path, "PNG")
    print(f"Generated: {out_path} ({size}x{size})")

generate_icon(192, "icon-192.png")
generate_icon(512, "icon-512.png")
generate_icon(180, "apple-touch-icon.png")
generate_icon(64, "favicon.png")
