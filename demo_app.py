"""DashCartCompare demo: a shopping list in, per-store subtotals out.

Run with:  .venv/bin/streamlit run demo_app.py

Thin slice, deliberately. It shows the Checkpoint 3.1 + S3 matcher working
end to end on the frozen five-store snapshot. It is NOT the Checkpoint 5
basket engine: there is no package-count arithmetic, so a line's cost is one
package's price. Every claim the UI makes is qualified on screen rather than
in a comment here, because a demo that overstates what it computed is worse
than no demo.
"""

import streamlit as st

import basket_demo as bd
from run_experiments import _load_catalog

EXAMPLES = {
    "Generic staples": "1 gallon whole milk\n12 large eggs\n16 oz butter\n1 lb strawberries",
    "Exact brands": "12 oz Barissimo French Vanilla ground coffee\n"
                    "16 oz Countryside Creamery Unsalted Butter\n"
                    "0.5 gal Oatly Original Oat Milk",
    "Hard / no complete basket": "2 lb chicken breast\n5 gal whole milk\n2 bags of chips",
}


@st.cache_resource(show_spinner="Loading catalog and fitting the matcher...")
def get_context():
    catalog = _load_catalog()
    return catalog, bd.build_context(catalog)


st.set_page_config(page_title="DashCartCompare", layout="wide")
st.title("DashCartCompare")
st.caption(
    "Which of five DoorDash-listed stores has the lowest **item subtotal** for a shopping list, "
    "using products that actually meet the request."
)

catalog, ctx = get_context()

with st.sidebar:
    st.header("Shopping list")
    example = st.selectbox("Start from an example", ["(write my own)"] + list(EXAMPLES))
    default = EXAMPLES.get(example, "")
    lines_text = st.text_area("One item per line", value=default, height=200,
                              placeholder="1 gallon whole milk\n12 large eggs")
    mode = st.radio(
        "Matching mode", ["flexible", "exact"],
        help="Flexible allows any brand as long as the requested attributes hold. "
             "Exact requires the same brand and variant, and asks for review when "
             "it cannot confirm them.",
    )
    min_score = st.slider(
        "Match score floor", 0.0, 1.0, bd.DEFAULT_MIN_SCORE, 0.05,
        help="Candidates scoring below this are not returned. Not a tuned "
             "threshold - see the caveat below the results.",
    )
    go = st.button("Compare stores", type="primary", use_container_width=True)

    st.divider()
    snapshots = catalog[["store_name", "snapshot_id"]].drop_duplicates()
    st.caption("**Snapshot data**, not live availability:")
    for r in snapshots.itertuples():
        st.caption(f"- {r.store_name}: `{r.snapshot_id}`")

if not go:
    st.info("Enter a shopping list and press **Compare stores**.")
    st.stop()

lines = [l for l in lines_text.splitlines() if l.strip()]
if not lines:
    st.warning("The shopping list is empty.")
    st.stop()

with st.spinner(f"Matching {len(lines)} item(s) across 5 stores..."):
    results, totals = bd.compare_basket(lines, ctx, mode, min_score)

ranked = bd.rank_complete_stores(totals)

# --- headline ---------------------------------------------------------------

if not ranked:
    st.error(
        "**No store can complete this basket.** Rather than name a winner from a partial "
        "basket, the comparison stops here — see the per-store detail below for what is missing."
    )
else:
    cheapest_cents = ranked[0][1]["subtotal_cents"]
    tied = [t for _, t in ranked if t["subtotal_cents"] == cheapest_cents]
    if len(tied) > 1:
        st.success(f"**Tied at ${cheapest_cents / 100:.2f}**: "
                   + ", ".join(t["store_name"] for t in tied))
    else:
        st.success(f"**{ranked[0][1]['store_name']}** has the lowest item subtotal: "
                   f"**${cheapest_cents / 100:.2f}**")

    cols = st.columns(len(ranked))
    for col, (_, t) in zip(cols, ranked):
        delta = t["subtotal_cents"] - cheapest_cents
        col.metric(t["store_name"], f"${t['subtotal_cents'] / 100:.2f}",
                   None if delta == 0 else f"+${delta / 100:.2f}",
                   delta_color="inverse")

