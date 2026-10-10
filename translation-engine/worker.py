"""CPU offline OPUS-MT English/Chinese -> Vietnamese (Python 3.11, CT2 4.8.2).

CLI: --model-dir DIR --request FILE --response FILE
DIR contains model.bin, config.json, shared_vocabulary.json, source.spm and
target.spm. The original layout also works: DIR=model-int8, with tokenizers
in the fixed sibling model-source directory. No download or model discovery.
Inputs containing Han use the fixed sibling DIR.parent/model-zh directory,
with the same five files in a flat layout. Other inputs use DIR. Each model
is loaded only when its group is nonempty; output retains original indices.
The parent verifies hashes for all ten runtime files before invocation.

Request: {"schema": 1, "texts": ["English text"]}
Success: {"schema": 1, "translations": ["Văn bản tiếng Việt"]}
Failure: {"schema": 1, "error": "translation_failed"}, nonzero exit status.
The response MUST be a new path. A same-directory private temporary file is
flushed and atomically linked into place without overwriting existing files.
If publication fails, the same generic error is emitted to stderr.

Limits: 32 MiB request, 10,000 items, 64 KiB UTF-8 per string, 512 source
tokens INCLUDING the language prefix and EOS. Decoding reaching its 512-token
cap, missing EOS, empty output, or control characters fails the entire job.
Newlines are allowed; SentencePiece may normalize source whitespace.
Model: Helsinki-NLP/opus-mt-en-vi, Apache-2.0, revision
989c9fb9ec63987901022baf0182dcec3e149be6. No Moses preprocessing is required
by Marian's _tokenize path: SentencePiece provides its own normalization.
Chinese: Helsinki-NLP/opus-mt-zh-vi, Apache-2.0, revision
67ea2dbfbaf13a16772a40346d3d72b59e591443. Its source prefix is >>vie<< only
if present in its own shared vocabulary, otherwise empty. Translation is
direct zh -> vi, never via English. Missing Chinese assets fail the request.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout, suppress
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Protocol, cast
import unicodedata


MAX_REQUEST_BYTES = 32 * 1024 * 1024
MAX_TEXT_BYTES = 64 * 1024
MAX_ITEMS = 10_000
MAX_INPUT_TOKENS = 512
MAX_OUTPUT_TOKENS = 512
BATCH_SIZE = 16
PREFIX = ">>vie<<"
EOS = "</s>"
SPECIAL_TOKENS = frozenset((PREFIX, EOS, "<s>", "<pad>", "<unk>"))
ERROR_RESPONSE: dict[str, object] = {"schema": 1, "error": "translation_failed"}


class WorkerError(ValueError):
    """A failed worker contract, with no source text or path attached."""


class SourceTokenizer(Protocol):
    def encode(self, text: str, *, out_type: type[str]) -> list[str]: ...


class TargetTokenizer(Protocol):
    def decode(self, tokens: list[str]) -> str: ...


class TranslationResult(Protocol):
    @property
    def hypotheses(self) -> list[list[str]]: ...


class Translator(Protocol):
    def translate_batch(
        self, tokens: list[list[str]], **options: object
    ) -> list[TranslationResult]: ...


def _regular_file(path: Path, limit: int) -> None:
    """Reject special files, symlinks/reparse points and oversized inputs."""
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or getattr(info, "st_file_attributes", 0) & 0x400
        or info.st_size > limit
    ):
        raise WorkerError("invalid_file")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len({key for key, _ in pairs}) != len(pairs):
        raise WorkerError("invalid_json")
    return dict(pairs)


def _reject_constant(_: str) -> object:
    raise WorkerError("invalid_json")


def _read_json(path: Path, limit: int) -> object:
    try:
        _regular_file(path, limit)
        with path.open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise WorkerError("invalid_file")
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise WorkerError("invalid_file")
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (OSError, ValueError, UnicodeError, RecursionError):
        raise WorkerError("invalid_json") from None


def _validate_text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerError("invalid_text")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeError:
        raise WorkerError("invalid_text") from None
    if size > MAX_TEXT_BYTES or any(
        char != "\n" and unicodedata.category(char) in ("Cc", "Cf", "Cs")
        for char in value
    ):
        raise WorkerError("invalid_text")
    return value


def read_request(path: Path) -> list[str]:
    """Read bounded strict UTF-8 JSON and validate the complete request."""
    payload = _read_json(path, MAX_REQUEST_BYTES)
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "texts"}
        or type(payload["schema"]) is not int
        or payload["schema"] != 1
        or not isinstance(payload["texts"], list)
        or len(payload["texts"]) > MAX_ITEMS
    ):
        raise WorkerError("invalid_request")
    return [_validate_text(text) for text in payload["texts"]]


def _model_paths(model_dir: Path) -> tuple[Path, Path, Path]:
    model = model_dir.resolve(strict=True)
    for name, limit in (
        ("model.bin", 512 * 1024 * 1024),
        ("shared_vocabulary.json", 16 * 1024 * 1024),
        ("config.json", 64 * 1024),
    ):
        _regular_file(model / name, limit)
    config = _read_json(model / "config.json", 64 * 1024)
    if not isinstance(config, dict) or any(
        config.get(key) != expected or type(config.get(key)) is not type(expected)
        for key, expected in {
            "add_source_eos": False, "add_source_bos": False,
            "eos_token": EOS, "decoder_start_token": EOS,
        }.items()
    ):
        raise WorkerError("invalid_model")
    tokenizer_dir = model
    if not any((model / name).exists() for name in ("source.spm", "target.spm")):
        source_directories = {
            "model-int8": "model-source", "zh-model-int8": "zh-model-source",
        }
        if model.name not in source_directories:
            raise WorkerError("invalid_model")
        tokenizer_dir = model.parent / source_directories[model.name]
    source, target = tokenizer_dir / "source.spm", tokenizer_dir / "target.spm"
    for path in (source, target):
        _regular_file(path, 16 * 1024 * 1024)
    return model, source, target


def load_engine(model_dir: Path) -> tuple[SourceTokenizer, TargetTokenizer, Translator]:
    """Load fixed local assets, using at most four CPU threads and int8."""
    try:
        model, source, target = _model_paths(model_dir)
    except OSError:
        raise WorkerError("invalid_model") from None
    # CT2 4.8.2 lazily imports conversion modules; inference needs no training
    # frameworks, pkg_resources, Hugging Face access, or downloaded assets.
    import ctranslate2
    import sentencepiece
    ctranslate2.set_random_seed(0)
    source_tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(source))
    target_tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(target))
    translator = ctranslate2.Translator(
        str(model), device="cpu", compute_type="int8",
        inter_threads=1, intra_threads=min(4, max(1, os.cpu_count() or 1)),
    )
    return (
        cast(SourceTokenizer, source_tokenizer), cast(TargetTokenizer, target_tokenizer),
        cast(Translator, translator),
    )


def _encode(text: str, tokenizer: SourceTokenizer, source_prefix: str) -> list[str]:
    pieces = tokenizer.encode(_validate_text(text), out_type=str)
    # Marian removes the language tag BEFORE SentencePiece, and appends EOS.
    tokens = ([source_prefix] if source_prefix else []) + pieces + [EOS]
    if (
        not pieces or len(tokens) > MAX_INPUT_TOKENS
        or any(piece in SPECIAL_TOKENS for piece in pieces)
    ):
        raise WorkerError("invalid_input_tokens")
    return tokens


def _decode(result: TranslationResult, tokenizer: TargetTokenizer) -> str:
    if len(result.hypotheses) != 1:
        raise WorkerError("invalid_result")
    tokens = result.hypotheses[0]
    # Conservatively reject even an EOS at the length cap: never accept a
    # decoder forced to terminate at its limit as a complete translation.
    if (
        len(tokens) < 2 or len(tokens) >= MAX_OUTPUT_TOKENS or tokens[-1] != EOS
        or any(token in SPECIAL_TOKENS for token in tokens[:-1])
    ):
        raise WorkerError("incomplete_result")
    return _validate_text(tokenizer.decode(tokens[:-1]))


def translate_texts(
    texts: list[str], source: SourceTokenizer, target: TargetTokenizer,
    translator: Translator, *, source_prefix: str = PREFIX,
) -> list[str]:
    """Validate every input before deterministic inference in bounded chunks."""
    if len(texts) > MAX_ITEMS or source_prefix not in (PREFIX, ""):
        raise WorkerError("invalid_request")
    encoded = [_encode(text, source, source_prefix) for text in texts]
    translations: list[str] = []
    for offset in range(0, len(encoded), BATCH_SIZE):
        chunk = encoded[offset:offset + BATCH_SIZE]
        results = translator.translate_batch(
            chunk, beam_size=3, num_hypotheses=1, sampling_topk=1,
            max_input_length=0, max_decoding_length=MAX_OUTPUT_TOKENS,
            end_token=EOS, return_end_token=True,
        )
        if len(results) != len(chunk):
            raise WorkerError("invalid_result_count")
        translations.extend(_decode(result, target) for result in results)
    return translations


def contains_han(text: str) -> bool:
    """Route Han ideographs, including compatibility/supplementary blocks."""
    return any(
        character in "々〇〻" or any(
            lower <= ord(character) <= upper
            for lower, upper in (
                (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
                (0x20000, 0x2FA1F), (0x30000, 0x3347F),
            )
        )
        for character in text
    )


def chinese_prefix(model_dir: Path) -> str:
    """Choose the Chinese model's language tag from its pinned vocabulary."""
    vocabulary = _read_json(model_dir / "shared_vocabulary.json", 16 * 1024 * 1024)
    if (
        not isinstance(vocabulary, list) or not vocabulary
        or not all(isinstance(token, str) for token in vocabulary)
        or EOS not in vocabulary
    ):
        raise WorkerError("invalid_model_vocabulary")
    return PREFIX if PREFIX in vocabulary else ""


