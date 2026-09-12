import os

import pytest

from app.utils import safe_join, sanitize_filename


# --- sanitize_filename ------------------------------------------------

def test_sanitize_filename_keeps_a_plain_name():
    assert sanitize_filename("photo.jpg") == "photo.jpg"


def test_sanitize_filename_strips_directory_components():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("/etc/passwd") == "passwd"


def test_sanitize_filename_strips_null_bytes():
    assert sanitize_filename("evil\x00.jpg") == "evil.jpg"


@pytest.mark.parametrize("name", ["", None, ".", ".."])
def test_sanitize_filename_rejects_empty_or_dot_names(name):
    with pytest.raises(ValueError):
        sanitize_filename(name)


# --- safe_join ----------------------------------------------------------

def test_safe_join_resolves_inside_the_folder(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()

    result = safe_join(str(folder), "photo.jpg")

    assert result == os.path.realpath(os.path.join(str(folder), "photo.jpg"))


def test_safe_join_neutralizes_traversal_in_the_filename(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()

    # sanitize_filename already reduces this to "passwd" via os.path.basename,
    # so the result must land inside `folder`, never at the real /etc/passwd.
    result = safe_join(str(folder), "../../../etc/passwd")

    folder_real = os.path.realpath(str(folder))
    assert result == os.path.join(folder_real, "passwd")
    assert result.startswith(folder_real + os.sep)


def test_safe_join_rejects_a_symlink_that_escapes_the_folder(tmp_path):
    """sanitize_filename can only strip path components out of the
    user-supplied name - it can't see that a filename which passes through
    fine (no "..", no separators) resolves, via a symlink already sitting
    in the folder, to a file outside it. That's what safe_join's realpath
    check is actually for."""
    folder = tmp_path / "uploads"
    folder.mkdir()

    outside = tmp_path / "secret.txt"
    outside.write_text("top secret")

    escape_link = folder / "innocent.txt"
    escape_link.symlink_to(outside)

    with pytest.raises(ValueError):
        safe_join(str(folder), "innocent.txt")


def test_safe_join_allows_a_symlink_that_stays_inside_the_folder(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()

    real_file = folder / "real.txt"
    real_file.write_text("fine")

    link = folder / "alias.txt"
    link.symlink_to(real_file)

    result = safe_join(str(folder), "alias.txt")

    assert result == os.path.realpath(str(real_file))


def test_safe_join_rejects_empty_filename(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()

    with pytest.raises(ValueError):
        safe_join(str(folder), "")
