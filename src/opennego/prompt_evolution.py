"""BYOK prompt evolution: evolve natural-language strategy prompts.

The project's thesis is that the strategy *prompt* is the lever. This module
makes that real: a population of prompts is mutated by an LLM and selected by
tournament fitness (see ``docs/design/prompt_evolution.md``).

A prompt's fitness only moves when matches run through a real model, so the
machinery is split behind two ports — a ``PromptMutatorPort`` and an agent
factory — each with a deterministic fake (CI, no-key) and a BYOK LLM
implementation. The loop is identical either way; only the injected pieces
differ, so CI proves the loop while the user's key proves the quality.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from opennego.agents.profiles import (
    BuyerPolicy,
    ProfileBackedBuyer,
    ProfileBackedSeller,
    SellerPolicy,
)
from opennego.learning import StrategyProfile
from opennego.ports import LLMPort, LLMRequest
from opennego.schema import Role

# CI fake agents read this tag from a prompt so a prompt's fitness is observable
# without a real model; real BYOK prompts simply omit it.
_AGGR_PATTERN = re.compile(r"\[\[aggr=([0-9]*\.?[0-9]+)\]\]")
DEFAULT_AGGRESSIVENESS = 0.5


class PromptEvolutionError(ValueError):
    """Raised when a prompt genome or evolution request is invalid."""


@dataclass(frozen=True)
class PromptGenome:
    genome_id: str
    prompt: str
    parent_ids: tuple[str, ...] = ()


# A prompt -> agent. The BYOK factory builds an LLM agent; the fake factory
# builds a deterministic agent whose behavior depends on the prompt.
AgentFactory = Callable[[PromptGenome, Role], Any]


class PromptMutatorPort(Protocol):
    """Produces strategy-prompt variants. Fake (CI) or LLM (BYOK)."""

    def mutate(self, prompt: str, *, feedback: str = "") -> str: ...

    def crossover(self, prompt_a: str, prompt_b: str) -> str: ...


# --- aggressiveness tag (CI fake fitness signal) ----------------------------


def parse_aggressiveness(prompt: str) -> float:
    match = _AGGR_PATTERN.search(prompt)
    if not match:
        return DEFAULT_AGGRESSIVENESS
    try:
        return max(0.0, min(1.0, float(match.group(1))))
    except ValueError:
        return DEFAULT_AGGRESSIVENESS


def _with_aggressiveness(prompt: str, value: float) -> str:
    value = max(0.0, min(1.0, value))
    tag = f"[[aggr={value:.3f}]]"
    if _AGGR_PATTERN.search(prompt):
        return _AGGR_PATTERN.sub(tag, prompt)
    return f"{prompt} {tag}".strip()


# --- mutators ---------------------------------------------------------------


@dataclass
class FakePromptMutator:
    """Deterministic, no-key mutator over the aggressiveness tag.

    Pure string transforms keyed by a stable hash, so an evolution run replays
    identically. Stands in for an LLM in CI and demos.
    """

    step: float = 0.15

    def mutate(self, prompt: str, *, feedback: str = "") -> str:
        current = parse_aggressiveness(prompt)
        digest = hashlib.sha256(f"{prompt}|{feedback}".encode("utf-8")).digest()
        # Deterministic signed step in [-step, step].
        unit = int.from_bytes(digest[:8], "big") / float(1 << 64)
        return _with_aggressiveness(prompt, current + (unit * 2.0 - 1.0) * self.step)

    def crossover(self, prompt_a: str, prompt_b: str) -> str:
        midpoint = (parse_aggressiveness(prompt_a) + parse_aggressiveness(prompt_b)) / 2
        return _with_aggressiveness(prompt_a, midpoint)


@dataclass
class LLMPromptMutator:
    """BYOK mutator: meta-prompts the user's model to improve/combine prompts."""

    llm: LLMPort
    model: str
    temperature: float = 0.7
    max_tokens: int | None = 512

    def mutate(self, prompt: str, *, feedback: str = "") -> str:
        instruction = (
            "You improve negotiation strategy prompts. Given the current "
            "strategy prompt and feedback from its matches, rewrite it to be "
            "more effective while keeping it concise. Return only the improved "
            "strategy prompt, no preamble."
        )
        user = f"Current strategy prompt:\n{prompt}\n\nMatch feedback:\n{feedback or 'none'}"
        return self._complete(instruction, user) or prompt

    def crossover(self, prompt_a: str, prompt_b: str) -> str:
        instruction = (
            "You combine two negotiation strategy prompts into one that keeps "
            "the strongest tactics of each. Return only the combined strategy "
            "prompt, no preamble."
        )
        user = f"Prompt A:\n{prompt_a}\n\nPrompt B:\n{prompt_b}"
        return self._complete(instruction, user) or prompt_a

    def _complete(self, instruction: str, user: str) -> str:
        response = self.llm.complete(
            LLMRequest(
                model=self.model,
                messages=(
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": user},
                ),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        )
        return (response.content or "").strip()


# --- agent factories --------------------------------------------------------


def _synthetic_profile(prompt: str, role: Role, genome_id: str) -> StrategyProfile:
    return StrategyProfile(
        id=genome_id,
        name=f"prompt_{role.value}_{genome_id}",
        role=role,
        archetype="prompt_evolved",
        difficulty="evolved",
        summary="Evolved strategy prompt.",
        base_prompt="Follow OpenNegotiation protocol exactly.",
        strategy_prompt=prompt,
    )


def fake_agent_factory(genome: PromptGenome, role: Role):
    """Deterministic prompt-sensitive agent for CI/demos (no model).

    Maps the prompt's aggressiveness tag onto a real policy so fitness responds
    to the prompt — reusing the M9 ``policy_override`` hook.
    """

    aggr = parse_aggressiveness(genome.prompt)
    profile = _synthetic_profile(genome.prompt, role, genome.genome_id)
    if role == Role.BUYER:
        # More aggressive = lower opening and a tighter willingness.
        policy = BuyerPolicy(
            opening_discount=0.85 - 0.35 * aggr,
            counter_fraction=0.9 - 0.2 * aggr,
            willingness_multiplier=1.0 - 0.15 * aggr,
        )
        return ProfileBackedBuyer(profile=profile, policy_override=policy)
    policy = SellerPolicy(
        opening_markup=0.9 + 0.1 * aggr,
        concession_fraction=0.6 - 0.35 * aggr,
    )
    return ProfileBackedSeller(profile=profile, policy_override=policy)


def make_llm_agent_factory(llm: LLMPort, model: str) -> AgentFactory:
    """BYOK factory: an LLM agent whose system prompt embeds the genome prompt."""

    from opennego.agents import make_profile_llm_agent

    def factory(genome: PromptGenome, role: Role):
        return make_profile_llm_agent(
            profile=_synthetic_profile(genome.prompt, role, genome.genome_id),
            llm=llm,
            model=model,
        )

    return factory
