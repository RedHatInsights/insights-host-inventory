def test_plugin_accessible(application):
    """# NOQA: M765
    Tests accessibility of the plugin
    """
    assert hasattr(application, "host_inventory") is True
