from __future__ import annotations

from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    return project_root() / "data"


def default_runs_dir() -> Path:
    return data_dir() / "runs"


def default_generated_dir() -> Path:
    return data_dir() / "generated"


def default_datasets_dir() -> Path:
    return data_dir() / "datasets"


def default_analysis_dir() -> Path:
    return data_dir() / "analysis"


def sample_scenario_path() -> Path:
    return data_dir() / "scenarios" / "scn_corridor_001.json"


def sample_blue_force_path() -> Path:
    return data_dir() / "force_packages" / "fp_blue_001.json"


def sample_red_force_path() -> Path:
    return data_dir() / "force_packages" / "fp_red_001.json"


def sample_blue_coa_a_path() -> Path:
    return data_dir() / "coas" / "blue_delay_center.json"


def sample_blue_coa_b_path() -> Path:
    return data_dir() / "coas" / "blue_mobile_flank.json"


def sample_red_coa_path() -> Path:
    return data_dir() / "coas" / "red_direct_thrust.json"
