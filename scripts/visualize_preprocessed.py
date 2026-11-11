"""Run the ImagePreprocessor on any input image and export enhanced RGB image."""

import argparse
import sys
from pathlib import Path

# Ensure repository root is on sys.path
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from backend.app.services.preprocessor import preprocessor


def main():
    parser = argparse.ArgumentParser(description="Preprocess an image and export visual outputs.")
    parser.add_argument(
        "image_path",
        nargs="?",
        default="sample_dataset/sample_invoice.png",
        help="Path to the input document image (default: sample_dataset/sample_invoice.png)",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="backend/data/processed_output",
        help="Directory to save preprocessed outputs (default: backend/data/processed_output)",
    )
    args = parser.parse_args()

    input_path = Path(args.image_path)
    if not input_path.exists():
        print(f"Error: Input image not found at {input_path}")
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading image from: {input_path}")
    raw_bytes = input_path.read_bytes()

    print("Running 4-stage ImagePreprocessor pipeline...")
    bundle = preprocessor.process(raw_bytes)

    enhanced_file = output_dir / f"{input_path.stem}_enhanced.jpg"
    enhanced_file.write_bytes(bundle.enhanced_rgb_bytes)

    print("\n--- Preprocessing Results ---")
    print(f"Dimensions:    {bundle.width}x{bundle.height}")
    print(f"Deskew Angle:  {bundle.deskew_angle:.2f} deg")
    print(f"Enhanced RGB:  {enhanced_file} ({len(bundle.enhanced_rgb_bytes):,} bytes)")
    print("Done!\n")


if __name__ == "__main__":
    main()

