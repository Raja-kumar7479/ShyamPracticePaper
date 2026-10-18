_IMAGE_SIGNATURES = [
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
]


def sniff_image_ext(file_storage):
    try:
        head = file_storage.stream.read(16)
        file_storage.stream.seek(0)
    except Exception:
        return None
    if not head:
        return None
    for signature, ext in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return ext
    if head[:4] == b"RIFF" and b"WEBP" in head[:16]:
        return "webp"
    return None


def is_real_image(file_storage):
    return sniff_image_ext(file_storage) is not None
