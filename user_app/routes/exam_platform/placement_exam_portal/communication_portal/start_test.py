import os
from config import Config

UPLOAD_FOLDER_AUDIO = os.path.join(Config.UPLOAD_BASE, 'audio_checks')
UPLOAD_FOLDER_RESP = os.path.join(Config.UPLOAD_BASE, 'user_responses')
UPLOAD_FOLDER_SNAP = os.path.join(Config.UPLOAD_BASE, 'proctor_snaps')

for folder in [UPLOAD_FOLDER_AUDIO, UPLOAD_FOLDER_RESP, UPLOAD_FOLDER_SNAP]:
    os.makedirs(folder, exist_ok=True)
