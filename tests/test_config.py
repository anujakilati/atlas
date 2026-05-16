from backend.config import CONFIG

def test_config_loaded():
    assert 'storage' in CONFIG
