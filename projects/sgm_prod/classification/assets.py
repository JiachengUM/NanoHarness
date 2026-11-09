from __future__ import annotations

import csv
import runpy
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from projects.sgm_prod.classification.models import (
    CapabilityCard,
    LLMPromptAsset,
    LexiconEntry,
    ParserRules,
    RiskRule,
)
from projects.sgm_prod.classification.normalize import normalize_query

_DEFAULT_PROJECT = "default"
_PROJECT_ALIASES = {"baic": "SGM"}
_ASSET_ROOT = Path(__file__).with_name("assets")
_ASSET_DIR = _ASSET_ROOT
_RULE_VERSION = "router_rules_navigation_llm_fallback"


class UnknownRouterProjectError(ValueError):
    pass


class RouterAssets(BaseModel):
    project: str = _DEFAULT_PROJECT
    rule_version: str
    simple_queries: frozenset[str]
    complex_queries: frozenset[str]
    capabilities: dict[str, CapabilityCard]
    lexicon: list[LexiconEntry]
    risks: list[RiskRule]
    parser_rules: ParserRules
    llm_prompts: dict[str, LLMPromptAsset]


class RouterAssetRegistry(BaseModel):
    profiles: dict[str, RouterAssets]

    def get(self, project: str = _DEFAULT_PROJECT) -> RouterAssets:
        normalized_project = (project or _DEFAULT_PROJECT).strip() or _DEFAULT_PROJECT
        asset_project = _PROJECT_ALIASES.get(
            normalized_project.lower(), normalized_project
        )
        try:
            assets = self.profiles[asset_project]
        except KeyError as exc:
            raise UnknownRouterProjectError(
                f"unknown router project: {normalized_project}"
            ) from exc
        if asset_project != normalized_project:
            return assets.model_copy(update={"project": normalized_project})
        return assets


def _index_capabilities(cards: list[CapabilityCard]) -> dict[str, CapabilityCard]:
    capabilities: dict[str, CapabilityCard] = {}
    for card in cards:
        if card.id in capabilities:
            raise ValueError(f"duplicate capability_id: {card.id}")
        capabilities[card.id] = card
    return capabilities


def _validate_lexicon(entries: list[LexiconEntry]) -> None:
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.slot, entry.canonical)
        if key in seen:
            raise ValueError(f"duplicate lexicon entry: {entry.slot}/{entry.canonical}")
        seen.add(key)


def _validate_risks(risks: list[RiskRule]) -> None:
    seen: set[str] = set()
    for rule in risks:
        if rule.risk_id in seen:
            raise ValueError(f"duplicate risk_id: {rule.risk_id}")
        seen.add(rule.risk_id)


def _read_csv_queries(
    path: Path,
    *,
    expected_label: str,
) -> frozenset[str]:
    queries: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_number, row in enumerate(reader, start=2):
            label = (row.get("label") or "").strip()
            if label != expected_label:
                raise ValueError(
                    f"{path}: row {line_number} expected label {expected_label}, got {label!r}"
                )

            for column in ("source", "domain"):
                if not (row.get(column) or "").strip():
                    raise ValueError(f"{path}: row {line_number} missing {column}")

            query = row.get("query") or ""
            normalized_query = normalize_query(query)
            if not normalized_query:
                raise ValueError(f"{path}: row {line_number} missing query")
            queries.add(normalized_query)
    return frozenset(queries)


def _case_csv_path(asset_dir: Path, label: str) -> Path:
    return asset_dir / "data" / f"{label}.csv"


def _rule_yaml_path(asset_dir: Path, filename: str) -> Path:
    return asset_dir / "rules" / filename


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def _read_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _read_yaml(path)


def _read_capability_files(path: Path) -> list[CapabilityCard]:
    if not path.is_dir():
        raise ValueError(f"{path} must be a directory containing capability YAML files")

    cards: list[CapabilityCard] = []
    for file_path in sorted(path.glob("*.yaml")):
        if file_path.name.startswith("_"):
            continue
        data = _read_yaml(file_path)
        executor = str(data.get("executor", "")).strip()
        if not executor:
            raise ValueError(f"{file_path}: missing executor")
        raw_cards = data.get("capabilities", [])
        if not isinstance(raw_cards, list):
            raise ValueError(f"{file_path}: capabilities must be a list")
        for item in raw_cards:
            if not isinstance(item, dict):
                raise ValueError(f"{file_path}: capability item must be a mapping")
            cards.append(CapabilityCard(**{**item, "executor": executor}))
    return cards


