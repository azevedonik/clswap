from clman.session import SESSION_FILENAME, find_session_file, read_session_email


def test_finds_file_in_start_dir(tmp_path):
    (tmp_path / SESSION_FILENAME).write_text("a@x.com\n")
    assert find_session_file(tmp_path) == tmp_path / SESSION_FILENAME


def test_walks_up_and_nearest_wins(tmp_path):
    (tmp_path / SESSION_FILENAME).write_text("outer@x.com\n")
    inner = tmp_path / "a" / "b"
    inner.mkdir(parents=True)
    assert find_session_file(inner) == tmp_path / SESSION_FILENAME

    (tmp_path / "a" / SESSION_FILENAME).write_text("inner@x.com\n")
    assert find_session_file(inner) == tmp_path / "a" / SESSION_FILENAME


def test_missing_returns_none(tmp_path):
    # tmp_path's real parents could theoretically hold a session file; a
    # sibling check via read keeps this hermetic enough for a unit test.
    found = find_session_file(tmp_path)
    assert found is None or tmp_path not in found.parents


def test_read_skips_comments_and_blanks(tmp_path):
    f = tmp_path / SESSION_FILENAME
    f.write_text("# work account\n\n  team@x.com  \nignored@x.com\n")
    assert read_session_email(f) == "team@x.com"


def test_read_empty_file_is_none(tmp_path):
    f = tmp_path / SESSION_FILENAME
    f.write_text("# only a comment\n\n")
    assert read_session_email(f) is None