def translate_routed(texts: list[str], model_dir: Path) -> list[str]:
    """Translate each language directly to Vietnamese, retaining input order."""
    if len(texts) > MAX_ITEMS:
        raise WorkerError("invalid_request")
    routes = [contains_han(_validate_text(text)) for text in texts]
    indexed_translations: list[tuple[int, str]] = []
    for is_chinese in (False, True):
        indices = [index for index, route in enumerate(routes) if route == is_chinese]
        if not indices:
            continue
        directory = model_dir.parent / "model-zh" if is_chinese else model_dir
        prefix = chinese_prefix(directory) if is_chinese else PREFIX
        # Each temporary engine is released after this call, keeping native
        # inference sequential and within one four-thread translator at a time.
        translated = translate_texts(
            [texts[index] for index in indices], *load_engine(directory),
            source_prefix=prefix,
        )
        indexed_translations.extend(zip(indices, translated, strict=True))
    return [translation for _, translation in sorted(indexed_translations)]


def write_response(path: Path, payload: dict[str, object]) -> None:
    """Atomically publish a new file; remove only the worker's private temp."""
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".translation-worker-", suffix=".tmp",
            dir=path.parent, delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        # link is atomic and fails if the destination exists (including a
        # concurrent writer or dangling symlink); os.replace would clobber it.
        os.link(temporary, path)
    finally:
        if temporary is not None:
            # Publication is the commit point. A locked leftover private temp
            # must not turn a successfully published response into a failure.
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