def _read_prompt_file(prompt_id: str, prompt_path: Path) -> LLMPromptAsset:
    if not prompt_path.exists():
        raise ValueError(f"{prompt_path}: missing LLM classification prompt asset")

    namespace = runpy.run_path(str(prompt_path))
    prompt = namespace.get("SYSTEM_PROMPT")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"{prompt_path}: SYSTEM_PROMPT must be a non-empty string")
    return LLMPromptAsset(id=prompt_id, system_prompt=prompt)


def _read_llm_prompt_files(path: Path) -> dict[str, LLMPromptAsset]:
    if not path.is_dir():
        raise ValueError(f"{path} must be a directory containing LLM prompt assets")

    prompts: dict[str, LLMPromptAsset] = {}
    default_prompt_path = path / "prompt.py"
    prompts[_DEFAULT_PROJECT] = _read_prompt_file(_DEFAULT_PROJECT, default_prompt_path)
    for file_path in sorted(path.glob("*.py")):
        if file_path.name.startswith("_") or file_path.name == "prompt.py":
            continue
        prompt_id = file_path.stem
        if prompt_id in prompts:
            raise ValueError(f"duplicate llm prompt id: {prompt_id}")
        prompts[prompt_id] = _read_prompt_file(prompt_id, file_path)
    return prompts


def load_router_assets_from_dir(project: str, asset_dir: Path) -> RouterAssets:
    lexicon_data = _read_yaml(_rule_yaml_path(asset_dir, "lexicon.yaml"))
    risk_data = _read_yaml(_rule_yaml_path(asset_dir, "global_risks.yaml"))
    parser_rules_data = _read_optional_yaml(_rule_yaml_path(asset_dir, "parser_rules.yaml"))

    cards = _read_capability_files(asset_dir / "capabilities")
    capabilities = _index_capabilities(cards)
    lexicon = [LexiconEntry(**item) for item in lexicon_data.get("entries", [])]
    _validate_lexicon(lexicon)
    risks = [RiskRule(**item) for item in risk_data.get("risks", [])]
    _validate_risks(risks)
    parser_rules = ParserRules(**parser_rules_data)

    simple_queries = _read_csv_queries(
        _case_csv_path(asset_dir, "simple"),
        expected_label="simple",
    )
    complex_queries = _read_csv_queries(
        _case_csv_path(asset_dir, "complex"),
        expected_label="complex",
    )
    conflicts = simple_queries & complex_queries
    if conflicts:
        examples = ", ".join(sorted(conflicts)[:5])
        raise ValueError(f"simple/complex exact query conflicts: {examples}")

    return RouterAssets(
        project=project,
        rule_version=_RULE_VERSION,
        simple_queries=simple_queries,
        complex_queries=complex_queries,
        capabilities=capabilities,
        lexicon=lexicon,
        risks=risks,
        parser_rules=parser_rules,
        llm_prompts=_read_llm_prompt_files(asset_dir / "llm_classfication"),
    )


def _profile_dirs(asset_root: Path) -> dict[str, Path]:
    if (asset_root / "capabilities").is_dir():
        return {_DEFAULT_PROJECT: asset_root}

    profiles = {
        path.name: path
        for path in sorted(asset_root.iterdir())
        if path.is_dir() and (path / "capabilities").is_dir()
    }
    if _DEFAULT_PROJECT not in profiles:
        raise ValueError(f"{asset_root}: missing default router asset profile")
    return profiles


@cache
def load_router_profiles(asset_root: Path | str | None = None) -> RouterAssetRegistry:
    root = _ASSET_ROOT if asset_root is None else Path(asset_root)
    profiles = {
        project: load_router_assets_from_dir(project, path)
        for project, path in _profile_dirs(root).items()
    }
    return RouterAssetRegistry(profiles=profiles)


def get_router_assets(
    project: str = _DEFAULT_PROJECT,
    *,
    asset_root: Path | str | None = None,
) -> RouterAssets:
    if (
        asset_root is None
        and (project or _DEFAULT_PROJECT).strip() == _DEFAULT_PROJECT
        and (_ASSET_DIR / "capabilities").is_dir()
    ):
        return load_router_assets()
    return load_router_profiles(asset_root).get(project)


@cache
def load_llm_classification_prompt(project: str = _DEFAULT_PROJECT) -> str:
    if project == _DEFAULT_PROJECT and (_ASSET_DIR / "capabilities").is_dir():
        return load_router_assets().llm_prompts[_DEFAULT_PROJECT].system_prompt
    return get_router_assets(project).llm_prompts[_DEFAULT_PROJECT].system_prompt


@cache
def load_router_assets() -> RouterAssets:
    if (_ASSET_DIR / "capabilities").is_dir():
        return load_router_assets_from_dir(_DEFAULT_PROJECT, _ASSET_DIR)
    return get_router_assets(_DEFAULT_PROJECT)
