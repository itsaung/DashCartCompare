"""Explicit observations from all 95 catalog photos, inspected 2026-09-18.

These are authored review decisions, not an automated visual classifier.
Use with the stable photo_sources.json mapping and saved photo hashes.
"""

# Index -> (observation, whether resolving the ambiguity still needs a guess).
OBSERVATIONS = {}


def observed(indices, text, guess=False):
    for index in indices:
        if index in OBSERVATIONS:
            raise ValueError(f"Duplicate photo observation {index}")
        OBSERVATIONS[index] = (text, guess)


observed([0], "Package visibly says 20 ct, Small-Fajita and net weight 23 oz: the count and weight listings describe the required package.")
observed([1], "Package says 10 ct, Medium-Soft Taco, 17.5 oz: not 20 fajita tortillas.")
observed([2], "Photo shows a four-cup yogurt multipack; raw_size describes each cup, not a single-cup purchase.")
observed([3], "Title identifies Original Unsweetened. Best guess: this is a distinct formulation from the requested regular Original; sweetness is not fully specified by the request.", True)
observed([4,23,40,41,42,63], "Photo shows packaged sliced deli turkey. Best guess for '3 deli turkey breasts': three retail packages rather than three whole breasts. Photo does not establish the shopper's intent.", True)
observed([5], "Photo shows an oven-roasted cured deli-sliced chicken breast package, not chicken strips.")
observed([6], "Can visibly says 16 FL OZ (473 mL). It does not match 33.8 fl oz or 10 gallons; one pound would require a mass/volume assumption.")
observed([7], "Photo shows the Half Baked ice-cream tub. Best guess: catalog bare '16 oz' means the usual one-pint volume; this photo does not visibly print the volume.", True)
observed([8], "Photo shows boneless skinless pink salmon with a fillet serving image. Best guess: the 16 oz bag contains suitable salmon fillet portions; individual-piece count is not established.", True)
observed([9,25,26,46,49,50,81,82,83], "Photo clearly shows a glass pasta-sauce jar, not the requested box. Applied literal container constraint from the benchmark.")
observed([10], "Photo shows prepared stuffed salmon portions. Best guess: an unqualified salmon-fillet request intends plain fish rather than stuffed prepared fish.", True)
observed([11], "Single-banana photo plus title '(each)' supports buying three units. Best guess assumes the ordering unit is each despite per-pound pricing metadata; checkout quantity was not verified.", True)
observed([12,13], "Photo shows a bunch of several bananas, not a selectable count of three. Best guess rejects a bunch for exactly three individual bananas; photographed fruit count is not a guaranteed sale count.", True)
observed([14], "Tray photo appears to show two salmon portions. Best guess accepts two fillets, but the catalog has variable-weight pricing and no guaranteed piece count.", True)
observed([15], "Photo explicitly says 12 bars, six 2-bar pouches; not six individual bars.")
observed([16], "Box front says Original cheese crackers; not Extra Toasty.")
observed([17], "Photo shows sweet banana quick bread. Best guess for an unqualified loaf of bread is ordinary sandwich/table bread, not banana cake-like bread.", True)
observed([18,55], "Mission bag visibly says 16 ct and NET WT 40 OZ, not 17.5 oz.")
observed([19], "Photo explicitly shows 2 PACK, two connected 5.3 oz cups; not one 5.3 oz package.")
observed([20,38,59], "Photo shows one foil-wrapped unsalted Kerrygold block, not the explicitly requested sticks.")
observed([21,61], "Box explicitly says 8 HALF STICKS, NET WT 1 LB; not four sticks under exact count/form matching.")
observed([22], "Package front explicitly says Mega Pack, Honey Smoked Turkey Breast, 22 oz. It cannot satisfy the 7/8/9/16 oz requests. Interpreting three turkey breasts as three packs is a separate guess.")
observed([24,71,80], "Photo and title identify Half Baked one-pint ice cream. Best guess interprets the request's bare '16 oz' as 16 fluid ounces, rather than mass.", True)
observed([27], "Package explicitly says TWO WILD ALASKA SALMON FILLETS. No plain/unseasoned requirement was stated, so two seasoned fillets satisfy the candidate-level request.")
observed([28], "Package explicitly says 8 granola bars, NET WT 6.7 OZ. It fails requests for 6, 18 or 100 bars; cardboard box also fails a literal bag constraint.")
observed([29,30,74,75,77,85,86,87,91,92,93], "Photo shows a cardboard retail box of granola bars. Under the existing literal-container benchmark rule, it does not satisfy a bag. Shopper may casually mean a pack; that interpretation remains a guess.", True)
observed([31,51,52,53,76,88,94], "Photo clearly shows a retail cardboard box containing crackers; no size/flavor restriction was specified.")
observed([32], "Hero package explicitly says 6 tortillas, not 20 or 24.")
observed([33], "La Fe package explicitly says ONE DOZEN, NET WT 17 OZ, not 17.5 oz.")
observed([34], "La Fe package explicitly says 10 COUNT, Net Wt 15 oz, not 17.5 oz.")
observed([35], "Mission package explicitly says 8 ct and NET WT 20 OZ; fails 20-count, 24-count and 17.5 oz requests.")
observed([36], "Photo is an unlabelled bowl of bulk cereal, not a marked 15 oz package. Best guess rejects a guaranteed fixed-size match.", True)
observed([37], "Daisy tub explicitly says 4% Milkfat and Pure & Natural, resolving the omitted descriptor in the title; catalog provides 16 oz size.")
observed([39], "Photo confirms Applegate Organics oven-roasted turkey, 6 oz. Gluten-free claim is not readable on this front image; accepting the requested product identity remains a best guess, not dietary verification.", True)
observed([43], "Photo explicitly shows 8 cans of 12 FL OZ, but catalog title says 12 ct. Best guess rejects the required 12-pack based on the image; image may be generic or outdated, so this is not confirmed.", True)
observed([44,45], "Photo shows six mochi ice-cream pieces, net weight 7.5 oz. Best guess rejects these as the requested 16 fl oz ice-cream package; no fluid volume is printed.", True)
observed([47], "Photo shows canned coconut milk. Best guess for an unqualified 'milk' request is beverage dairy milk, not cooking coconut milk.", True)
observed([48], "Photo shows a bag of dried coconut chips. Best guess for unqualified snack chips is potato/corn/similar savory chips, not dried coconut; the shopper did not explicitly specify a type.", True)
observed([54], "Photo says Golden Wheat and does not establish whole wheat. Best guess rejects it for a whole-wheat requirement; ingredient list was not inspected.", True)
observed([56], "Photo confirms shelf-stable unsweetened original, but explicitly shows SIX 32-fl-oz cartons. Catalog title lists a single 32 fl oz. Best guess rejects the six-pack for one 946 ml carton; conflicting image/title evidence remains unresolved.", True)
observed([57,78], "Photo shows gold-wrapped Kerrygold butter block, not unsalted butter sticks.")
observed([58], "Photo shows a spreadable Naturally Softer butter tub, not sticks.")
observed([60], "Box explicitly says milk from Irish grass-fed cows, UNSALTED, 2 STICKS, 2 x4 OZ (TOTAL 8 OZ). It satisfies the requested butter.")
observed([62,72,73], "Photo shows an individual prepared chicken breast with no weight label. Best guess rejects it as a guaranteed fixed 2 lb package; no weight can be measured from the image.", True)
observed([64,79], "Photo identifies Fresca sparkling soda water, original citrus. Best guess treats sweetened-style soda as different from unqualified sparkling water; request does not explicitly specify sweeteners.", True)
observed([65,66,67,68,69,70], "Photo shows bottled or multipack sparkling beverages. Best guess rejects a one-pound request: neither catalog nor image establishes net mass, and no water-density conversion is assumed.", True)
observed([84], "Photo shows one apple with no bag or weight label. Best guess rejects it as a verified 3 lb bag; image alone cannot establish sale weight.", True)
observed([89,90], "Photo shows a Goldfish snack bag, not a cardboard box; literal container requirement fails.")

assert set(OBSERVATIONS) == set(range(95))

# Explicit pair-level decisions, indexed by request and its observed product
# photos. Every current uncertain pair must have an entry; no default label.
ACCEPTABLE = {
    "r007": [60], "r036": [7], "r052": [11], "r071": [37],
    "r073": [0], "r080": [39], "r083": [7,24,71,80], "r091": [8],
    "r124": [31,51,52,53,76,88,94], "r129": [14,27],
    "r130": [4,22,23,40,41,42,63], "r141": [0],
}
