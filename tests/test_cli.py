import pytest

from draftvoice import __version__
from draftvoice.cli import main


def test_help_runs_without_a_command(capsys):
    assert main([]) == 0
    assert "draftvoice" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out