st.caption(
    "Item subtotal only — excludes delivery fees, taxes, tips, memberships and checkout "
    "promotions. One package per line: package-count arithmetic is Checkpoint 5 and is not "
    "implemented here, so a line whose requested quantity needs more than one package is "
    "under-counted."
)

# --- per-line detail --------------------------------------------------------

st.subheader("Item matches")
for r in results:
    if r.response == "answerable":
        label, icon = f"{r.text}", "✅"
    elif r.response == "needs_clarification":
        label, icon = f"{r.text} — needs review", "❓"
    else:
        label, icon = f"{r.text} — no acceptable match", "🚫"

    with st.expander(f"{icon}  {label}", expanded=(r.response != "answerable")):
        s = r.structured
        st.caption(
            f"Interpreted as: **{s.get('product_type') or '?'}** · "
            f"quantity **{s.get('canonical_quantity') or s.get('quantity') or '?'} "
            f"{s.get('canonical_unit') or s.get('unit') or ''}** · "
            f"dimension **{s.get('dimension') or 'unknown'}**"
        )
        if r.note:
            st.warning(r.note)
        if r.matches:
            rows = [
                {
                    "Store": m.store_name,
                    "Product": m.title,
                    "Price": "—" if m.price_cents is None else f"${m.price_cents / 100:.2f}",
                    "Score": round(m.score, 3),
                }
                for m in sorted(r.matches.values(),
                                key=lambda m: (m.price_cents is None, m.price_cents or 0))
            ]
            st.dataframe(rows, hide_index=True, use_container_width=True)
        elif r.response == "needs_clarification":
            st.info("The request is ambiguous or its identity could not be confirmed. "
                    "In the full product this is where you would pick a reference product.")

# --- incomplete baskets -----------------------------------------------------

incomplete = [(sid, t) for sid, t in totals.items() if not (t["complete"] and t["fully_priced"])]
if incomplete:
    st.subheader("Incomplete baskets")
    st.caption("Shown separately and never ranked against a complete basket.")
    for _, t in sorted(incomplete, key=lambda kv: kv[1]["store_name"]):
        reasons = []
        if t["missing"]:
            reasons.append(f"{len(t['missing'])} item(s) not found in this snapshot")
        if not t["fully_priced"]:
            reasons.append("at least one match has no usable price")
        with st.expander(f"{t['store_name']} — " + "; ".join(reasons) or t["store_name"]):
            for miss in t["missing"]:
                st.write(f"- missing: {miss}")

st.divider()
with st.expander("What this demo gets wrong (read before trusting a number)"):
    st.markdown(
        """
**The score floor is blunt, and right and wrong matches do not separate cleanly.**
Measured on these examples:

| Request | Top score | Verdict |
|---|---|---|
| `1 gallon whole milk` | 0.401 | right |
| `5 gal whole milk` | 0.306 | wrong — *Whole Carrots* |
| `2 lb chicken breast` | 0.574 | wrong — no 2 lb fixed package exists in any snapshot |

A wrong match outscores a right one, so no single floor separates them. The default
0.35 removes the most obvious junk and nothing more; it is **not** a tuned threshold.
Checkpoint S6 derives a real threshold and a review band on the dev split with a
declared cost function.

**Why this matters more in a basket than in a metrics table:** wrong matches are
systematically *cheap*, and a cheapest-basket ranking therefore prefers them. One
false match can hand a store a fake win. Try `2 lb chicken breast` above and watch
a $2.19 deli item win on a request no store can actually fill.

**No package-count arithmetic.** One package per line, so a line needing two
packages is under-counted. That is Checkpoint 5.

**Snapshot data.** Absence means *not found in our snapshot*, not *unavailable*.
        """
    )
st.caption(
    "Matcher: TF-IDF retrieval, then dimension, package-size and brand/variant identity filters "
    "(Checkpoint 3.1 + Checkpoint 4 S3). Embedding and hybrid matchers are not wired in yet. "
    "Absence from a snapshot means *not found in our snapshot*, not *unavailable at the store*."
)
