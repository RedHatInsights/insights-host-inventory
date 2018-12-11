import os


class Config:
    def __init__(self, config_name):
        self.config_name = config_name

        self.db_user = os.getenv("INVENTORY_DB_USER", "insights")
        self.db_password = os.getenv("INVENTORY_DB_PASS", "insights")
        self.db_host = os.getenv("INVENTORY_DB_HOST", "localhost")
        self.db_name = os.getenv("INVENTORY_DB_NAME", "test_db")
        self.db_pool_timeout = int(os.getenv("INVENTORY_DB_POOL_TIMEOUT", "5"))
        self.db_pool_size = int(os.getenv("INVENTORY_DB_POOL_SIZE", "5"))

        self.base_url_path = self._get_base_url_path()
        self.api_path = self._get_api_path()

        if config_name != "testing":
            print("Insights Host Inventory Configuration:")
            print("Base URL Path: %s" % self.base_url_path)
            print("API URL Path: %s" % self.api_path)
            print("DB Host: %s" % self.db_host)
            print("DB Name: %s" % self.db_name)

    def getDBUri(self):
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}/{self.db_name}"

    def getDBPoolTimeout(self):
        return self.db_pool_timeout

    def getDBPoolSize(self):
        return self.db_pool_size

    def getApiPath(self):
        return self.api_path

    def getBaseUrlPath(self):
        return self.base_url_path

    def _get_base_url_path(self):
        app_name = os.getenv("APP_NAME", "inventory")
        path_prefix = os.getenv("PATH_PREFIX", "/r/insights/platform")
        base_url_path = f"{path_prefix}/{app_name}"
        return base_url_path

    def _get_api_path(self):
        base_url_path = self._get_base_url_path()
        version = "v1"
        api_path = f"{base_url_path}/api/{version}"
        return api_path
