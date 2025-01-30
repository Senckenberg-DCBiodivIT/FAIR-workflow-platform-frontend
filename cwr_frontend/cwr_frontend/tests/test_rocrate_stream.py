import tempfile
import requests_mock
import json

from rocrate.rocrate import ROCrate
from cwr_frontend.rocrate_utils import stream_ROCrate
from zipfile import ZipFile


def test_ro_crate_stream():
    crate = ROCrate(gen_preview=True)
    stream = stream_ROCrate(crate)

    with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as f:
        # write zip to file
        for chunk in stream:
            f.write(chunk)

        f.flush()
        f.seek(0)

        # read zip and assert content

        with ZipFile(f.name, "r") as myzip:
            assert len(myzip.infolist()) == 2
            names = list(map(lambda info: info.filename, myzip.infolist()))
            assert "ro-crate-metadata.json" in names
            assert "ro-crate-preview.html" in names

            with myzip.open("ro-crate-metadata.json") as metadata:
                lines = metadata.read().decode("utf-8")
                assert lines == json.dumps(crate.metadata.generate(), indent=4)


def test_ro_crate_stream_file_by_name():
    with tempfile.NamedTemporaryFile(mode="w") as testfile:
        testfile.write("hello world")
        testfile.flush()
        testfile.seek(0)

        crate = ROCrate(gen_preview=True)
        crate.add_file(testfile.name, dest_path="test.txt")

        stream = stream_ROCrate(crate)

        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as f:
            # write zip to file
            for chunk in stream:
                f.write(chunk)

            f.flush()
            f.seek(0)

            # read zip and assert content
            with ZipFile(f.name, "r") as myzip:
                assert len(myzip.infolist()) == 3

                with myzip.open("test.txt") as read_testfile:
                    lines = read_testfile.read().decode("utf-8")
                    assert lines == "hello world"


def test_ro_crate_stream_io():
    with tempfile.NamedTemporaryFile(mode="wb") as testfile:
        testfile.write(b"hello world")
        testfile.flush()
        testfile.seek(0)

        crate = ROCrate(gen_preview=True)
        crate.add_file(open(testfile.name, "r"), dest_path="test.txt")

        stream = stream_ROCrate(crate)

        with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as f:
            # write zip to file
            for chunk in stream:
                f.write(chunk)

            f.flush()
            f.seek(0)

            # read zip and assert content
            with ZipFile(f.name, "r") as myzip:
                assert len(myzip.infolist()) == 3

                with myzip.open("test.txt") as read_testfile:
                    lines = read_testfile.read().decode("utf-8")
                    assert lines == "hello world"


@requests_mock.Mocker(kw="mock")
def test_ro_crate_stream_remote_files(**kwargs):
    remote_file = "https://example.com/myfile" #https://raw.githubusercontent.com/ResearchObject/ro-crate-py/refs/heads/master/test/test-data/sample_file.txt"
    kwargs["mock"].get(remote_file, text="hello remote world")


    crate = ROCrate(gen_preview=True)
    crate.add_file(remote_file, dest_path="test.txt", fetch_remote=True)

    stream = stream_ROCrate(crate)

    with tempfile.NamedTemporaryFile(suffix=".zip", mode="wb") as f:
        # write zip to file
        for chunk in stream:
            f.write(chunk)

        f.flush()
        f.seek(0)

        # read zip and assert content
        with ZipFile(f.name, "r") as myzip:
            assert len(myzip.infolist()) == 3

            with myzip.open("test.txt") as read_testfile:
                lines = read_testfile.read().decode("utf-8")
                assert lines == "hello remote world"
