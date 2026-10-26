"""Shrink photos in /config/www/photos so the 1st-gen iPad can show them.

Run by shell_command.resize_photos (automation "Çerçeve fotoğraflarını küçült").
- Pictures larger than MAX px on either side are scaled down (aspect ratio kept),
  turned upright using their EXIF orientation and saved back under the same name.
- Files modified in the last few seconds are skipped (they may still be copying);
  the next run picks them up.
- Stops after ~45 s so it stays inside shell_command's 60 s limit; the rest is
  handled on the next run.
"""
import os
import sys
import time

FOLDER = "/config/www/photos"
MAX = 1024
QUALITY = 85
SETTLE = 15          # seconds a file must be unchanged before we touch it
BUDGET = 45          # seconds per run
EXTS = (".jpg", ".jpeg", ".png")

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow is not available")
    sys.exit(2)

start = time.time()
done = skipped = failed = 0
for name in sorted(os.listdir(FOLDER)):
    if time.time() - start > BUDGET:
        break
    path = os.path.join(FOLDER, name)
    if name.startswith(".") or not name.lower().endswith(EXTS) or not os.path.isfile(path):
        continue
    if time.time() - os.path.getmtime(path) < SETTLE:
        skipped += 1
        continue
    try:
        with Image.open(path) as im:
            if max(im.size) <= MAX and im.getexif().get(0x0112, 1) == 1:
                continue
            fmt = im.format
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX, MAX), Image.LANCZOS)
            tmp = os.path.join(FOLDER, ".resize-" + name)   # dot-files are ignored by the frame
            if fmt == "PNG":
                im.save(tmp, "PNG", optimize=True)
            else:
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
                im.save(tmp, "JPEG", quality=QUALITY, optimize=True, progressive=False)
        os.replace(tmp, path)
        done += 1
    except Exception as err:  # keep going with the other files
        failed += 1
        print("failed: %s: %s" % (name, err))
        try:
            os.remove(os.path.join(FOLDER, ".resize-" + name))
        except OSError:
            pass

print("resized=%d waiting=%d failed=%d pillow=%s" % (done, skipped, failed, Image.__version__ if hasattr(Image, "__version__") else "?"))
