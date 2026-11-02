"""Exercise installed artifacts with `python -I scripts/smoke_install.py`."""

from collections.abc import Sequence
from importlib.metadata import distribution
from importlib.resources import files

from context_optimizer import (
    ContextSegment,
    OptimizationPolicy,
    OptimizationRequest,
    optimize_context,
)


class Dependencies:
    """Synthetic smoke-test language, never a model-token approximation."""

    def render(self, segments: Sequence[ContextSegment], /) -> str:
        return "|".join(s.text for s in segments)

    def count(self, text: str, /) -> int:
        return len(text)

    def score(self, query: str, segments: Sequence[ContextSegment], /) -> Sequence[float]:
        return [1.0] * len(segments)


def main() -> None:
    package = distribution("context-optimizer")
    assert files("context_optimizer").joinpath("py.typed").is_file()
    assert all("extra ==" in requirement for requirement in package.requires or ())
    segments = (ContextSegment("a", "AA"), ContextSegment("p", "P", pinned=True))
    request = OptimizationRequest("q", segments, 1)
    deps = Dependencies()
    disabled = optimize_context(request, token_counter=deps, renderer=deps, scorer=deps)
    assert disabled.reason_code == "disabled" and disabled.context is None
    assert disabled.selected_segment_ids == ("a", "p")
    selected = optimize_context(
        request,
        token_counter=deps,
        renderer=deps,
        scorer=deps,
        policy=OptimizationPolicy(True, 0, 1, 0, ("greedy",)),
    )
    assert selected.applied and selected.context == "P"
    assert selected.selected_segment_ids == ("p",) and selected.optimized_tokens == 1
    print(f"Installed {package.metadata['Name']} {package.version}: smoke passed")


if __name__ == "__main__":
    main()
