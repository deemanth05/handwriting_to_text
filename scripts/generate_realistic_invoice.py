"""Generate a realistic, authentic handwritten Indian hardware store invoice image.

Features:
- Pre-printed retail bill-book header with ruled table columns
- Natural blue ballpoint pen handwriting (using Windows Ink Free font)
- Realistic business items, quantities, rates, subtotal, GST, and grand total
- Authentic paper grain, ruled lines, rubber stamp, and signature
- No 'sample', 'test', or 'mock' watermarks anywhere
"""

import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np


def create_realistic_invoice(output_path: Path):
    width = 1600
    height = 2200

    # 1. Base Paper Texture: Warm off-white / ivory parchment
    base = Image.new("RGB", (width, height), (250, 248, 242))
    
    # Add subtle paper grain/noise
    noise = np.random.normal(0, 3.5, (height, width, 3)).astype(np.int16)
    arr = np.array(base, dtype=np.int16) + noise
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    draw = ImageDraw.Draw(img)

    # Load Fonts
    font_bold_path = "C:/Windows/Fonts/segoeuib.ttf"
    font_regular_path = "C:/Windows/Fonts/segoeui.ttf"
    font_hand_path = "C:/Windows/Fonts/Inkfree.ttf"
    if not Path(font_hand_path).exists():
        font_hand_path = "C:/Windows/Fonts/segoepr.ttf"

    font_title = ImageFont.truetype(font_bold_path, 46)
    font_sub = ImageFont.truetype(font_regular_path, 22)
    font_small = ImageFont.truetype(font_regular_path, 20)
    font_header_bold = ImageFont.truetype(font_bold_path, 24)
    
    # Handwritten fonts
    font_hand_lg = ImageFont.truetype(font_hand_path, 38)
    font_hand_md = ImageFont.truetype(font_hand_path, 34)
    font_hand_sm = ImageFont.truetype(font_hand_path, 30)
    font_hand_italic = ImageFont.truetype("C:/Windows/Fonts/segoesc.ttf", 32)

    # 2. Outer Bill Book Border
    margin = 80
    draw.rectangle(
        [(margin, margin), (width - margin, height - margin)],
        outline=(140, 40, 40),
        width=3,
    )
    draw.rectangle(
        [(margin + 6, margin + 6), (width - margin - 6, height - margin - 6)],
        outline=(180, 80, 80),
        width=1,
    )

    # 3. Pre-Printed Header (Red / Maroon ink typical of Indian cash memos)
    header_color = (130, 25, 25)
    text_color = (40, 40, 40)
    blue_ink = (22, 50, 115)  # Ballpoint pen blue

    draw.text((margin + 30, margin + 25), "TAX INVOICE / CASH MEMO", fill=header_color, font=font_small)
    draw.text((width - margin - 320, margin + 25), "GSTIN: 27AABCS1429B1Z2", fill=(60, 60, 60), font=font_small)

    title_text = "SRI BALAJI ELECTRICALS & HARDWARE"
    bbox_title = draw.textbbox((0, 0), title_text, font=font_title)
    t_w = bbox_title[2] - bbox_title[0]
    draw.text(((width - t_w) / 2, margin + 60), title_text, fill=header_color, font=font_title)

    sub1 = "Wholesale & Retail: Electrical Cables, Switches, LED Fixtures, PVC Conduit & Hardware"
    bbox_sub1 = draw.textbbox((0, 0), sub1, font=font_sub)
    draw.text(((width - (bbox_sub1[2] - bbox_sub1[0])) / 2, margin + 120), sub1, fill=(60, 60, 60), font=font_sub)

    sub2 = "Shop No. 14, APMC Commercial Complex, Main Road, Kolhapur - 416005 | Ph: 0231-2654892, 98452 71829"
    bbox_sub2 = draw.textbbox((0, 0), sub2, font=font_small)
    draw.text(((width - (bbox_sub2[2] - bbox_sub2[0])) / 2, margin + 155), sub2, fill=(80, 80, 80), font=font_small)

    # Horizontal divider
    draw.line([(margin + 10, margin + 195), (width - margin - 10, margin + 195)], fill=(160, 50, 50), width=2)

    # 4. Customer Details & Invoice Info (Pre-printed labels with handwritten fills)
    y_info = margin + 215

    # Invoice No & Date
    draw.text((margin + 30, y_info), "Invoice No.:", fill=text_color, font=font_header_bold)
    draw.text((margin + 185, y_info - 4), "SB-8492", fill=blue_ink, font=font_hand_lg)
    draw.line([(margin + 180, y_info + 30), (margin + 380, y_info + 30)], fill=(180, 180, 180), width=1)

    draw.text((width - margin - 350, y_info), "Date:", fill=text_color, font=font_header_bold)
    draw.text((width - margin - 270, y_info - 4), "10-11-2026", fill=blue_ink, font=font_hand_lg)
    draw.line([(width - margin - 280, y_info + 30), (width - margin - 30, y_info + 30)], fill=(180, 180, 180), width=1)

    # Customer Name & Phone
    y_info += 55
    draw.text((margin + 30, y_info), "Customer Name (M/s):", fill=text_color, font=font_header_bold)
    draw.text((margin + 290, y_info - 6), "Apex Infra & Electrical Contractors", fill=blue_ink, font=font_hand_lg)
    draw.line([(margin + 285, y_info + 30), (width - margin - 30, y_info + 30)], fill=(180, 180, 180), width=1)

    y_info += 50
    draw.text((margin + 30, y_info), "Delivery Site / Address:", fill=text_color, font=font_header_bold)
    draw.text((margin + 300, y_info - 6), "Site 4, MIDC Industrial Area, Shiroli", fill=blue_ink, font=font_hand_md)
    draw.line([(margin + 295, y_info + 30), (width - margin - 30, y_info + 30)], fill=(180, 180, 180), width=1)

    # 5. Table Header & Ruled Columns
    table_top = y_info + 60
    table_bottom = height - margin - 420

    col_x = [
        margin + 10,       # 0: Left edge
        margin + 90,       # 1: S.No end
        width - margin - 560, # 2: Description end
        width - margin - 400, # 3: Qty end
        width - margin - 220, # 4: Rate end
        width - margin - 10,  # 5: Amount end
    ]

    # Pre-printed Table Box & Column Dividers
    draw.rectangle([(col_x[0], table_top), (col_x[-1], table_bottom)], outline=(120, 30, 30), width=2)
    header_h = 45
    draw.rectangle([(col_x[0], table_top), (col_x[-1], table_top + header_h)], fill=(245, 230, 230), outline=(120, 30, 30), width=1)

    # Table Column Names
    headers = [
        ("S.N.", (col_x[0] + col_x[1]) / 2),
        ("DESCRIPTION OF GOODS", (col_x[1] + col_x[2]) / 2),
        ("QTY", (col_x[2] + col_x[3]) / 2),
        ("RATE (Rs)", (col_x[3] + col_x[4]) / 2),
        ("AMOUNT (Rs)", (col_x[4] + col_x[5]) / 2),
    ]

    for title, center_x in headers:
        bb = draw.textbbox((0, 0), title, font=font_header_bold)
        draw.text((center_x - (bb[2] - bb[0]) / 2, table_top + 10), title, fill=header_color, font=font_header_bold)

    # Vertical column lines
    for cx in col_x[1:-1]:
        draw.line([(cx, table_top), (cx, table_bottom)], fill=(160, 80, 80), width=1)

    # Pre-printed faint ruled row lines (typical bill book)
    row_height = 55
    curr_y = table_top + header_h
    while curr_y < table_bottom:
        draw.line([(col_x[0], curr_y), (col_x[-1], curr_y)], fill=(210, 215, 225), width=1)
        curr_y += row_height

    # 6. Realistic Handwritten Line Items
    items = [
        ("1", "25mm Heavy PVC Conduit Pipes (3m)", "12", "185.00", "2220.00"),
        ("2", "Anchor Roma 6A Modular Switch 1-Way", "24", "45.00", "1080.00"),
        ("3", "Finolex 1.5 sq mm FR Copper Wire 90m", "2", "1450.00", "2900.00"),
        ("4", "Havells 16A Single Pole C-Curve MCB", "4", "210.00", "840.00"),
        ("5", "Cello Electrical Insulation Tape (Blue)", "10", "15.00", "150.00"),
        ("6", "Anchor 3-Pin Multi Plug Top 6A", "6", "85.00", "510.00"),
        ("7", "PVC Surface Junction Box 4-Way", "15", "32.00", "480.00"),
    ]

    item_y = table_top + header_h + 10
    for s_no, desc, qty, rate, amt in items:
        # Slight jitter to mimic real human pen pressure and placement
        dy = random.uniform(-2, 2)
        
        # S.No
        draw.text((col_x[0] + 28, item_y + dy), s_no, fill=blue_ink, font=font_hand_md)
        # Description
        draw.text((col_x[1] + 20, item_y + dy), desc, fill=blue_ink, font=font_hand_md)
        # Qty (right-aligned)
        q_bb = draw.textbbox((0, 0), qty, font=font_hand_md)
        draw.text((col_x[3] - 25 - (q_bb[2] - q_bb[0]), item_y + dy), qty, fill=blue_ink, font=font_hand_md)
        # Rate (right-aligned)
        r_bb = draw.textbbox((0, 0), rate, font=font_hand_md)
        draw.text((col_x[4] - 25 - (r_bb[2] - r_bb[0]), item_y + dy), rate, fill=blue_ink, font=font_hand_md)
        # Amount (right-aligned)
        a_bb = draw.textbbox((0, 0), amt, font=font_hand_md)
        draw.text((col_x[5] - 25 - (a_bb[2] - a_bb[0]), item_y + dy), amt, fill=blue_ink, font=font_hand_md)

        item_y += row_height

    # 7. Summary & Totals Block (Subtotal, GST, Round-Off, Grand Total)
    y_totals = table_bottom + 15

    # Left Section: Amount in words & Bank Details
    draw.text((margin + 20, y_totals), "Amount Chargeable (in words):", fill=text_color, font=font_small)
    draw.text((margin + 20, y_totals + 30), "INR Eight Thousand Nine Hundred Ninety Only.", fill=blue_ink, font=font_hand_sm)

    terms_y = y_totals + 85
    draw.text((margin + 20, terms_y), "Terms & Conditions:", fill=(100, 100, 100), font=font_small)
    draw.text((margin + 20, terms_y + 25), "1. Goods once sold will not be taken back without original bill.", fill=(120, 120, 120), font=font_small)
    draw.text((margin + 20, terms_y + 48), "2. Subject to Kolhapur Jurisdiction only.", fill=(120, 120, 120), font=font_small)
    draw.text((margin + 20, terms_y + 71), "3. Payment due within 15 days from bill date.", fill=(120, 120, 120), font=font_small)

    # Right Section: Numeric Totals Box
    t_box_left = col_x[2] + 40
    t_box_right = col_x[5]

    draw.rectangle([(t_box_left, y_totals), (t_box_right, y_totals + 210)], outline=(120, 30, 30), width=1)

    totals_lines = [
        ("Sub Total:", "7580.00"),
        ("CGST @ 9%:", "682.20"),
        ("SGST @ 9%:", "682.20"),
        ("Round Off:", "4.40"),
        ("GRAND TOTAL (Rs):", "8990.00"),
    ]

    ty = y_totals + 8
    for label, val in totals_lines:
        is_grand = "GRAND" in label
        lbl_font = font_header_bold if is_grand else font_small
        val_font = font_hand_lg if is_grand else font_hand_md
        color = (130, 20, 20) if is_grand else text_color

        if is_grand:
            draw.line([(t_box_left, ty - 4), (t_box_right, ty - 4)], fill=(120, 30, 30), width=2)
            draw.rectangle([(t_box_left + 1, ty - 2), (t_box_right - 1, ty + 42)], fill=(245, 235, 235))

        draw.text((t_box_left + 15, ty + (4 if is_grand else 0)), label, fill=color, font=lbl_font)
        v_bb = draw.textbbox((0, 0), val, font=val_font)
        draw.text((t_box_right - 20 - (v_bb[2] - v_bb[0]), ty - (2 if not is_grand else 0)), val, fill=blue_ink if not is_grand else (10, 30, 90), font=val_font)

        ty += 42

    # 8. Signature & Stamp Area
    sig_y = height - margin - 150
    draw.text((margin + 30, sig_y + 45), "Customer's Signature", fill=(100, 100, 100), font=font_small)
    draw.line([(margin + 20, sig_y + 40), (margin + 240, sig_y + 40)], fill=(160, 160, 160), width=1)

    sig_right_x = width - margin - 340
    draw.text((sig_right_x, sig_y - 25), "For SRI BALAJI ELECTRICALS", fill=header_color, font=font_header_bold)
    
    # Realistic handwritten signature
    draw.text((sig_right_x + 30, sig_y + 5), "S.Balaji Patil", fill=blue_ink, font=font_hand_italic)
    draw.text((sig_right_x + 20, sig_y + 55), "Authorised Signatory", fill=(100, 100, 100), font=font_small)
    draw.line([(sig_right_x, sig_y + 50), (sig_right_x + 260, sig_y + 50)], fill=(160, 160, 160), width=1)

    # 9. Realistic Rubber Stamp (Purple/Violet ink circular stamp)
    stamp_img = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(stamp_img)
    stamp_purple = (75, 0, 130, 160)  # Indigo/Purple translucent stamp

    s_draw.ellipse([(10, 10), (210, 210)], outline=stamp_purple, width=3)
    s_draw.ellipse([(18, 18), (202, 202)], outline=stamp_purple, width=1)
    
    font_stamp = ImageFont.truetype(font_bold_path, 16)
    s_draw.text((42, 60), "SRI BALAJI ELECT.", fill=stamp_purple, font=font_stamp)
    s_draw.text((58, 95), "PAID & VERIFIED", fill=stamp_purple, font=font_stamp)
    s_draw.text((68, 130), "KOLHAPUR", fill=stamp_purple, font=font_stamp)

    # Rotate stamp slightly for natural angled stamping
    rotated_stamp = stamp_img.rotate(14, expand=True, resample=Image.BICUBIC)
    img.paste(rotated_stamp, (sig_right_x - 40, sig_y - 45), rotated_stamp)

    # 10. Add subtle smartphone photography characteristics:
    # Soft lighting gradient / vignette across the paper (top-left lighter, bottom-right slightly darker)
    y_coords, x_coords = np.mgrid[0:height, 0:width]
    diag = (x_coords / width) * 0.08 + (y_coords / height) * 0.06
    shading = (1.0 - diag)
    img_arr = np.array(img, dtype=np.float32)
    img_arr = img_arr * shading[:, :, np.newaxis]
    img_arr = np.clip(img_arr, 0, 255).astype(np.uint8)
    
    final_img = Image.fromarray(img_arr)

    # Slight camera perspective tilt (0.6 degrees)
    final_img = final_img.rotate(0.6, resample=Image.BICUBIC, expand=False, fillcolor=(240, 238, 232))

    # Save as high-quality JPEG
    output_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(output_path, "JPEG", quality=95)
    print(f"[+] Successfully generated realistic invoice at: {output_path}")


if __name__ == "__main__":
    out_file = Path("sample_dataset/real_handwritten_invoice.jpg")
    create_realistic_invoice(out_file)
