# DoorDash 92117 discovery validation

Discovery: anonymous DoorDash browser session, delivery location set by selecting the site's `92117 San Diego, CA 92117, USA` autocomplete result. Grocery > See All Stores Nearby, traversed from top to bottom while retaining cards removed by the virtualized list. 131 unique store IDs were observed.

Scope: one ZIP-based location and one listing at the time of the run, not every branch physically inside 92117 and not a guarantee of delivery to a particular street address. DoorDash mixes grocery, convenience, liquor, deli, specialty, and other listings in this view. Closed listings were retained.

- `discovered_stores.tsv`: observed store names, IDs, and original URL layout.
- `validation.json`: request results and exactly ten unique products for each passing store.
- `report.html`: readable store directory and expandable product samples.

The sample runner requests store home pages and at most two linked category pages, stopping once it has ten unique products with names and prices. Whole HTML responses can contain additional product cards; the validator decodes/retains at most ten products per store and does not crawl full catalogs. Failed or short samples are flagged, with no partial product group published. No products are padded or duplicated. Prices come from fresh unauthenticated store pages; they are not address-specific checkout quotes.

The existing historical inventory CSVs and full-catalog scraper are untouched. Re-running `validate_nearby_stores.py` resumes this validation file and skips already recorded stores; use a separate output directory/run configuration for a future fresh run.
