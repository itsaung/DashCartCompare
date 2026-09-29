"""Price watch report: swings found across snapshots of the tracked stores.

Run with:  .venv/bin/streamlit run price_watch_app.py

Reads runs/ and price_watch/ only; never crawls. PRICE_WATCH_ROOT points it
at another directory holding the same two folders (used for fixture checks).
"""
import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import price_watch as pw
import price_watch_config as cfg

ROOT = Path(os.environ.get("PRICE_WATCH_ROOT", cfg.HERE))
RUNS = ROOT / "runs"
WATCH = ROOT / "price_watch"

st.set_page_config(page_title="Price Watch", layout="wide")


@st.cache_data(ttl=60)
def load():
    swings, snaps = pw.all_swings(RUNS)
    histories = {}
    for name, slug, store_id in cfg.TRACKED_STORES:
        histories[name] = pw.build_history(pw.load_snapshots(pw.store_dir(slug, store_id, RUNS)))
    return swings, snaps, histories


def read_jsonl(path: Path) -> list:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


swings, snaps, histories = load()
crawl_log = read_jsonl(WATCH / "crawl_log.jsonl")
alerts = read_jsonl(WATCH / "alerts.jsonl")

st.title("Price Watch")
st.caption(
    # "$" is escaped: Streamlit markdown reads a $...$ pair as LaTeX.
    f"Items whose highest observed price is at least {pw.fmt_usd(cfg.WATCH_MIN_PRICE_CENTS)}. "
    f"A swing is a change between consecutive observations of at least "
    f"{cfg.SWING_REL_THRESHOLD:.0%} and {pw.fmt_usd(cfg.SWING_ABS_THRESHOLD_CENTS)}. "
    "Thresholds are provisional until the noise floor is measured.".replace("$", "\\$")
)

cols = st.columns(len(cfg.TRACKED_STORES) + 1)
for col, (name, _, _) in zip(cols, cfg.TRACKED_STORES):
    s = snaps.get(name, [])
    col.metric(name, f"{len(s)} snapshots")
    col.caption(f"Last: {s[-1][1] if s else 'never'}")
dips = [s for s in swings if s["direction"] == "dip"]
cols[-1].metric("Swings found", len(swings))
cols[-1].caption(f"{len(dips)} dips, {len(swings) - len(dips)} rises")

if all(len(s) < 2 for s in snaps.values()):
    st.info(
        "Each store has fewer than two snapshots, so no price can be compared yet. "
        "Swings appear after the next crawl: `.venv/bin/python price_watch_snapshot.py`."
    )

tab_swings, tab_item, tab_alerts, tab_crawls = st.tabs(["Swings", "Item history", "Alerts sent", "Crawl health"])

with tab_swings:
    f1, f2, f3, f4 = st.columns(4)
    stores = f1.multiselect("Store", [s[0] for s in cfg.TRACKED_STORES], default=[s[0] for s in cfg.TRACKED_STORES])
    direction = f2.selectbox("Direction", ["Dips", "Rises", "Both"])
    labels = f3.multiselect(
        "Explanation",
        ["unexplained", "sale_start", "sale_end"],
        default=["unexplained", "sale_start", "sale_end"],
        help="sale_start / sale_end: the listing shows (or stops showing) a crossed-out original price.",
    )
    min_pct = f4.slider("Minimum change", 20, 90, 20, step=5, format="%d%%")
    only_reverted = st.checkbox("Only swings that later reverted (likeliest pricing errors)")

    shown = [
        s
        for s in swings
        if s["store"] in stores
        and s["label"] in labels
        and abs(s["delta_rel"]) * 100 >= min_pct
        and (direction == "Both" or s["direction"] == direction[:-1].lower())
        and (not only_reverted or s["reverted_at"])
    ]
    if not swings:
        st.write("No swings in the snapshots so far.")
    elif not shown:
        st.write("No swings match these filters.")
    else:
        df = pd.DataFrame(
            {
                "": [s["image_url"] for s in shown],
                "Item": [s["item_name"] for s in shown],
                "Store": [s["store"] for s in shown],
                "Category": [f"{s['category']} / {s['subcategory']}".rstrip(" /") for s in shown],
                "Before": [s["before_cents"] / 100 for s in shown],
                "After": [s["after_cents"] / 100 for s in shown],
                "Change": [s["delta_rel"] * 100 for s in shown],
                "Change $": [s["delta_cents"] / 100 for s in shown],
                "Explanation": [s["label"] for s in shown],
                "Seen at": [s["after_at"] for s in shown],
                "Reverted at": [s["reverted_at"] or "" for s in shown],
            }
        )
        st.dataframe(
            df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "": st.column_config.ImageColumn(width="small"),
                "Before": st.column_config.NumberColumn(format="$%.2f"),
                "After": st.column_config.NumberColumn(format="$%.2f"),
                "Change": st.column_config.NumberColumn(format="%+.0f%%"),
                "Change $": st.column_config.NumberColumn(format="$%+.2f"),
            },
        )
        st.caption(f"{len(shown)} of {len(swings)} swings shown.")

