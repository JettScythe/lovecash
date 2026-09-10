from typer.testing import CliRunner

from lovecash.cli import app


def test_run_command_exists_and_shows_help():
    result = CliRunner().invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "headless" in result.output


def test_all_documented_commands_exist():
    """Every command the README/docs promise must be registered."""
    result = CliRunner().invoke(app, ["--help"])
    for cmd in ("init", "doctor", "run", "serve", "qr", "scripthash"):
        assert cmd in result.output, f"missing documented command: {cmd}"
