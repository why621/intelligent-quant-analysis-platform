from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = REPO_ROOT / "packages" / "contracts"
OPENAPI_PATH = CONTRACT_ROOT / "openapi.yaml"


def load_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as stream:
        document = yaml.safe_load(stream)
    assert isinstance(document, dict), f"{path} must contain a YAML object"
    return document


def iter_refs(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref":
                yield child
            yield from iter_refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_refs(child)


def resolve_pointer(document: object, pointer: str) -> object:
    current = document
    for raw_part in pointer.removeprefix("#/").split("/"):
        if not raw_part:
            continue
        part = raw_part.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict) and part in current, f"missing pointer part: {part}"
        current = current[part]
    return current


def test_openapi_declares_all_application_interfaces() -> None:
    spec = load_yaml(OPENAPI_PATH)
    assert spec["openapi"] == "3.1.0"
    assert set(spec["paths"]) == {
        "/health",
        "/data/status",
        "/assets",
        "/assets/{symbol}/history",
        "/market/overview",
        "/analytics/correlation",
        "/strategies",
        "/strategies/ranking",
        "/backtests",
        "/backtests/{jobId}",
        "/allocation/suggestion",
    }


def test_all_contract_references_resolve() -> None:
    documents = {path.resolve(): load_yaml(path) for path in CONTRACT_ROOT.rglob("*.yaml")}
    for source_path, document in documents.items():
        for reference in iter_refs(document):
            assert isinstance(reference, str)
            file_part, _, pointer = reference.partition("#")
            target_path = (
                source_path if not file_part else (source_path.parent / file_part).resolve()
            )
            assert target_path in documents, f"{source_path}: missing referenced file {target_path}"
            resolve_pointer(documents[target_path], f"#/{pointer.lstrip('/')}")
