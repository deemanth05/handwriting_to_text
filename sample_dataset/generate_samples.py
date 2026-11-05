"""Generates synthetic test documents with handwriting-like text, stamps, and regional numerals."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

DATASET_DIR = Path(__file__).resolve().parent


def create_sample_invoice():
    img = Image.new("RGB", (800, 1000), color=(250, 248, 242))
    draw = ImageDraw.Draw(img)

    # Header / Merchant
    draw.text((50, 40), "SHREE GANESH GENERAL STORES", fill=(20, 20, 20))
    draw.text((50, 65), "Station Road, Pune - 411001", fill=(80, 80, 80))
    draw.text((50, 90), "GSTIN: 27AABCS1429B1Z1", fill=(80, 80, 80))

    # Meta
    draw.text((550, 40), "Invoice #: INV-2026-089", fill=(30, 30, 30))
    draw.text((550, 65), "Date: 31/10/2026", fill=(30, 30, 30))

    draw.line((50, 120, 750, 120), fill=(180, 180, 180), width=2)

    # Table Header
    draw.text((50, 140), "Item Description", fill=(0, 0, 0))
    draw.text((450, 140), "Qty", fill=(0, 0, 0))
    draw.text((550, 140), "Rate", fill=(0, 0, 0))
    draw.text((670, 140), "Total (Rs)", fill=(0, 0, 0))
    draw.line((50, 170, 750, 170), fill=(200, 200, 200), width=1)

    # Table Rows
    rows = [
        ("Atta Premium 5kg", "2", "240.00", "480.00"),
        ("Toor Dal 1kg", "3", "160.00", "480.00"),
        ("Sunflower Oil 1L", "2", "145.00", "290.00"),
        ("Sugar 2kg", "2", "50.00", "100.00"),
    ]

    y = 200
    for desc, qty, rate, total in rows:
        draw.text((50, y), desc, fill=(30, 30, 30))
        draw.text((460, y), qty, fill=(30, 30, 30))
        draw.text((550, y), rate, fill=(30, 30, 30))
        draw.text((670, y), total, fill=(30, 30, 30))
        y += 40

    draw.line((50, y + 20, 750, y + 20), fill=(180, 180, 180), width=1)
    y += 40

    # Totals
    draw.text((500, y), "Subtotal: Rs. 1350.00", fill=(20, 20, 20))
    draw.text((500, y + 30), "Tax (GST 5%): Rs. 67.50", fill=(20, 20, 20))
    draw.text((500, y + 60), "Discount: Rs. 17.50", fill=(20, 20, 20))
    draw.text((500, y + 95), "Grand Total: Rs. 1400.00", fill=(180, 20, 20))

    # Stamp
    draw.ellipse((100, 700, 250, 850), outline=(200, 40, 40), width=3)
    draw.text((120, 760), "PAID & VERIFIED", fill=(200, 40, 40))

    out_path = DATASET_DIR / "sample_invoice.png"
    img.save(out_path)
    print(f"Created {out_path}")


def create_sample_khata():
    img = Image.new("RGB", (800, 950), color=(253, 250, 240))
    draw = ImageDraw.Draw(img)

    draw.text((50, 40), "Rameshwar Kirana Khata Bahi", fill=(10, 10, 10))
    draw.text((50, 70), "Grahak Naam: Rajesh Patil", fill=(40, 40, 40))
    draw.text((550, 70), "Dinank: 2026-10-25", fill=(40, 40, 40))

    draw.line((50, 110, 750, 110), fill=(150, 150, 150), width=2)

    draw.text((50, 130), "Vigaran (Items)", fill=(0, 0, 0))
    draw.text((450, 130), "Nang (Qty)", fill=(0, 0, 0))
    draw.text((550, 130), "Dar (Rate)", fill=(0, 0, 0))
    draw.text((670, 130), "Rakkam", fill=(0, 0, 0))
    draw.line((50, 160, 750, 160), fill=(200, 200, 200), width=1)

    # Devanagari numerals in rows
    rows = [
        ("Chawal Basmati 10kg", "1", "650", "650"),
        ("Chana Dal 2kg", "2", "90", "180"),
        ("Chai Patti 500g", "1", "170", "170"),
    ]

    y = 190
    for desc, qty, rate, total in rows:
        draw.text((50, y), desc, fill=(30, 30, 30))
        draw.text((460, y), qty, fill=(30, 30, 30))
        draw.text((550, y), rate, fill=(30, 30, 30))
        draw.text((670, y), total, fill=(30, 30, 30))
        y += 40

    draw.line((50, y + 20, 750, y + 20), fill=(180, 180, 180), width=1)
    y += 50
    draw.text((500, y), "Subtotal: Rs. 1000.00", fill=(20, 20, 20))
    draw.text((500, y + 35), "Jama (Paid): Rs. 500.00", fill=(20, 120, 20))
    draw.text((500, y + 70), "Baki (Closing): Rs. 500.00", fill=(180, 20, 20))

    out_path = DATASET_DIR / "sample_khata.png"
    img.save(out_path)
    print(f"Created {out_path}")


def create_sample_prescription():
    img = Image.new("RGB", (800, 950), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    draw.text((50, 40), "DR. S. K. SHARMA, MD (Medicine)", fill=(10, 40, 120))
    draw.text((50, 65), "Sanjeevani Clinic, MG Road, Mumbai", fill=(60, 60, 60))
    draw.text((550, 65), "Date: 28-10-2026", fill=(30, 30, 30))

    draw.line((50, 100, 750, 100), fill=(10, 40, 120), width=2)
    draw.text((50, 120), "Patient: Mrs. Ananya Deshmukh | Age: 42 | Gender: F", fill=(30, 30, 30))

    draw.text((50, 170), "Rx:", fill=(10, 40, 120))
    meds = [
        "1. Tab Paracetamol 650mg - 1-0-1 (After food) - 5 days",
        "2. Cap Amoxicillin 500mg - 1-0-1 (After food) - 5 days",
        "3. Tab Pantoprazole 40mg - 1-0-0 (Before food) - 7 days",
        "4. Syrup Ascoril LS - 10ml TDS - 5 days",
    ]
    y = 210
    for med in meds:
        draw.text((80, y), med, fill=(20, 20, 20))
        y += 45

    draw.text((50, 500), "Consultation Fee: Rs. 500.00", fill=(50, 50, 50))
    draw.text((550, 500), "Doctor's Signature", fill=(10, 40, 120))

    out_path = DATASET_DIR / "sample_prescription.png"
    img.save(out_path)
    print(f"Created {out_path}")


if __name__ == "__main__":
    create_sample_invoice()
    create_sample_khata()
    create_sample_prescription()
