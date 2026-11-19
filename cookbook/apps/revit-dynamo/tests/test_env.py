"""A pandas that does not load is hidden (Dynamo's pandas with numpy 2)."""

import sys

import pytest

from ir_dynamo import env


@pytest.fixture
def clean_import_state(monkeypatch):
    """No pandas module and the meta path of the test run, restored afterwards."""
    for name in [n for n in sys.modules if n == "pandas" or n.startswith("pandas.")]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", list(sys.meta_path))
    monkeypatch.setattr(sys, "path", list(sys.path))
    yield
    for name in [n for n in sys.modules if n == "pandas" or n.startswith("pandas.")]:
        del sys.modules[name]


def _fake_pandas(folder, body):
    package = folder / "pandas"
    package.mkdir()
    (package / "__init__.py").write_text(body)
    sys.path.insert(0, str(folder))


def test_a_pandas_that_raises_valueerror_is_hidden(tmp_path, clean_import_state):
    _fake_pandas(
        tmp_path,
        "import pandas._libs\n",
    )
    (tmp_path / "pandas" / "_libs.py").write_text(
        "raise ValueError('numpy.dtype size changed, may indicate binary incompatibility')\n"
    )
    assert env.hide_broken_pandas() is True
    assert not any(n == "pandas" or n.startswith("pandas.") for n in sys.modules)
    with pytest.raises(ImportError):
        import pandas  # noqa: F401
    assert env.hide_broken_pandas() is True
    assert sum(getattr(f, "_infrared_hides", None) == "pandas" for f in sys.meta_path) == 1


def test_a_pandas_that_loads_stays(tmp_path, clean_import_state):
    _fake_pandas(tmp_path, "__version__ = '9.9.9'\n")
    assert env.hide_broken_pandas() is False
    import pandas

    assert pandas.__version__ == "9.9.9"
