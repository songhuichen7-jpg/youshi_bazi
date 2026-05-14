from paipan import VERSION

def test_version_exported():
    assert isinstance(VERSION, str)
    assert VERSION.count(".") == 2
