import os, subprocess
# Verificar rclone
r = subprocess.run(["which", "rclone"], capture_output=True, text=True)
print("rclone path:", r.stdout.strip() or "NOT FOUND")

# Verificar conf
conf = os.environ.get("RCLONE_CONFIG", "/opt/ejc/config/rclone.conf")
print("RCLONE_CONFIG env:", conf)
print("conf exists:", os.path.exists(conf))

# Testar DRIVE_AVAILABLE do service
from app.services.google_drive import DRIVE_AVAILABLE, upload_file
print("DRIVE_AVAILABLE:", DRIVE_AVAILABLE)

if DRIVE_AVAILABLE:
    try:
        result = upload_file(b"teste ejc drive ok", "teste_ejc_drive.txt", "text/plain")
        print("UPLOAD OK:", result)
    except Exception as e:
        print("UPLOAD ERRO:", e)
else:
    print("Drive nao disponivel — verificar RCLONE_CONFIG e rclone.conf")