@contextmanager
def _quiet_runtime() -> Iterator[None]:
    """Suppress dependency diagnostics, including native writes to fd 1/2."""
    saved: list[tuple[int, int]] = []
    with open(os.devnull, "w", encoding="utf-8") as sink:
        try:
            for descriptor in (1, 2):
                try:
                    original = os.dup(descriptor)
                except OSError:
                    # A windowed frozen application may have no standard fds.
                    continue
                saved.append((descriptor, original))
                os.dup2(sink.fileno(), descriptor)
            with redirect_stdout(sink), redirect_stderr(sink):
                yield
        finally:
            for descriptor, original in reversed(saved):
                try:
                    os.dup2(original, descriptor)
                finally:
                    os.close(original)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise WorkerError("invalid_arguments")


def main(argv: list[str] | None = None) -> int:
    """Return zero only after publishing every valid translation."""
    response: Path | None = None
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False, add_help=False)
        parser.add_argument("--model-dir", type=Path, required=True)
        parser.add_argument("--request", type=Path, required=True)
        parser.add_argument("--response", type=Path, required=True)
        args = parser.parse_args(argv)
        # Never overwrite a caller's input, previous result, or unrelated file.
        if os.path.lexists(args.response):
            raise WorkerError("response_exists")
        response = args.response
        texts = read_request(args.request)
        with _quiet_runtime():
            translations = translate_routed(texts, args.model_dir)
        write_response(response, {"schema": 1, "translations": translations})
        return 0
    except Exception:
        # The parent keeps counts; never serialize exception text or a traceback.
        if response is not None:
            try:
                write_response(response, ERROR_RESPONSE)
                return 1
            except Exception:
                pass
        sys.stderr.write(json.dumps(ERROR_RESPONSE, separators=(",", ":")) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
