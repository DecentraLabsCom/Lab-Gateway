import winrm_command_builders


def test_labstation_command_builder_uses_powershell_argument_splatting():
    script = winrm_command_builders.build_labstation_command(
        r"C:\LabStation\LabStation.exe",
        "status-json",
        ["--json", "value"],
    )

    assert "$labStationExe = 'C:\\LabStation\\LabStation.exe'" in script
    assert "$labStationArgs = @('status-json', '--json', 'value')" in script
    assert "& $labStationExe @labStationArgs" in script
    assert "exit $exitCode" in script


def test_labstation_command_builder_preserves_executable_paths_with_spaces():
    script = winrm_command_builders.build_labstation_command(
        r"C:\Lab Station\LabStation.exe",
        "prepare-session",
        ["--guard-grace=90"],
    )

    assert "$labStationExe = 'C:\\Lab Station\\LabStation.exe'" in script
    assert "$labStationArgs = @('prepare-session', '--guard-grace=90')" in script


def test_labstation_command_builder_removes_legacy_outer_executable_quotes():
    script = winrm_command_builders.build_labstation_command(
        r'"C:\Lab Station\LabStation.exe"',
        "power",
        ["shutdown"],
    )

    assert "$labStationExe = 'C:\\Lab Station\\LabStation.exe'" in script
    assert "$labStationArgs = @('power', 'shutdown')" in script


def test_labstation_command_builder_quotes_arguments_with_spaces():
    script = winrm_command_builders.build_labstation_command(
        r"C:\Lab Station\LabStation.exe",
        "power",
        ["shutdown", "--reason=Remote order"],
    )

    assert "$labStationArgs = @('power', 'shutdown', '--reason=Remote order')" in script


def test_labstation_command_builder_escapes_single_quotes_in_arguments():
    script = winrm_command_builders.build_labstation_command(
        r"C:\Lab Station\LabStation.exe",
        "power",
        ["shutdown", "--reason=Provider's order"],
    )

    assert "--reason=Provider''s order" in script


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
