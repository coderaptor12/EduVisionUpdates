import os
import shutil

# Paths where the database might be hiding
paths = [
    'eduvision.db',
    'instance/eduvision.db',
    'newcpp/EduVision/instance/eduvision.db'
]

print("--- EduVision DB Reset Tool ---")
for path in paths:
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"✅ Deleted: {path}")
        except Exception as e:
            print(f"❌ Could not delete {path}: {e}")

# Also delete the instance folder just to be safe
if os.path.exists('instance'):
    shutil.rmtree('instance')
    print("✅ Deleted instance folder.")

print("--- Done! Now run your app.py ---")