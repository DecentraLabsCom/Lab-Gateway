import winrm_command_builders


def test_labstation_command_builder_preserves_executable_and_argument_order():
    assert winrm_command_builders.build_labstation_command(
        r"C:\LabStation\LabStation.exe",
        "status-json",
        ["--json", "value"],
    ) == (
        r"C:\LabStation\LabStation.exe",
        ["status-json", "--json", "value"],
    )


def test_labstation_command_builder_quotes_executable_paths_with_spaces():
    assert winrm_command_builders.build_labstation_command(
        r"C:\Lab Station\LabStation.exe",
        "prepare-session",
        ["--guard-grace=90"],
    ) == (
        r'"C:\Lab Station\LabStation.exe"',
        ["prepare-session", "--guard-grace=90"],
    )


def test_labstation_command_builder_quotes_arguments_with_spaces():
    assert winrm_command_builders.build_labstation_command(
        r"C:\LabStation\LabStation.exe",
        "power",
        ["shutdown", "--reason=Remote order"],
    ) == (
        r"C:\LabStation\LabStation.exe",
        ["power", "shutdown", '"--reason=Remote order"'],
    )


def test_remote_file_builders_escape_single_quotes_for_powershell_literals():
    assert winrm_command_builders.build_read_remote_file_command(r"C:\Lab's\heartbeat.json") == (
        "Get-Content -LiteralPath 'C:\\Lab''s\\heartbeat.json' -Raw -Encoding UTF8"
    )
    assert winrm_command_builders.build_write_remote_file_command(
        r"C:\Lab's\state.txt",
        "it's ready",
    ) == "Set-Content -LiteralPath 'C:\\Lab''s\\state.txt' -Value 'it''s ready' -Encoding UTF8"
    assert winrm_command_builders.build_remove_remote_file_command(r"C:\Lab's\state.txt") == (
        "if (Test-Path -LiteralPath 'C:\\Lab''s\\state.txt') { Remove-Item -LiteralPath 'C:\\Lab''s\\state.txt' -Force }"
    )


def test_read_remote_file_builder_uses_an_empty_literal_for_missing_path():
    assert winrm_command_builders.build_read_remote_file_command(None) == (
        "Get-Content -LiteralPath '' -Raw -Encoding UTF8"
    )
