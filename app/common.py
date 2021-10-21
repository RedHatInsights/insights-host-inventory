import os

#comment blah test
def get_build_version():
    return os.getenv("OPENSHIFT_BUILD_COMMIT", "Unknown")
