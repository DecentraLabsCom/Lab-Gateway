from temp_cleanup import cleanup_fmu_temp_files


def test_cleanup_fmu_temp_files_removes_only_matching_extraction_directories(tmp_path):
    matching = tmp_path / "tmp-fmu-match"
    matching.mkdir()
    (matching / "modelDescription.xml").write_text("<fmiModelDescription />", encoding="utf-8")

    missing_model_description = tmp_path / "tmp-fmu-missing"
    missing_model_description.mkdir()
    (missing_model_description / "other.txt").write_text("keep", encoding="utf-8")

    unrelated = tmp_path / "fmu-unrelated"
    unrelated.mkdir()
    (unrelated / "modelDescription.xml").write_text("keep", encoding="utf-8")

    assert cleanup_fmu_temp_files(tmp_path) == 1
    assert not matching.exists()
    assert missing_model_description.exists()
    assert unrelated.exists()


def test_cleanup_fmu_temp_files_ignores_removal_errors(tmp_path, monkeypatch):
    matching = tmp_path / "tmp-fmu-match"
    matching.mkdir()
    (matching / "modelDescription.xml").write_text("<fmiModelDescription />", encoding="utf-8")

    def fail_remove(_path):
        raise OSError("busy")

    monkeypatch.setattr("temp_cleanup.shutil.rmtree", fail_remove)

    assert cleanup_fmu_temp_files(tmp_path) == 0
    assert matching.exists()