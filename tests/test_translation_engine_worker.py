"""Offline protocol and inference safety tests; no native model is imported."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


WORKER_PATH = Path(__file__).resolve().parents[1] / "translation-engine" / "worker.py"
SPEC = importlib.util.spec_from_file_location("translation_engine_worker", WORKER_PATH)
assert SPEC is not None and SPEC.loader is not None
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


class FakeTokenizer:
    def __init__(self, output: str | None = None) -> None:
        self.output = output
        self.encoded: list[str] = []
        self.decoded: list[list[str]] = []

    def encode(self, text: str, *, out_type: type[str]) -> list[str]:
        assert out_type is str
        self.encoded.append(text)
        return text.split()

    def decode(self, tokens: list[str]) -> str:
        self.decoded.append(tokens)
        return self.output if self.output is not None else " ".join(tokens)


class FakeTranslator:
    def __init__(self) -> None:
        self.calls: list[tuple[list[list[str]], dict[str, object]]] = []

    def translate_batch(
        self, tokens: list[list[str]], **options: object
    ) -> list[SimpleNamespace]:
        self.calls.append((tokens, options))
        return [SimpleNamespace(hypotheses=[
            (row[1:-1] if row[0] == ">>vie<<" else row[:-1]) + ["</s>"]
        ]) for row in tokens]


@pytest.fixture
def engine() -> tuple[FakeTokenizer, FakeTokenizer, FakeTranslator]:
    return FakeTokenizer(), FakeTokenizer(), FakeTranslator()


def request_file(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def model_files(root: Path, *, flat: bool = False) -> Path:
    model = root if flat else root / "model-int8"
    tokenizer = root if flat else root / "model-source"
    model.mkdir(parents=True, exist_ok=True)
    tokenizer.mkdir(parents=True, exist_ok=True)
    (model / "model.bin").write_bytes(b"model")
    (model / "shared_vocabulary.json").write_text("[]", encoding="utf-8")
    (model / "config.json").write_text(
        json.dumps({"add_source_eos": False, "add_source_bos": False,
                    "eos_token": "</s>", "decoder_start_token": "</s>"}),
        encoding="utf-8",
    )
    for name in ("source.spm", "target.spm"):
        (tokenizer / name).write_bytes(b"tokenizer")
    return model


@pytest.mark.parametrize("payload", [
    None, [], {}, {"schema": True, "texts": ["Hi"]},
    {"schema": 1.0, "texts": ["Hi"]}, {"schema": 2, "texts": ["Hi"]},
    {"schema": 1, "texts": "Hi"}, {"schema": 1, "texts": [3]},
    {"schema": 1, "texts": [""]}, {"schema": 1, "texts": [" \n"]},
    {"schema": 1, "texts": ["a\x00b"]}, {"schema": 1, "texts": ["a\tb"]},
    {"schema": 1, "texts": ["a\rb"]}, {"schema": 1, "texts": ["a\x7fb"]},
    {"schema": 1, "texts": ["a\u202eb"]}, {"schema": 1, "texts": ["\ud800"]},
    {"schema": 1, "texts": [], "extra": 1},
])
def test_rejects_invalid_request(tmp_path: Path, payload: object) -> None:
    with pytest.raises(worker.WorkerError):
        worker.read_request(request_file(tmp_path, payload))


def test_request_item_text_and_byte_limits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    accepted = ["hello"] * 10_000
    assert worker.read_request(request_file(tmp_path, {"schema": 1, "texts": accepted})) == accepted
    with pytest.raises(worker.WorkerError):
        worker.read_request(request_file(tmp_path, {"schema": 1, "texts": accepted + ["extra"]}))
    with pytest.raises(worker.WorkerError):
        worker.read_request(request_file(tmp_path, {"schema": 1, "texts": ["x" * 65_537]}))
    monkeypatch.setattr(worker, "MAX_REQUEST_BYTES", 20)
    with pytest.raises(worker.WorkerError):
        worker.read_request(request_file(tmp_path, {"schema": 1, "texts": ["hello"]}))


@pytest.mark.parametrize("raw", [
    b"\xff", b"{", b'{"schema":1,"schema":1,"texts":[]}',
    b'{"schema":1,"texts":[NaN]}', b"[" * 1100,
])
def test_invalid_json_is_rejected(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(worker.WorkerError):
        worker.read_request(path)


def test_newline_and_empty_batch_allowed(tmp_path: Path, engine: tuple) -> None:
    assert worker.read_request(request_file(tmp_path, {"schema": 1, "texts": ["a\nb"]})) == ["a\nb"]
    assert worker.translate_texts([], *engine) == []
    assert engine[2].calls == []


def test_prefix_eos_chunks_order_and_decoding_settings(engine: tuple) -> None:
    source, target, translator = engine
    texts = [f"item{i}" for i in range(35)]
    assert worker.translate_texts(texts, *engine) == texts
    assert source.encoded == texts
    assert [len(rows) for rows, _ in translator.calls] == [16, 16, 3]
    assert translator.calls[0][0][0] == [">>vie<<", "item0", "</s>"]
    assert target.decoded[0] == ["item0"]
    options = translator.calls[0][1]
    assert options["beam_size"] == 3
    assert options["sampling_topk"] == 1
    assert options["max_input_length"] == 0
    assert options["return_end_token"] is True
    assert options["end_token"] == "</s>"
    assert options["max_decoding_length"] == 512


def test_token_limit_includes_prefix_and_eos_and_prevalidates_all(engine: tuple) -> None:
    accepted = " ".join(["x"] * 510)
    assert worker.translate_texts([accepted], *engine) == [accepted]
    engine[2].calls.clear()
    with pytest.raises(worker.WorkerError):
        worker.translate_texts(["ok"] * 16 + [accepted + " x"], *engine)
    assert engine[2].calls == []


@pytest.mark.parametrize("tokens", [
    [], ["</s>"], ["hello"], ["</s>", "later", "</s>"],
    ["<unk>", "</s>"], ["<pad>", "</s>"], [">>vie<<", "</s>"],
    ["x"] * 511 + ["</s>"],
])
def test_rejects_empty_special_missing_eos_or_capped_output(
    engine: tuple, tokens: list[str]
) -> None:
    translator = Mock()
    translator.translate_batch.return_value = [SimpleNamespace(hypotheses=[tokens])]
    with pytest.raises(worker.WorkerError):
        worker.translate_texts(["input"], engine[0], engine[1], translator)


@pytest.mark.parametrize("value", ["", " \n", "a\x00", "a\t", "a\r", "a\x85", "a\u200b", "\udfff"])
def test_rejects_unsafe_decoded_output(engine: tuple, value: str) -> None:
    with pytest.raises(worker.WorkerError):
        worker.translate_texts(["input"], engine[0], FakeTokenizer(value), engine[2])


def test_output_unicode_newline_preserved(engine: tuple) -> None:
    expected = "Cài đặt\nCamera"
    assert worker.translate_texts(
        ["input"], engine[0], FakeTokenizer(expected), engine[2]
    ) == [expected]


@pytest.mark.parametrize("results", [[], [SimpleNamespace(hypotheses=[])],
    [SimpleNamespace(hypotheses=[["a", "</s>"], ["b", "</s>"]])]])
def test_result_shape_must_match_input(engine: tuple, results: list) -> None:
    translator = Mock()
    translator.translate_batch.return_value = results
    with pytest.raises(worker.WorkerError):
        worker.translate_texts(["input"], engine[0], engine[1], translator)


@pytest.mark.parametrize("flat", [True, False])
def test_loads_known_local_paths_and_cpu_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flat: bool
) -> None:
    model = model_files(tmp_path, flat=flat)
    ct2, spm = Mock(), Mock()
    monkeypatch.setitem(sys.modules, "ctranslate2", ct2)
    monkeypatch.setitem(sys.modules, "sentencepiece", spm)
    monkeypatch.setattr(worker.os, "cpu_count", lambda: 64)
    worker.load_engine(model)
    assert ct2.Translator.call_args.args == (str(model.resolve()),)
    assert ct2.Translator.call_args.kwargs == {
        "device": "cpu", "compute_type": "int8", "inter_threads": 1, "intra_threads": 4,
    }
    expected = model if flat else tmp_path / "model-source"
    assert [call.kwargs["model_file"] for call in spm.SentencePieceProcessor.call_args_list] == [
        str(expected / "source.spm"), str(expected / "target.spm")]


@pytest.mark.parametrize("cpu_count, expected", [(None, 1), (1, 1), (2, 2)])
def test_thread_budget_for_small_hosts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    cpu_count: int | None, expected: int,
) -> None:
    model = model_files(tmp_path, flat=True)
    ct2 = Mock()
    monkeypatch.setitem(sys.modules, "ctranslate2", ct2)
    monkeypatch.setitem(sys.modules, "sentencepiece", Mock())
    monkeypatch.setattr(worker.os, "cpu_count", lambda: cpu_count)
    worker.load_engine(model)
    assert ct2.Translator.call_args.kwargs["intra_threads"] == expected


def test_bad_model_contract_and_missing_file_rejected(tmp_path: Path) -> None:
    model = model_files(tmp_path, flat=True)
    (model / "config.json").write_text('{"add_source_eos":true}', encoding="utf-8")
    with pytest.raises(worker.WorkerError):
        worker.load_engine(model)
    (model / "target.spm").unlink()
    with pytest.raises(worker.WorkerError):
        worker.load_engine(model)


def test_success_is_atomic_utf8_and_does_not_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "response.json"
    payload = {"schema": 1, "translations": ["Cài đặt"]}
    worker.write_response(path, payload)
    original = path.read_bytes()
    assert json.loads(original) == payload
    assert "Cài đặt".encode() in original
    with pytest.raises(FileExistsError):
        worker.write_response(path, {"schema": 1, "translations": ["changed"]})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_failure_cleans_owned_temp_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    keep = tmp_path / "unrelated.tmp"
    keep.write_bytes(b"keep")
    monkeypatch.setattr(worker.os, "link", Mock(side_effect=OSError("failure")))
    with pytest.raises(OSError):
        worker.write_response(tmp_path / "response.json", {"schema": 1, "translations": []})
    assert list(tmp_path.iterdir()) == [keep]


def test_cli_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    engine: tuple, capsys: pytest.CaptureFixture,
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["hello", "world"]})
    response = tmp_path / "response.json"
    monkeypatch.setattr(worker, "load_engine", lambda _: engine)
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(response),
    ]) == 0
    assert json.loads(response.read_bytes()) == {"schema": 1, "translations": ["hello", "world"]}
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_late_failure_never_exposes_partial_results_or_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    engine: tuple, capsys: pytest.CaptureFixture,
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["PRIVATE TEXT"] * 17})
    response = tmp_path / "response.json"
    translator = Mock()
    translator.translate_batch.side_effect = [
        [SimpleNamespace(hypotheses=[["ok", "</s>"]])] * 16,
        RuntimeError("PRIVATE TEXT and sensitive path"),
    ]
    monkeypatch.setattr(worker, "load_engine", lambda _: (engine[0], engine[1], translator))
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(response),
    ]) != 0
    assert json.loads(response.read_bytes()) == {"schema": 1, "error": "translation_failed"}
    captured = capsys.readouterr()
    assert "PRIVATE" not in captured.out + captured.err
    assert "Traceback" not in captured.err


def test_existing_response_is_preserved_without_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["hello"]})
    response = tmp_path / "response.json"
    response.write_bytes(b"owned by another process")
    loader = Mock()
    monkeypatch.setattr(worker, "load_engine", loader)
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(response),
    ]) != 0
    loader.assert_not_called()
    assert response.read_bytes() == b"owned by another process"
    assert json.loads(capsys.readouterr().err) == {"schema": 1, "error": "translation_failed"}


def test_bad_cli_arguments_are_sanitized(capsys: pytest.CaptureFixture) -> None:
    assert worker.main(["--request", "PRIVATE TEXT", "--unknown", "SECRET"]) != 0
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err) == {"schema": 1, "error": "translation_failed"}


def test_same_input_output_rejected(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["hello"]})
    original = request.read_bytes()
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(request),
    ]) != 0
    assert request.read_bytes() == original
    capsys.readouterr()


def test_symlink_request_rejected(tmp_path: Path) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": []})
    link = tmp_path / "link.json"
    try:
        os.symlink(request, link)
    except OSError:
        pytest.skip("Creating symlinks requires Windows privilege")
    with pytest.raises(worker.WorkerError):
        worker.read_request(link)


def test_direct_translation_rejects_too_many_items(engine: tuple) -> None:
    with pytest.raises(worker.WorkerError):
        worker.translate_texts(["hello"] * 10_001, *engine)
    assert engine[2].calls == []


def test_missing_or_special_request_file(tmp_path: Path) -> None:
    for path in (tmp_path / "missing.json", tmp_path):
        with pytest.raises(worker.WorkerError):
            worker.read_request(path)


def test_cli_empty_batch_does_not_load_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": []})
    response = tmp_path / "response.json"
    loader = Mock(side_effect=AssertionError("must not load"))
    monkeypatch.setattr(worker, "load_engine", loader)
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(response),
    ]) == 0
    loader.assert_not_called()
    assert json.loads(response.read_bytes()) == {"schema": 1, "translations": []}


def test_unwritable_response_reports_only_generic_json(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    response = tmp_path / "missing-parent" / "response.json"
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", "PRIVATE-MISSING-REQUEST",
        "--response", str(response),
    ]) != 0
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err) == {"schema": 1, "error": "translation_failed"}


def test_misnamed_model_directory_cannot_search_for_tokenizers(tmp_path: Path) -> None:
    model = model_files(tmp_path, flat=True)
    (model / "source.spm").unlink()
    (model / "target.spm").unlink()
    with pytest.raises(worker.WorkerError):
        worker.load_engine(model)


def test_missing_model_is_a_generic_contract_error(tmp_path: Path) -> None:
    with pytest.raises(worker.WorkerError, match="^invalid_model$"):
        worker.load_engine(tmp_path / "missing")


def test_post_commit_cleanup_failure_still_returns_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    engine: tuple, capsys: pytest.CaptureFixture,
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["hello"]})
    response = tmp_path / "response.json"
    monkeypatch.setattr(worker, "load_engine", lambda _: engine)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", Mock(side_effect=PermissionError("locked")))
        result = worker.main([
            "--model-dir", str(tmp_path), "--request", str(request),
            "--response", str(response),
        ])
    assert result == 0
    assert json.loads(response.read_bytes()) == {"schema": 1, "translations": ["hello"]}
    assert capsys.readouterr().err == ""
    for path in tmp_path.glob(".translation-worker-*.tmp"):
        path.unlink()


def test_dependency_diagnostics_are_suppressed_at_python_and_native_levels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["PRIVATE TEXT"]})
    response = tmp_path / "response.json"

    def noisy_loader(_: Path) -> None:
        print("PRIVATE TEXT from Python")
        print("PRIVATE TEXT from stderr", file=sys.stderr)
        os.write(1, b"PRIVATE TEXT from native stdout")
        os.write(2, b"PRIVATE TEXT from native stderr")
        raise RuntimeError("PRIVATE TEXT in exception")

    monkeypatch.setattr(worker, "load_engine", noisy_loader)
    assert worker.main([
        "--model-dir", str(tmp_path), "--request", str(request),
        "--response", str(response),
    ]) != 0
    captured = capfd.readouterr()
    assert captured.out == captured.err == ""
    assert json.loads(response.read_bytes()) == {"schema": 1, "error": "translation_failed"}


@pytest.mark.parametrize("text, expected", [
    ("Settings", False), ("Cài đặt", False), ("123", False),
    ("カメラ", False), ("한글", False), ("设置", True), ("設定", True),
    ("DJI 飞行器 123", True), ("㐀", True), ("\uf900", True),
    ("\U00020000", True), ("\U00031350", True), ("〇", True),
])
def test_han_detection(text: str, expected: bool) -> None:
    assert worker.contains_han(text) is expected


@pytest.mark.parametrize("tag_present", [False, True])
def test_chinese_prefix_comes_from_its_own_vocabulary(
    tmp_path: Path, tag_present: bool
) -> None:
    vocabulary = ["</s>", "<unk>", "设置"] + ([">>vie<<"] if tag_present else [])
    (tmp_path / "shared_vocabulary.json").write_text(json.dumps(vocabulary), encoding="utf-8")
    assert worker.chinese_prefix(tmp_path) == (">>vie<<" if tag_present else "")


@pytest.mark.parametrize("vocabulary", [[], {}, [1, "</s>"], ["word"]])
def test_invalid_chinese_vocabulary_is_rejected(tmp_path: Path, vocabulary: object) -> None:
    (tmp_path / "shared_vocabulary.json").write_text(json.dumps(vocabulary), encoding="utf-8")
    with pytest.raises(worker.WorkerError):
        worker.chinese_prefix(tmp_path)


def test_unilingual_token_limit_counts_only_one_eos(engine: tuple) -> None:
    accepted = " ".join(["中"] * 511)
    translator = Mock()
    translator.translate_batch.return_value = [SimpleNamespace(hypotheses=[["ok", "</s>"]])]
    assert worker.translate_texts(
        [accepted], engine[0], engine[1], translator, source_prefix=""
    ) == ["ok"]
    assert translator.translate_batch.call_args.args[0] == [["中"] * 511 + ["</s>"]]
    with pytest.raises(worker.WorkerError):
        worker.translate_texts([accepted + " 中"], *engine, source_prefix="")


def test_routing_preserves_mixed_order_duplicates_and_direct_translation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    english = (FakeTokenizer(), FakeTokenizer("English result"), FakeTranslator())
    chinese = (FakeTokenizer(), FakeTokenizer("Chinese result"), FakeTranslator())
    primary = tmp_path / "model"
    chinese_dir = tmp_path / "model-zh"
    chinese_dir.mkdir()
    (chinese_dir / "shared_vocabulary.json").write_text('["</s>", "中"]', encoding="utf-8")
    loader = Mock(side_effect=lambda path: chinese if path == chinese_dir else english)
    monkeypatch.setattr(worker, "load_engine", loader)
    assert worker.translate_routed(
        ["hello", "设置", "hello", "DJI 飞行器", "bye"], primary
    ) == ["English result", "Chinese result", "English result", "Chinese result", "English result"]
    assert [call.args[0] for call in loader.call_args_list] == [primary, chinese_dir]
    assert english[0].encoded == ["hello", "hello", "bye"]
    assert chinese[0].encoded == ["设置", "DJI 飞行器"]
    assert chinese[2].calls[0][0] == [["设置", "</s>"], ["DJI", "飞行器", "</s>"]]


def test_english_only_never_loads_or_inspects_chinese_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: tuple
) -> None:
    loader = Mock(return_value=engine)
    prefix_reader = Mock(side_effect=AssertionError("must not inspect"))
    monkeypatch.setattr(worker, "load_engine", loader)
    monkeypatch.setattr(worker, "chinese_prefix", prefix_reader)
    primary = tmp_path / "model"
    assert worker.translate_routed(["hello"], primary) == ["hello"]
    loader.assert_called_once_with(primary)
    prefix_reader.assert_not_called()


def test_chinese_only_skips_english_model_and_supports_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: tuple
) -> None:
    primary = tmp_path / "model"
    chinese_dir = tmp_path / "model-zh"
    chinese_dir.mkdir()
    (chinese_dir / "shared_vocabulary.json").write_text('["</s>", ">>vie<<"]', encoding="utf-8")
    loader = Mock(return_value=engine)
    monkeypatch.setattr(worker, "load_engine", loader)
    assert worker.translate_routed(["设置"], primary) == ["设置"]
    loader.assert_called_once_with(chinese_dir)
    assert engine[2].calls[0][0] == [[">>vie<<", "设置", "</s>"]]


def test_missing_chinese_model_fails_cli_without_english_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: tuple
) -> None:
    request = request_file(tmp_path, {"schema": 1, "texts": ["hello", "设置"]})
    response = tmp_path / "response.json"
    monkeypatch.setattr(worker, "load_engine", Mock(return_value=engine))
    assert worker.main([
        "--model-dir", str(tmp_path / "model"), "--request", str(request),
        "--response", str(response),
    ]) != 0
    assert engine[0].encoded == ["hello"]
    assert json.loads(response.read_bytes()) == {"schema": 1, "error": "translation_failed"}


def test_chinese_config_is_independently_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = model_files(tmp_path / "model-zh", flat=True)
    (model / "shared_vocabulary.json").write_text('["</s>", "中"]', encoding="utf-8")
    (model / "config.json").write_text('{"add_source_eos":true}', encoding="utf-8")
    ct2 = Mock()
    monkeypatch.setitem(sys.modules, "ctranslate2", ct2)
    with pytest.raises(worker.WorkerError):
        worker.translate_routed(["设置"], tmp_path / "model")
    ct2.Translator.assert_not_called()


def test_routed_request_limit_applies_across_both_languages(tmp_path: Path) -> None:
    with pytest.raises(worker.WorkerError):
        worker.translate_routed(["hi"] * 5001 + ["中"] * 5000, tmp_path / "model")
