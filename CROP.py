from pathlib import Path
from io import BytesIO
from PIL import Image, ImageOps
from mutagen.flac import FLAC, Picture

# Set path to your music folder
music_folder_input = input("ENTER THE PATH: ").strip().strip('"')
MUSIC_FOLDER = Path(music_folder_input)

def crop_to_center_square(image):
    """Crops a PIL image to a 1:1 ratio centered directly in the middle of the cover."""
    image = ImageOps.exif_transpose(image)
    width, height = image.size
    
    if width == height:
        return image, False  # Already square

    # Use the shorter side as the square dimension
    min_dim = min(width, height)

    # Calculate center offsets
    left = (width - min_dim) // 2
    top = (height - min_dim) // 2
    right = left + min_dim
    bottom = top + min_dim

    return image.crop((left, top, right, bottom)), True

def process_flac_crop(file_path):
    try:
        flac = FLAC(file_path)

        if not flac.pictures:
            print(f"⚠️  No cover art found: {file_path.name}")
            return

        existing_picture = flac.pictures[0]
        img = Image.open(BytesIO(existing_picture.data))
        orig_w, orig_h = img.size

        # Center-crop image to 1:1
        cropped_img, was_cropped = crop_to_center_square(img)

        if not was_cropped:
            print(f"✅ Already 1:1 square ({orig_w}x{orig_h}): {file_path.name}")
            return

        # Ensure clean RGB format
        if cropped_img.mode != "RGB":
            cropped_img = cropped_img.convert("RGB")

        # Save cropped result to memory buffer
        output_buffer = BytesIO()
        cropped_img.save(output_buffer, format="JPEG", quality=100, subsampling=0)
        new_cover_bytes = output_buffer.getvalue()

        # Update FLAC picture tag
        flac.clear_pictures()

        picture = Picture()
        picture.type = 3  # Front Cover
        picture.mime = "image/jpeg"
        picture.desc = "Front Cover"
        picture.data = new_cover_bytes

        flac.add_picture(picture)
        flac.save()

        new_w, new_h = cropped_img.size
        print(f"✂️  Center-cropped to 1:1 ({orig_w}x{orig_h} -> {new_w}x{new_h}): {file_path.name}")

    except Exception as e:
        print(f"❌ Error processing {file_path.name}: {e}")

def main():
    if not MUSIC_FOLDER.exists():
        print(f"Folder non-existent: {MUSIC_FOLDER}")
        return

    files = list(MUSIC_FOLDER.rglob("*.flac"))
    print(f"Found {len(files)} FLAC file(s). Center cropping cover art to 1:1 square...\n")

    for file in files:
        process_flac_crop(file)

    print("\nProcessing complete!")

if __name__ == "__main__":
    main()