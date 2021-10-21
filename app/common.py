import os

def get_build_version():
    return os.getenv("OPENSHIFT_BUILD_COMMIT", "Unknown")
