"""Prepare the photos in /config/www/photos for the 1st-gen iPad frame.

Run by shell_command.resize_photos (see homeassistant/automations.yaml).

Albums
- Every sub-folder of /config/www/photos is an album (e.g. photos/Holidays/).
- Pictures dropped straight into /config/www/photos are moved into the default
  album folder (DEFAULT_ALBUM), so the old "just copy them in" habit keeps working.
- EXTRA_ALBUMS are created as empty folders if they don't exist yet.
- The album list is written to /config/www/photos/albums.json; the frame reads it.

Resizing
- Pictures are scaled down (aspect ratio kept) to fit MAX x MAX, or WIDE x MAX for
  landscape ones (the frame slides those across the screen, so they get more pixels),
  turned upright using their EXIF orientation and saved back under the same name.
- Files modified in the last few seconds are skipped (they may still be copying);
  the next run picks them up.
- Stops resizing after ~45 s so it stays inside shell_command's 60 s limit; the rest is
  handled on the next run. albums.json is always written.
"""
import json
import os
import sys
import time

FOLDER = "/config/www/photos"
DEFAULT_ALBUM = "Photos"     # loose pictures in /config/www/photos are moved here
EXTRA_ALBUMS = []            # album folders to create up front, e.g. ["Holidays", "Art"]
MAX = 1024
WIDE = 1536          # landscape photos: up to 1536 px wide
QUALITY = 85
SETTLE = 15          # seconds a file must be unchanged before we touch it
BUDGET = 45          # seconds per run
EXTS = (".jpg", ".jpeg", ".png")

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None

start = time.time()
done = skipped = failed = moved = 0


def is_photo(path, name):
    return not name.startswith(".") and name.lower().endswith(EXTS) and os.path.isfile(path)


def settled(path):
    return time.time() - os.path.getmtime(path) >= SETTLE


# 1) album folders
for name in [DEFAULT_ALBUM] + EXTRA_ALBUMS:
    os.makedirs(os.path.join(FOLDER, name), exist_ok=True)

# 2) photos in the top folder go into the default album
for name in sorted(os.listdir(FOLDER)):
    path = os.path.join(FOLDER, name)
    if not is_photo(path, name):
        continue
    if not settled(path):
        skipped += 1
        continue
    dest = os.path.join(FOLDER, DEFAULT_ALBUM, name)
    if os.path.exists(dest):
        stem, ext = os.path.splitext(name)
        n = 2
        while os.path.exists(os.path.join(FOLDER, DEFAULT_ALBUM, "%s-%d%s" % (stem, n, ext))):
            n += 1
        dest = os.path.join(FOLDER, DEFAULT_ALBUM, "%s-%d%s" % (stem, n, ext))
    try:
        os.replace(path, dest)
        moved += 1
    except OSError as err:
        failed += 1
        print("move failed: %s: %s" % (name, err))

albums = sorted(
    (d for d in os.listdir(FOLDER) if not d.startswith(".") and os.path.isdir(os.path.join(FOLDER, d))),
    key=lambda d: (d != DEFAULT_ALBUM, d.lower()),
)


# 3) shrink
def shrink(folder, name):
    global done, failed, skipped
    path = os.path.join(folder, name)
    if not settled(path):
        skipped += 1
        return
    tmp = os.path.join(folder, ".resize-" + name)   # dot-files are ignored by the frame
    try:
        with Image.open(path) as im:
            rot = im.getexif().get(0x0112, 1)
            w, h = im.size
            if rot in (5, 6, 7, 8):
                w, h = h, w          # EXIF says the picture is turned 90 degrees
            box = (WIDE, MAX) if w > h else (MAX, MAX)
            if w <= box[0] and h <= box[1] and rot == 1:
                return
            fmt = im.format
            im = ImageOps.exif_transpose(im)
            im.thumbnail(box, Image.LANCZOS)
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
            os.remove(tmp)
        except OSError:
            pass


index = []
for album in albums:
    folder = os.path.join(FOLDER, album)
    files = []
    for name in sorted(os.listdir(folder), key=str.lower):
        path = os.path.join(folder, name)
        if not is_photo(path, name):
            continue
        if Image is not None and time.time() - start < BUDGET:
            shrink(folder, name)
        files.append(album + "/" + name)
    index.append({"name": album, "files": files})

# 4) album list for the frame
tmp = os.path.join(FOLDER, ".albums.json")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"default": DEFAULT_ALBUM, "albums": index, "updated": int(time.time())}, f, ensure_ascii=False)
os.replace(tmp, os.path.join(FOLDER, "albums.json"))

print("albums=%d moved=%d resized=%d waiting=%d failed=%d pillow=%s" % (
    len(index), moved, done, skipped, failed,
    (Image.__version__ if hasattr(Image, "__version__") else "?") if Image is not None else "missing"))
