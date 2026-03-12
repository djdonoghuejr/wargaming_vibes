from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SamplingProfile:
    profile_id: str
    name: str
    scenario_variation_scale: float
    force_variation_scale: float
    coa_variation_scale: float


BUILTIN_PROFILES = {
    "baseline_deterministic": SamplingProfile(
        profile_id="baseline_deterministic",
        name="Baseline Deterministic",
        scenario_variation_scale=0.0,
        force_variation_scale=0.0,
        coa_variation_scale=0.0,
    ),
    "hybrid_stochastic_v1": SamplingProfile(
        profile_id="hybrid_stochastic_v1",
        name="Hybrid Stochastic v1",
        scenario_variation_scale=1.0,
        force_variation_scale=1.0,
        coa_variation_scale=1.0,
    ),
}


def get_sampling_profile(profile_id: str) -> SamplingProfile:
    if profile_id not in BUILTIN_PROFILES:
        raise KeyError(
            f"Unknown sampling profile '{profile_id}'. Available profiles: {sorted(BUILTIN_PROFILES)}."
        )
    return BUILTIN_PROFILES[profile_id]
