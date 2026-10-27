"""Property-based tests for Archives of Nethys URL detection."""

from pathlib import Path
import sys

from hypothesis import given, strategies as st

# Ensure the src directory is importable when running pytest from the repo root
ROOT = Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.aon_detector import is_aon_url

# Strategie per domini AoN e non-AoN
aon_domains = st.sampled_from(
    [
        "aonprd.com",
        "2e.aonprd.com",
        "legacy.aonprd.com",
    ]
)

non_aon_domains = st.sampled_from(
    [
        "example.com",
        "d20pfsrd.com",
        "prd.moe",
    ]
)

# Strategie per percorsi e query/frammenti
paths = st.text(min_size=0, max_size=20).map(lambda s: "/" + s if s else "")
queries = st.text(min_size=0, max_size=20).map(lambda s: "?" + s if s else "")
fragments = st.text(min_size=0, max_size=20).map(lambda s: "#" + s if s else "")


@given(domain=aon_domains, path=paths, query=queries, fragment=fragments)
def test_is_aon_url_returns_true_for_aon_variants(domain, path, query, fragment):
    url = f"https://{domain}{path}{query}{fragment}"
    assert is_aon_url(url)


@given(domain=non_aon_domains, path=paths, query=queries, fragment=fragments)
def test_is_aon_url_returns_false_for_non_aon(domain, path, query, fragment):
    url = f"https://{domain}{path}{query}{fragment}"
    assert not is_aon_url(url)