with tab_item:
    options = {}
    for name, hist in histories.items():
        for item_id, obs in hist.items():
            if max(o["price_cents"] for o in obs) >= cfg.WATCH_MIN_PRICE_CENTS:
                options[f"{obs[-1]['item_name']} — {name}"] = (name, item_id)
    swung = {(s["store"], s["item_id"]) for s in swings}
    only_swung = st.checkbox("Only items with a swing", value=bool(swung))
    keys = sorted(k for k, v in options.items() if not only_swung or v in swung)
    if not keys:
        st.write("No items to show.")
    else:
        pick = st.selectbox("Item", keys)
        name, item_id = options[pick]
        obs = histories[name][item_id]
        hist_df = pd.DataFrame(
            {
                "Observed (UTC)": pd.to_datetime([o["observed_at"] for o in obs]).tz_localize(None),
                "Price": [o["price_cents"] / 100 for o in obs],
                "Original price": [o["original_cents"] / 100 if o["original_cents"] else None for o in obs],
            }
        ).melt("Observed (UTC)", var_name="Series", value_name="USD").dropna()
        # Step, not a slope: a price is only known at observations, and between
        # two it did not glide -- it changed once, somewhere in the gap.
        chart = (
            alt.Chart(hist_df)
            .mark_line(interpolate="step-after", point=True)
            .encode(
                x=alt.X("Observed (UTC):T"),
                y=alt.Y("USD:Q", scale=alt.Scale(zero=True)),
                color="Series:N",
                tooltip=["Observed (UTC):T", "Series:N", alt.Tooltip("USD:Q", format="$,.2f")],
            )
        )
        st.altair_chart(chart, use_container_width=True)
        st.caption(f"{len(obs)} observations. Gaps are snapshots where this item was not seen, not price changes.")

with tab_alerts:
    if not alerts:
        st.write("No alerts sent yet.")
    else:
        st.dataframe(
            pd.DataFrame(
                {
                    "Sent for snapshot": [a["snapshot_id"] for a in alerts],
                    "Store": [a["store"] for a in alerts],
                    "Item": [a["item_name"] for a in alerts],
                    "Before": [pw.fmt_usd(a["before_cents"]) for a in alerts],
                    "After": [pw.fmt_usd(a["after_cents"]) for a in alerts],
                    "Change": [f"{a['delta_rel']:+.0%}" for a in alerts],
                    "Explanation": [a["label"] for a in alerts],
                }
            ).iloc[::-1],
            hide_index=True,
            use_container_width=True,
        )

with tab_crawls:
    if not crawl_log:
        st.write("No crawls logged by price_watch_snapshot.py yet. Earlier baseline snapshots:")
        st.dataframe(
            pd.DataFrame([{"Store": n, "Snapshot": s[0], "Items": s[2]} for n, ss in snaps.items() for s in ss]),
            hide_index=True,
        )
    else:
        st.dataframe(pd.DataFrame(crawl_log).iloc[::-1], hide_index=True, use_container_width=True)
