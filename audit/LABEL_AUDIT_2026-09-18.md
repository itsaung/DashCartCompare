# Complete label audit — 2026-09-18

Reviewed all 1658 current pairs across 150 requests.
Changed 270 labels; confirmed 1388.
Archived 69 obsolete decisions outside the current pool in the before snapshot.

AI adjudication against the frozen catalog; not independent human review or live verification.
Uncertain labels intentionally remain unresolved. No retrieval scores or thresholds were tuned.

## Results

- Acceptable: 447
- Incorrect: 1097
- Needs clarification: 114

## Changes

| Previous | Audited | Count |
|---|---|---:|
| Acceptable | Incorrect | 103 |
| Acceptable | Needs clarification | 67 |
| Incorrect | Acceptable | 25 |
| Incorrect | Needs clarification | 39 |
| Needs clarification | Acceptable | 6 |
| Needs clarification | Incorrect | 30 |

## Method and remaining limits

Every candidate title, category and package was inspected in request groups. Explicit per-request adjudications were materialized only after validating catalog/pool/request hashes. Shared candidates within paraphrase groups were checked for agreement.

The request schema was corrected for r096/r144 (no invented water-only tuna restriction), r083 (ambiguous bare oz on ice cream), and r039 (no fixed 12 oz unsalted dairy butter found in the full frozen catalog; the 12 oz macadamia nut butter is a different product). Request and guideline versions are now v2.

Candidate-level uncertainty does not by itself prove that a request has no answer in the entire catalog. Most other no-match request assertions have not been exhaustively searched beyond their pools. Exact package matching, including multipack count, is the benchmark policy; basket quantity optimization is separate.

The old heuristic remains a draft-label generator for future unseen candidates, not gold truth. It must not overwrite these adjudications. Independent human review of held-out labels remains valuable.

Full evidence, old decisions and new rationales: `label_audit_2026-09-18.json`. Complete original file: `label_decisions_before_2026-09-18.json`.

## Changed pairs

| Key | Request | Candidate | Before | After |
|---|---|---|---|---|
| r004 / 1042759 / 8776479882 | 0.5 gal Oatly Original Oat Milk | Oatly Gluten Free Full Fat Oat Milk Carton (0.5 gal) | Acceptable | Incorrect |
| r004 / 1742136 / 32390457372 | 0.5 gal Oatly Original Oat Milk | Oatly Gluten Free Full Fat Oat Milk Carton (0.5 gal) | Acceptable | Incorrect |
| r007 / 24325284 / 9819999719 | 8 oz Kerrygold Grass Fed Pure Irish Unsalted Butter Sticks | Kerrygold Grass-Fed Pure Irish Butter Unsalted (8 oz) | Acceptable | Needs clarification |
| r007 / 1742136 / 34049152986 | 8 oz Kerrygold Grass Fed Pure Irish Unsalted Butter Sticks | Kerrygold Pure Unsalted Irish Butter (8 oz) | Acceptable | Needs clarification |
| r007 / 35802549 / 30994828069 | 8 oz Kerrygold Grass Fed Pure Irish Unsalted Butter Sticks | Kerrygold Pure Unsalted Irish Butter (8 oz) | Acceptable | Needs clarification |
| r007 / 1742136 / 11194800448 | 8 oz Kerrygold Grass Fed Pure Irish Unsalted Butter Sticks | Kerrygold Unsalted Irish Butter Sticks (4 oz x 2 ct) | Acceptable | Needs clarification |
| r007 / 1742136 / 10109271326 | 8 oz Kerrygold Grass Fed Pure Irish Unsalted Butter Sticks | Kerrygold Pure Irish Butter (8 oz) | Acceptable | Needs clarification |
| r009 / 29631686 / 1000030409614176 | 52 fl oz of Simply Nature Organic Orange Juice please | Simply Nature Organic 100% Apple Juice Bottle (64 fl oz) | Acceptable | Incorrect |
| r009 / 1042759 / 1000037999605003 | 52 fl oz of Simply Nature Organic Orange Juice please | Simply Orange Pulp-Free Juice Bottle (76 fl oz) | Needs clarification | Incorrect |
| r011 / 24325284 / 10306334884 | 80 oz Aldi Basmati Rice | Brown Rice Basmati (by pound) | Needs clarification | Incorrect |
| r012 / 1742136 / 11931730368 | 48 fl oz Califia Farms Organic Dairy Free Original Oat Milk Bottle | Califia Farms Gluten & Dairy Free Extra Creamy Oat Milk Bottle (48 fl oz) | Needs clarification | Incorrect |
| r012 / 35802549 / 30994828097 | 48 fl oz Califia Farms Organic Dairy Free Original Oat Milk Bottle | Califia Farms Gluten & Dairy Free Extra Creamy Oat Milk Bottle (48 fl oz) | Needs clarification | Incorrect |
| r012 / 1742136 / 10109224174 | 48 fl oz Califia Farms Organic Dairy Free Original Oat Milk Bottle | Califia Farms Dairy & Soy Free Unsweetened Almond Milk Bottle (48 fl oz) | Needs clarification | Incorrect |
| r015 / 29631686 / 1000030409614263 | 64 fl oz Friendly Farms Almond Milk Original | Friendly Farms Original Unsweetened Almond Milk (64 fl oz) | Acceptable | Needs clarification |
| r015 / 29631686 / 22646303838 | 64 fl oz Friendly Farms Almond Milk Original | Friendly Farms Gluten Free Original Unsweetened Vanilla Almond Milk Carton (0.5 gal) | Acceptable | Incorrect |
| r015 / 29631686 / 1000030409614268 | 64 fl oz Friendly Farms Almond Milk Original | Friendly Farms Unsweetened Almond Milk Vanilla (64 fl oz) | Needs clarification | Incorrect |
| r019 / 1042759 / 38131667643 | 3 lb Gala Apples Bag | Gala Apples | Acceptable | Needs clarification |
| r022 / 1042759 / 8776479870 | 946 ml Almond Breeze Unsweetened Original Almond Milk Shelf Stable Carton | Almond Breeze Original Shelf-Stable Almond Milk (32 fl oz) | Acceptable | Incorrect |
| r022 / 1742136 / 10109224134 | 946 ml Almond Breeze Unsweetened Original Almond Milk Shelf Stable Carton | Almond Breeze Unsweetened Original Almond Milk (32 fl oz) | Acceptable | Needs clarification |
| r023 / 1742136 / 24507948329 | 2 lb Honeycrisp Apples | Organic Honeycrisp Apples (each) | Acceptable | Incorrect |
| r023 / 1742136 / 22747549348 | 2 lb Honeycrisp Apples | Honeycrisp Apple | Acceptable | Incorrect |
| r023 / 24325284 / 7935230420 | 2 lb Honeycrisp Apples | Organic Honeycrisp Apple (each) | Acceptable | Incorrect |
| r024 / 1742136 / 24507948329 | two pounds of Honeycrisp apples | Organic Honeycrisp Apples (each) | Acceptable | Incorrect |
| r024 / 1742136 / 22747549348 | two pounds of Honeycrisp apples | Honeycrisp Apple | Acceptable | Incorrect |
| r024 / 24325284 / 7935230420 | two pounds of Honeycrisp apples | Organic Honeycrisp Apple (each) | Acceptable | Incorrect |
| r025 / 24325284 / 1000001427173366 | 12 oz ground coffee | Death Wish Coffee Organic Espresso Roast Ground Coffee (9 oz) | Acceptable | Incorrect |
| r027 / 1742136 / 10109224134 | 0.5 gal almond milk | Almond Breeze Unsweetened Original Almond Milk (32 fl oz) | Acceptable | Incorrect |
| r028 / 1742136 / 10109224187 | 0.5 gal almond milk, any brand | Almond Breeze Unsweetened Vanilla Almond Milk (96 fl oz) | Acceptable | Incorrect |
| r029 / 1742136 / 17270803204 | 0.5 gal oat milk | Oatly Original Oat Milk (32 fl oz) | Acceptable | Incorrect |
| r032 / 1042759 / 39204374517 | 12 ct large eggs | Vital Farms Organic Pasture Raised Grade A XL Eggs (12 ct) | Acceptable | Incorrect |
| r033 / 35802549 / 30994827152 | a dozen large eggs, any brand is fine | Kroger Cage Free Extra Large White Eggs (12 ct) | Acceptable | Incorrect |
| r035 / 1042759 / 32962373534 | 20 oz whole wheat bread | Nature's Own 100% Whole Grain Wheat Bread (20 oz) | Incorrect | Acceptable |
| r035 / 1742136 / 1000002555061094 | 20 oz whole wheat bread | Artesano Golden Wheat Bakery Bread (20 oz) | Acceptable | Needs clarification |
| r036 / 24325284 / 9122402372 | 16 fl oz ice cream | Bubbies Ice Cream Mochi Strawberry Ice Cream (6 ct) | Incorrect | Needs clarification |
| r036 / 24325284 / 13949771340 | 16 fl oz ice cream | Bubbies Ice Cream Premium Mochi Mango Ice Cream (6 ct) | Incorrect | Needs clarification |
| r036 / 29631686 / 32760619640 | 16 fl oz ice cream | Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (16 oz) | Incorrect | Needs clarification |
| r038 / 1742136 / 30221023615 | 16 oz chicken breast strips | Hand Trimmed Chicken Breast Strips Pack | Acceptable | Incorrect |
| r041 / 29631686 / 22646325374 | 5.3 oz flavored greek yogurt, any flavor | Friendly Farms Low Fat Strawberry Greek Yogurt 4 ct (5.3 oz) | Acceptable | Needs clarification |
| r042 / 1042759 / 10554770200 | 15 oz cereal | Golden Crisp Breakfast Cereal (14.75 oz) | Acceptable | Incorrect |
| r042 / 24325284 / 5970031115 | 15 oz cereal | 6 Grain Hot Cereal | Acceptable | Needs clarification |
| r045 / 1042759 / 1000010135871003 | milk | Muscle Milk High Protein Chocolate Shake (14 fl oz) | Acceptable | Incorrect |
| r045 / 1042759 / 1000010135871004 | milk | Muscle Milk High Protein Strawberries 'N Cream Shake (14 fl oz) | Acceptable | Incorrect |
| r045 / 24325284 / 5648872769 | milk | Sprouts Coconut Milk (13.5 oz) | Acceptable | Needs clarification |
| r046 / 1042759 / 1000010135871003 | milk please | Muscle Milk High Protein Chocolate Shake (14 fl oz) | Acceptable | Incorrect |
| r046 / 1042759 / 1000010135871004 | milk please | Muscle Milk High Protein Strawberries 'N Cream Shake (14 fl oz) | Acceptable | Incorrect |
| r046 / 24325284 / 5648872769 | milk please | Sprouts Coconut Milk (13.5 oz) | Incorrect | Needs clarification |
| r047 / 1042759 / 1000010135871003 | some milk | Muscle Milk High Protein Chocolate Shake (14 fl oz) | Acceptable | Incorrect |
| r047 / 1742136 / 9810006181 | some milk | A2 Milk Co. Pasteurized Whole Milk Carton (59 fl oz) | Incorrect | Acceptable |
| r047 / 24325284 / 5648872769 | some milk | Sprouts Coconut Milk (13.5 oz) | Acceptable | Needs clarification |
| r048 / 1042759 / 9287188724 | a bag of chips | Pringles Sour Cream and Onion Potato Crisps Chips Can (5.5 oz) | Acceptable | Incorrect |
| r048 / 1742136 / 17391871045 | a bag of chips | Pringles Sour Cream and Onion Potato Crisps Chips Can (5.5 oz) | Acceptable | Incorrect |
| r048 / 24325284 / 10230027000 | a bag of chips | Sprouts Organic Coconut Chips (7 oz) | Acceptable | Needs clarification |
| r048 / 1042759 / 10200480905 | a bag of chips | Lily's No Sugar Added Dark Chocolate Style Baking Chips (9 oz) | Acceptable | Incorrect |
| r048 / 1042759 / 10483670398 | a bag of chips | Chips Ahoy! Chewy Chocolate Chip Cookies Family Size (19.5 oz) | Acceptable | Incorrect |
| r048 / 24325284 / 6631200386 | a bag of chips | Vegan Chocolate Chips Cookies (12 oz) | Acceptable | Incorrect |
| r048 / 1042759 / 37167972310 | a bag of chips | Signature Select Milk Chocolate Chips (11.5 oz) | Acceptable | Incorrect |
| r048 / 1742136 / 10109275514 | a bag of chips | Signature Select Milk Chocolate Chips (11.5 oz) | Acceptable | Incorrect |
| r049 / 1042759 / 39153607476 | chips, one bag | Ghirardelli Premium Milk Chocolate Baking Chips Bag (11.5 oz) | Acceptable | Incorrect |
| r049 / 24325284 / 10230027000 | chips, one bag | Sprouts Organic Coconut Chips (7 oz) | Acceptable | Needs clarification |
| r050 / 35802549 / 31447193589 | a loaf of bread | Bakehouse Bread Company Banana Bread (14 oz) | Acceptable | Needs clarification |
| r051 / 1742136 / 12518453564 | 2 lb chicken breast | Roasted Chicken Breast Hot | Acceptable | Needs clarification |
| r051 / 1742136 / 32695775745 | 2 lb chicken breast | Fried Chicken Breast Hot | Acceptable | Needs clarification |
| r051 / 1742136 / 1000020349873024 | 2 lb chicken breast | Grilled Chicken Breast, Cold | Acceptable | Needs clarification |
| r051 / 24325284 / 25724283559 | 2 lb chicken breast | Mary's Chicken Boneless Skinless Chicken Breast Pack | Acceptable | Incorrect |
| r051 / 29631686 / 25302960431 | 2 lb chicken breast | Kirkwood Boneless Skinless Chicken Breasts Pack | Acceptable | Incorrect |
| r052 / 29631686 / 1000037210864004 | 3 bananas | Organic Bananas (bunch) | Incorrect | Needs clarification |
| r052 / 29631686 / 33873154338 | 3 bananas | Organic Bananas Bunch | Incorrect | Needs clarification |
| r052 / 29631686 / 43649193203 | 3 bananas | Banana (each) | Incorrect | Needs clarification |
| r058 / 29631686 / 1000030409614278 | 16 oz Simply Nature Organic Creamy Peanut Butter | Simply Nature Organic Salted Butter (16 oz) | Acceptable | Incorrect |
| r059 / 1042759 / 1000011054468004 | 5 oz Starkist Chunk Light Tuna in Water Can | Starkist Chunk Light Tuna in Oil Can (5 oz) | Acceptable | Incorrect |
| r060 / 1042759 / 1000011054468004 | 5 oz can of Starkist Chunk Light Tuna in Water, get me one | Starkist Chunk Light Tuna in Oil Can (5 oz) | Acceptable | Incorrect |
| r061 / 29631686 / 22646288070 | 29.75 oz Mama Cozzi Rising Crust Four Cheese Pizza | Mama Cozzi Rising Crust Pepperoni Pizza (30.2 oz) | Acceptable | Incorrect |
| r061 / 29631686 / 22646327844 | 29.75 oz Mama Cozzi Rising Crust Four Cheese Pizza | Mama Cozzi Stuffed Crust Cheese Pizza (30.4 oz) | Needs clarification | Incorrect |
| r062 / 24325284 / 21040431452 | 12 fl oz x 12 ct La Croix Razz-Cranberry Sparkling Water Cans | La Croix Sparkling Water Pure Cans (12 oz x 8 ct) | Needs clarification | Incorrect |
| r064 / 29631686 / 24222461766 | 18 ct Millville Chocolate Chip Chewy Granola Bars | Millville Chocolate Chip Peanut Butter Chewy Granola Bars (18 ct) | Acceptable | Incorrect |
| r065 / 29631686 / 22646327699 | 12 oz Season's Choice Steamable Frozen Broccoli Florets | Season's Choice Steamable Frozen Broccoli Florets (12 oz) | Incorrect | Acceptable |
| r065 / 29631686 / 1000032247130013 | 12 oz Season's Choice Steamable Frozen Broccoli Florets | Season's Choice Steamable Frozen Cut Green Bean (12 oz) | Needs clarification | Incorrect |
| r065 / 29631686 / 1000030409614247 | 12 oz Season's Choice Steamable Frozen Broccoli Florets | Season's Choice Steamable Sweet Corn (12 oz) | Needs clarification | Incorrect |
| r065 / 29631686 / 1000030409614217 | 12 oz Season's Choice Steamable Frozen Broccoli Florets | Season's Choice Steamable Sweet Peas (12 oz) | Needs clarification | Incorrect |
| r066 / 29631686 / 27761443669 | 12 oz Goldfish Cheddar Crackers | Goldfish Xtra Cheddar Crackers (12 oz) | Acceptable | Incorrect |
| r068 / 29631686 / 1000030409614579 | 9 oz Lunch Mate Oven Roasted Turkey Breast | Lunch Mate Deli Style Mesquite Smoked Turkey Breast (9 oz) | Needs clarification | Incorrect |
| r070 / 29631686 / 1000030409614421 | 6 ct Millville Chewy Dipped Peanut Butter Granola Bars | Millville Chewy Dipped Granola Bars Chocolate Chip (6 ct) | Acceptable | Incorrect |
| r070 / 29631686 / 22646327063 | 6 ct Millville Chewy Dipped Peanut Butter Granola Bars | Millville Peanut Butter Crunchy Granola Bars (6 ct) | Needs clarification | Incorrect |
| r072 / 35802549 / 30994828681 | 8 oz Foster Farms Oven Roasted Turkey Breast | Foster Farms Honey Roasted Turkey Breast (8 oz) | Acceptable | Incorrect |
| r073 / 29631686 / 1000030409614136 | 20 ct Pueblo Lindo Fajita Flour Tortillas | Pueblo Lindo Fajita Flour Tortillas (23 oz) | Incorrect | Needs clarification |
| r073 / 29631686 / 1000032999710119 | 20 ct Pueblo Lindo Fajita Flour Tortillas | Pueblo Lindo Flour Tortillas (17.5 oz) | Incorrect | Needs clarification |
| r075 / 29631686 / 38873432785 | 16 oz Aldi Powdered Peanut Butter | Aldi Paper Bag | Needs clarification | Incorrect |
| r077 / 1042759 / 27211830562 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Florets (10.8 oz) | Incorrect | Acceptable |
| r077 / 1742136 / 10261586941 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Florets (10.8 oz) | Incorrect | Acceptable |
| r077 / 35802549 / 30994826159 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Florets (10.8 oz) | Incorrect | Acceptable |
| r077 / 1042759 / 22856847007 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Cauliflower & Carrots Mixed Vegetables (10.8 oz) | Needs clarification | Incorrect |
| r077 / 1742136 / 12776223552 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Cuts (10.8 oz) | Needs clarification | Incorrect |
| r077 / 1742136 / 9357566380 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Sauced Cheesy Broccoli (10.8 oz) | Needs clarification | Incorrect |
| r077 / 35802549 / 41517124658 | 10.8 oz Birds Eye Steamfresh Frozen Broccoli Florets | Birds Eye Steamfresh Frozen Broccoli Cauliflower & Carrots Mixed Vegetables (10.8 oz) | Needs clarification | Incorrect |
| r078 / 1742136 / 18269401867 | 5.3 oz Good Culture 2% Milkfat Simply Cottage Cheese | Good Culture Simply Low-Fat 2% Classic Cottage Cheese (5.3 oz) | Needs clarification | Acceptable |
| r079 / 29631686 / 1000030409614203 | 17 fl oz PurAqua Frost Lemonade Sparkling Water Bottle | PurAqua Sparkling Frost Water Lemonade (17 fl oz) | Needs clarification | Acceptable |
| r079 / 29631686 / 22646304007 | 17 fl oz PurAqua Frost Lemonade Sparkling Water Bottle | PurAqua Frost Pink Grapefruit Sparkling Flavored Water Bottle (17 fl oz) | Acceptable | Incorrect |
| r079 / 29631686 / 22646304009 | 17 fl oz PurAqua Frost Lemonade Sparkling Water Bottle | PurAqua Frost Orange Mango Sparkling Water Bottle (17 fl oz) | Needs clarification | Incorrect |
| r079 / 29631686 / 42177046801 | 17 fl oz PurAqua Frost Lemonade Sparkling Water Bottle | PurAqua Frost Sparkling Black Raspberry Water (16 oz) | Needs clarification | Incorrect |
| r079 / 29631686 / 42177046800 | 17 fl oz PurAqua Frost Lemonade Sparkling Water Bottle | PurAqua Sparkling Frost Caffeine Strawberry Citrus Sparkling Water (16 oz) | Needs clarification | Incorrect |
| r080 / 24325284 / 43911612966 | 6 oz Applegate Farms Organics Gluten Free Oven Roasted Turkey Breast | Applegate Organic Oven Roasted Turkey Breast (6 oz) | Incorrect | Needs clarification |
| r081 / 29631686 / 22646327016 | 8.8 oz Savoritz Mini Peanut Butter Sandwich Crackers | Savoritz 4 Kids Mini Cheese Sandwich Crackers (8.8 oz) | Acceptable | Incorrect |
| r083 / 29631686 / 32760619640 | 16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream | Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (16 oz) | Acceptable | Needs clarification |
| r083 / 1042759 / 8776540508 | 16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream | Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (1 pt) | Incorrect | Needs clarification |
| r083 / 1742136 / 10582421916 | 16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream | Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (1 pt) | Incorrect | Needs clarification |
| r083 / 35802549 / 30994833097 | 16 oz Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream | Ben & Jerry's Half Baked Chocolate & Vanilla Ice Cream (1 pt) | Incorrect | Needs clarification |
| r085 / 1742136 / 10109271315 | 4 ct Land O'Lakes Unsalted Butter Sticks | Land O'Lakes Unsalted Butter Half Sticks (16 oz) | Incorrect | Needs clarification |
| r085 / 35802549 / 30994827505 | 4 ct Land O'Lakes Unsalted Butter Sticks | Land O'Lakes Unsalted Butter Half Sticks (16 oz) | Incorrect | Needs clarification |
| r087 / 1042759 / 19991456004 | 8 oz Ruffles Flamin' Hot Flavored Potato Chips | Ruffles Flamin' Hot Cheddar Cheese & Sour Cream Flavored Potato Chips Bag (8 oz) | Acceptable | Incorrect |
| r088 / 1042759 / 27734109846 | 12 fl oz x 12 ct Diet Coke Diet Cola Soda | Diet Coke Soda Soft Drink Fridge Pack Cans (12 fl oz x 12 ct) | Needs clarification | Acceptable |
| r088 / 1742136 / 20746643762 | 12 fl oz x 12 ct Diet Coke Diet Cola Soda | Diet Coke Caffeine Free No Sugar & Calories Soda Cans Fridge Pack (355 ml x 12 ct) | Needs clarification | Incorrect |
| r088 / 1742136 / 9236580251 | 12 fl oz x 12 ct Diet Coke Diet Cola Soda | Diet Coke Soda Soft Drink Fridge Pack Cans (12 fl oz x 12 ct) | Needs clarification | Acceptable |
| r091 / 1742136 / 1000013953588333 | 16 oz salmon fillet | Atlantic Premium Salmon Fillet Center Cut (pack) | Acceptable | Incorrect |
| r091 / 1742136 / 1000031966157093 | 16 oz salmon fillet | Skuna Bay Fresh Atlantic Salmon Fillet (by pound) | Acceptable | Incorrect |
| r091 / 1742136 / 14533931524 | 16 oz salmon fillet | Fresh Farmed Atlantic Salmon Fillet Color Added (by pound) | Acceptable | Incorrect |
| r091 / 1742136 / 21423420361 | 16 oz salmon fillet | Open Nature Alaskan Sockeye Salmon Skin On Wild Caught Fillet (pack) | Acceptable | Incorrect |
| r091 / 1742136 / 21423420362 | 16 oz salmon fillet | Atlantic Norweigan Salmon Fillet with Seafood & Lobster Pack | Acceptable | Incorrect |
| r091 / 24325284 / 1000042139843016 | 16 oz salmon fillet | Coho Salmon Fillet (each) | Acceptable | Incorrect |
| r091 / 24325284 / 10600730459 | 16 oz salmon fillet | Sprouts Fresh Atlantic Salmon Fillet (by pound) | Acceptable | Incorrect |
| r091 / 29631686 / 22646284002 | 16 oz salmon fillet | Fresh Norwegian Atlantic Salmon Fillet Pack | Acceptable | Incorrect |
| r091 / 29631686 / 33905145040 | 16 oz salmon fillet | Fremont Fish Market Boneless Skinless Wild Caught Pink Salmon (16 oz) | Incorrect | Needs clarification |
| r094 / 29631686 / 22646326552 | 12 oz frozen broccoli florets | Broccoli Florets (12 oz) | Acceptable | Incorrect |
| r095 / 35802549 / 30994851727 | 6 ct granola bars | Chewy Granola Bars 100% Whole Grains Chocolate Chip Granola Bars (6.7 oz) | Incorrect | Needs clarification |
| r095 / 29631686 / 22646327062 | 6 ct granola bars | Millville Crunchy Granola Bars Oats and Honey 2 Packs (6 ct) | Acceptable | Needs clarification |
| r096 / 1042759 / 1000011054468004 | 5 oz canned tuna | Starkist Chunk Light Tuna in Oil Can (5 oz) | Incorrect | Acceptable |
| r096 / 1042759 / 1000040270769002 | 5 oz canned tuna | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r096 / 35802549 / 1000013334011006 | 5 oz canned tuna | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r096 / 35802549 / 44208371799 | 5 oz canned tuna | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r098 / 1742136 / 1000013953588402 | 9 oz deli turkey breast | Primo Taglio Pan Roasted Turkey Breast | Acceptable | Incorrect |
| r098 / 35802549 / 30994828628 | 9 oz deli turkey breast | Deli Fresh Turkey Breast Mega Pack | Acceptable | Needs clarification |
| r099 / 1042759 / 20277094899 | 12 fl oz x 12 ct sparkling water | Fresca Grapefruit Citrus Original Sparkling Soda Water (12 fl oz x 12 ct) | Acceptable | Needs clarification |
| r099 / 1742136 / 17270795871 | 12 fl oz x 12 ct sparkling water | Fresca Grapefruit Citrus Original Sparkling Soda Water (12 fl oz x 12 ct) | Acceptable | Needs clarification |
| r101 / 24325284 / 20640849539 | 20 ct flour tortillas | Hero Bread Flour Tortillas (9.3 oz) | Incorrect | Needs clarification |
| r101 / 24325284 / 24472659379 | 20 ct flour tortillas | Mission Foods Large Flour Tortillas | Acceptable | Needs clarification |
| r103 / 35802549 / 30994828628 | 8 oz deli turkey | Deli Fresh Turkey Breast Mega Pack | Acceptable | Needs clarification |
| r104 / 24325284 / 5648919472 | 17.5 oz flour tortillas | La Fe Tortillas Unbleached Flour Tortillas (10 ct) | Incorrect | Needs clarification |
| r104 / 24325284 / 24472659379 | 17.5 oz flour tortillas | Mission Foods Large Flour Tortillas | Acceptable | Needs clarification |
| r104 / 24325284 / 5648919475 | 17.5 oz flour tortillas | La Fe Tortillas No Preservatives Flour Tortillas (12 ct) | Incorrect | Needs clarification |
| r104 / 1742136 / 37596221536 | 17.5 oz flour tortillas | Mission Burrito Flour Tortillas (16 ct) | Incorrect | Needs clarification |
| r104 / 35802549 / 30994674460 | 17.5 oz flour tortillas | Mission Burrito Flour Tortillas (16 ct) | Incorrect | Needs clarification |
| r106 / 24325284 / 20640849539 | 24 ct flour tortillas | Hero Bread Flour Tortillas (9.3 oz) | Incorrect | Needs clarification |
| r106 / 24325284 / 24472659379 | 24 ct flour tortillas | Mission Foods Large Flour Tortillas | Acceptable | Needs clarification |
| r107 / 35802549 / 30994851727 | 18 ct granola bars | Chewy Granola Bars 100% Whole Grains Chocolate Chip Granola Bars (6.7 oz) | Incorrect | Needs clarification |
| r109 / 35802549 / 32929359730 | 5.3 oz cottage cheese | Daisy Brand 4% Milkfat Cottage Cheese 2 ct (5.3 oz) | Acceptable | Needs clarification |
| r111 / 35802549 / 30994828628 | 7 oz deli turkey | Deli Fresh Turkey Breast Mega Pack | Acceptable | Needs clarification |
| r112 / 35802549 / 30994828628 | 16 oz deli turkey | Deli Fresh Turkey Breast Mega Pack | Acceptable | Needs clarification |
| r113 / 29631686 / 42177046800 | 33.8 fl oz sparkling water | PurAqua Sparkling Frost Caffeine Strawberry Citrus Sparkling Water (16 oz) | Incorrect | Needs clarification |
| r117 / 1742136 / 24507948329 | 3 lb Honeycrisp Apples | Organic Honeycrisp Apples (each) | Acceptable | Incorrect |
| r117 / 1742136 / 22747549348 | 3 lb Honeycrisp Apples | Honeycrisp Apple | Acceptable | Incorrect |
| r117 / 24325284 / 7935230420 | 3 lb Honeycrisp Apples | Organic Honeycrisp Apple (each) | Acceptable | Incorrect |
| r118 / 35802549 / 31846791568 | 46 fl oz orange juice | Kroger Mandarin Orange Cups in 100% Juice (4 oz x 4 ct) | Needs clarification | Incorrect |
| r119 / 24325284 / 23372596582 | 9 ct pasta sauce jars, any flavor | Sauz Pasta Sauce Summer Lemon Marinara Pasta Sauce (25 oz) | Incorrect | Acceptable |
| r119 / 24325284 / 5648960048 | 9 ct pasta sauce jars, any flavor | Sprouts Pasta Sauce Garlic (25 oz) | Incorrect | Acceptable |
| r119 / 35802549 / 30994838342 | 9 ct pasta sauce jars, any flavor | Kroger Traditional Pasta Sauce (24 oz) | Incorrect | Acceptable |
| r119 / 24325284 / 14040263051 | 9 ct pasta sauce jars, any flavor | Sprouts Organic Pasta Sauce Garlic (25 oz) | Incorrect | Acceptable |
| r119 / 29631686 / 22646325794 | 9 ct pasta sauce jars, any flavor | Priano Marinara Pasta Sauce (24 oz) | Incorrect | Acceptable |
| r122 / 1042759 / 23693652338 | a can of tuna | Friskies Seafood Sensations Salmon Tuna Shrimp & Seaweed Dry Cat Food (16 lb) | Acceptable | Incorrect |
| r122 / 1742136 / 1000032834131019 | a can of tuna | Delectables Lickables Bisque Tuna & Chicken Tuna Tuna & Shrimp Lickable Cat Treats (1.4 oz x 12 ct) | Acceptable | Incorrect |
| r122 / 24325284 / 11764452060 | a can of tuna | Spicy Tuna Roll (9.7 oz) | Acceptable | Incorrect |
| r122 / 1742136 / 11301068147 | a can of tuna | Signature Select Tuna Salad (15 oz) | Acceptable | Incorrect |
| r122 / 24325284 / 12095632558 | a can of tuna | Salad Herb Tuna (each) | Acceptable | Incorrect |
| r122 / 35802549 / 31292946711 | a can of tuna | Resers Tuna Salad (12 oz) | Acceptable | Incorrect |
| r122 / 1742136 / 10448101440 | a can of tuna | ACE Sushi Tuna Roll (7.4 oz) | Acceptable | Incorrect |
| r123 / 1042759 / 1000029530296001 | a jar of peanut butter | Reese's Peanut Butter Mini Pumpkins Unwrapped Chocolate Candies (7 oz) | Acceptable | Incorrect |
| r123 / 1042759 / 1000040042508001 | a jar of peanut butter | Smucker's Uncrustables Frozen Peanut Butter & Raspberry Spread Sandwiches Box 4 ct (8 oz) | Acceptable | Incorrect |
| r123 / 1042759 / 10000476580 | a jar of peanut butter | Smucker's Uncrustables Frozen Peanut Butter & Grape Jelly Sandwiches (2 oz x 4 ct) | Acceptable | Incorrect |
| r123 / 1042759 / 10394314071 | a jar of peanut butter | GoMacro Peanut Butter Chocolate Chip Macro Bar (2.4 oz) | Acceptable | Incorrect |
| r123 / 1042759 / 10553655750 | a jar of peanut butter | Smucker's Uncrustables Frozen Peanut Butter & Strawberry Jam Sandwiches (2 oz x 4 ct) | Acceptable | Incorrect |
| r123 / 24325284 / 22980623119 | a jar of peanut butter | Sprouts Peanut Butter Popcorn (6 oz) | Acceptable | Incorrect |
| r124 / 1042759 / 1000002739432004 | 1 box of crackers | Goldfish Cheddar Cheese Baked Snack Crackers (6.6 oz) | Acceptable | Needs clarification |
| r124 / 1042759 / 1000003155996001 | 1 box of crackers | Goldfish Flavor Blasted Xtra Cheddar Baked Snack Crackers (6.6 oz) | Acceptable | Needs clarification |
| r124 / 1042759 / 10255951505 | 1 box of crackers | Barnums Snak Saks! Animals Crackers (8 oz) | Acceptable | Incorrect |
| r124 / 1042759 / 10288800611 | 1 box of crackers | Club Crackers Snack Stacks Original Crackers (12.5 oz) | Acceptable | Needs clarification |
| r124 / 1042759 / 10379468273 | 1 box of crackers | Cheez-It White Cheddar Baked Snack Crackers Grab Bag (7 oz) | Acceptable | Incorrect |
| r124 / 1042759 / 13472443448 | 1 box of crackers | Ritz Peanut Butter Flavored Filling Sandwich Crackers Snack Packs (8 pk x 6 ct) | Acceptable | Needs clarification |
| r124 / 1742136 / 12044237780 | 1 box of crackers | Club Crackers Snack Stacks Original Crackers (12.5 oz) | Acceptable | Needs clarification |
| r124 / 35802549 / 30994851749 | 1 box of crackers | Club Crackers Snack Stacks Original Crackers (12.5 oz) | Acceptable | Needs clarification |
| r124 / 24325284 / 24049084915 | 1 box of crackers | Mary's Gone Crackers Organic Herb Crackers (4 oz) | Acceptable | Needs clarification |
| r124 / 24325284 / 22272682071 | 1 box of crackers | Sprouts Original Water Crackers (4.4 oz) | Acceptable | Needs clarification |
| r124 / 24325284 / 24463140609 | 1 box of crackers | Mary's Gone Crackers Organic Original Super Seed Crackers (4 oz) | Acceptable | Needs clarification |
| r126 / 1042759 / 10199849891 | a bag of granola bars | Nature Valley Crunchy Oats 'n Honey Granola Bars Pouches (1.49 oz x 6 ct) | Acceptable | Needs clarification |
| r126 / 1042759 / 12649276025 | a bag of granola bars | Nature Valley Sweet & Salty Nut Peanut Granola Bars (1.2 oz x 6 ct) | Acceptable | Needs clarification |
| r126 / 1042759 / 15040347666 | a bag of granola bars | Chewy Granola Bars Variety Pack (0.84 oz x 18 ct) | Acceptable | Needs clarification |
| r126 / 1042759 / 26047649087 | a bag of granola bars | Chewy Chocolate Chip Granola Bars Value Pack (0.84 oz x 18 ct) | Acceptable | Needs clarification |
| r126 / 1042759 / 26461382000 | a bag of granola bars | Chewy Granola Bars Dipps Covered Chocolate Chip Granola Bars (1.09 oz x 6 ct) | Acceptable | Needs clarification |
| r126 / 1042759 / 27390894337 | a bag of granola bars | Quaker Chewy Granola Bars Chocolate Chip (8 ct) | Acceptable | Needs clarification |
| r126 / 1742136 / 25836986384 | a bag of granola bars | Chewy Granola Bars S'mores Granola Bars (0.84 oz x 8 ct) | Acceptable | Needs clarification |
| r126 / 35802549 / 30994851726 | a bag of granola bars | Chewy Granola Bars S'mores Granola Bars (0.84 oz x 8 ct) | Acceptable | Needs clarification |
| r126 / 35802549 / 30994851727 | a bag of granola bars | Chewy Granola Bars 100% Whole Grains Chocolate Chip Granola Bars (6.7 oz) | Acceptable | Needs clarification |
| r126 / 1742136 / 25836986386 | a bag of granola bars | Chewy Granola Bars Peanut Butter Chocolate Chip Granola Bars (0.84 oz x 8 ct) | Acceptable | Needs clarification |
| r126 / 35802549 / 30994851728 | a bag of granola bars | Chewy Granola Bars Peanut Butter Chocolate Chip Granola Bars (0.84 oz x 8 ct) | Acceptable | Needs clarification |
| r126 / 1742136 / 23598313944 | a bag of granola bars | Quaker Oats Chewy Granola Bars Big Chocolate Chip Granola Bars (1.48 oz x 5 ct) | Acceptable | Needs clarification |
| r128 / 1042759 / 20815743403 | a box of pasta sauce | Chef Boyardee Beefaroni Pasta in Tomato & Meat Sauce Can (15 oz) | Acceptable | Incorrect |
| r128 / 1042759 / 21366092208 | a box of pasta sauce | Prego Gluten Free Italian Flavored with Meat Pasta Sauce (24 oz) | Acceptable | Needs clarification |
| r128 / 1042759 / 21366092209 | a box of pasta sauce | Prego Italian Roasted Garlic Parmesan Pasta Sauce (24 oz) | Acceptable | Needs clarification |
| r128 / 1042759 / 27419289484 | a box of pasta sauce | Classico Four Cheese Alfredo Pasta Sauce Jar (15 oz) | Acceptable | Incorrect |
| r128 / 1042759 / 27892354894 | a box of pasta sauce | Velveeta Original Microwavable Shells Pasta & Cheese Sauce Cups (2.39 oz x 4 ct) | Acceptable | Incorrect |
| r128 / 1042759 / 29461405036 | a box of pasta sauce | Prego Tomato Basil & Garlic Italian Pasta Sauce (24 oz) | Acceptable | Needs clarification |
| r128 / 24325284 / 23372596582 | a box of pasta sauce | Sauz Pasta Sauce Summer Lemon Marinara Pasta Sauce (25 oz) | Acceptable | Needs clarification |
| r128 / 24325284 / 5648960048 | a box of pasta sauce | Sprouts Pasta Sauce Garlic (25 oz) | Acceptable | Needs clarification |
| r128 / 35802549 / 30994838342 | a box of pasta sauce | Kroger Traditional Pasta Sauce (24 oz) | Acceptable | Needs clarification |
| r128 / 24325284 / 14040263051 | a box of pasta sauce | Sprouts Organic Pasta Sauce Garlic (25 oz) | Acceptable | Needs clarification |
| r128 / 29631686 / 22646326071 | a box of pasta sauce | Simply Nature Pasta Sauce (23.5 oz) | Acceptable | Needs clarification |
| r128 / 35802549 / 30936400674 | a box of pasta sauce | Kroger Marinara Pasta Sauce (24 oz) | Acceptable | Needs clarification |
| r129 / 35802549 / 30994848258 | 2 salmon fillets | Sea Cuisine Honey Chipotle Salmon Fillets (10.5 oz) | Incorrect | Needs clarification |
| r129 / 1742136 / 1000001363661147 | 2 salmon fillets | Temptations Lickable Spoons Tasty Chicken & Savory Salmon Puree Cat Treats (4 ct) | Acceptable | Incorrect |
| r129 / 1742136 / 1000032834131024 | 2 salmon fillets | Delectables Squeeze Up Tuna & Salmon Wet Cat Treat Tubes (4 ct) | Acceptable | Incorrect |
| r129 / 24325284 / 20931401195 | 2 salmon fillets | Farm Fresh Lemon Citrus Salmon (6 ct) | Acceptable | Incorrect |
| r129 / 24325284 / 24850263505 | 2 salmon fillets | The Better Fish Simply Skinless Barramundi Fillets (12 ct) | Acceptable | Incorrect |
| r129 / 24325284 / 34880224483 | 2 salmon fillets | Honey Smoked Fish co. Original Honey Smoked Salmon (6 ct) | Acceptable | Incorrect |
| r129 / 24325284 / 35926038346 | 2 salmon fillets | C.Wirthy & Co. Teriyaki Salmon (10 ct) | Acceptable | Incorrect |
| r129 / 29631686 / 36853168254 | 2 salmon fillets | Atlantic Salmon Portion Pack | Incorrect | Needs clarification |
| r130 / 24325284 / 1000001427175050 | 3 deli turkey breasts | Boar's Head Organic Oven Roasted Turkey Breast (6 ct) | Acceptable | Needs clarification |
| r130 / 24325284 / 10240894288 | 3 deli turkey breasts | Applegate Organic Smoked Turkey Breast (6 ct) | Acceptable | Needs clarification |
| r130 / 24325284 / 11730030077 | 3 deli turkey breasts | True Story Oven Roasted Turkey Breast (6 ct) | Acceptable | Needs clarification |
| r130 / 24325284 / 24339504656 | 3 deli turkey breasts | Sprouts Uncured Turkey Bacon (8 ct) | Acceptable | Incorrect |
| r130 / 24325284 / 24629999760 | 3 deli turkey breasts | Godshall's Organic Uncured Turkey Bacon (8 ct) | Acceptable | Incorrect |
| r130 / 24325284 / 25144241977 | 3 deli turkey breasts | Applegate Uncured Turkey Pepperoni (4 ct) | Acceptable | Incorrect |
| r130 / 1742136 / 14533930577 | 3 deli turkey breasts | Oscar Mayer Black Pepper Turkey Breast Deli Sliced Deli Meat (8 oz) | Incorrect | Needs clarification |
| r130 / 35802549 / 30994828615 | 3 deli turkey breasts | Oscar Mayer Black Pepper Turkey Breast Deli Sliced Deli Meat (8 oz) | Incorrect | Needs clarification |
| r130 / 35802549 / 30994828628 | 3 deli turkey breasts | Deli Fresh Turkey Breast Mega Pack | Acceptable | Needs clarification |
| r130 / 29631686 / 1000030409614581 | 3 deli turkey breasts | Lunch Mate Oven Roasted Turkey Breast (9 oz) | Incorrect | Needs clarification |
| r131 / 35802549 / 30994851727 | 100 ct granola bars | Chewy Granola Bars 100% Whole Grains Chocolate Chip Granola Bars (6.7 oz) | Incorrect | Needs clarification |
| r132 / 1742136 / 1000002709433016 | 1 lb sparkling water | Tehuacan Sparkling Natural Mineral Water (12 oz x 12 ct) | Incorrect | Needs clarification |
| r132 / 1742136 / 17453283494 | 1 lb sparkling water | Soleil Sparkling Water Original Cans (12 oz x 8 ct) | Incorrect | Needs clarification |
| r132 / 1742136 / 19704276460 | 1 lb sparkling water | Signature Select Strawberry Watermelon Flavored Sparkling Water Beverage Bottle (33.8 oz) | Incorrect | Needs clarification |
| r132 / 1742136 / 20704808982 | 1 lb sparkling water | Signature Select Peach Creme Sparkling Water Bottle (33.8 oz) | Incorrect | Needs clarification |
| r132 / 1742136 / 32390446339 | 1 lb sparkling water | Soleil Blood Orange Sparkling Water Cans (12 oz x 8 ct) | Incorrect | Needs clarification |
| r132 / 1742136 / 32390446368 | 1 lb sparkling water | Soleil Peach Sparkling Water Cans (12 oz x 8 ct) | Incorrect | Needs clarification |
| r132 / 29631686 / 42177046800 | 1 lb sparkling water | PurAqua Sparkling Frost Caffeine Strawberry Citrus Sparkling Water (16 oz) | Acceptable | Needs clarification |
| r138 / 29631686 / 41877836530 | 12 fl oz x 12 ct PurAqua Belle Vie Strawberry Sparkling Water Cans | PurAqua Belle Vie Lemon Sparkling Water Cans (12 fl oz x 12 ct) | Needs clarification | Incorrect |
| r138 / 29631686 / 41511254172 | 12 fl oz x 12 ct PurAqua Belle Vie Strawberry Sparkling Water Cans | PurAqua Belle Vie Lime Sparkling Water Cans (12 fl oz x 12 ct) | Needs clarification | Incorrect |
| r138 / 29631686 / 41877836529 | 12 fl oz x 12 ct PurAqua Belle Vie Strawberry Sparkling Water Cans | PurAqua Belle Vie Grapefruit Sparkling Water Cans (12 fl oz x 12 ct) | Needs clarification | Incorrect |
| r139 / 29631686 / 22646288070 | 29.75 oz Mama Cozzi Rising Crust Four Cheese Pizza, if you would | Mama Cozzi Rising Crust Pepperoni Pizza (30.2 oz) | Acceptable | Incorrect |
| r139 / 29631686 / 22646327844 | 29.75 oz Mama Cozzi Rising Crust Four Cheese Pizza, if you would | Mama Cozzi Stuffed Crust Cheese Pizza (30.4 oz) | Needs clarification | Incorrect |
| r141 / 29631686 / 1000030409614136 | 20 ct Pueblo Lindo Fajita Flour Tortillas please | Pueblo Lindo Fajita Flour Tortillas (23 oz) | Incorrect | Needs clarification |
| r141 / 29631686 / 1000032999710119 | 20 ct Pueblo Lindo Fajita Flour Tortillas please | Pueblo Lindo Flour Tortillas (17.5 oz) | Incorrect | Needs clarification |
| r142 / 29631686 / 1000040970948003 | a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda | Diet Coke Diet Cola Soda (12 fl oz x 12 ct) | Incorrect | Acceptable |
| r142 / 1042759 / 27734109846 | a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda | Diet Coke Soda Soft Drink Fridge Pack Cans (12 fl oz x 12 ct) | Incorrect | Acceptable |
| r142 / 1742136 / 9236580251 | a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda | Diet Coke Soda Soft Drink Fridge Pack Cans (12 fl oz x 12 ct) | Incorrect | Acceptable |
| r142 / 35802549 / 30994675255 | a 12 fl oz x 12 ct pack of Diet Coke Diet Cola Soda | Diet Coke Soda Soft Drink Fridge Pack Cans (12 fl oz x 12 ct) | Incorrect | Acceptable |
| r143 / 1742136 / 24507948329 | three pounds Honeycrisp apples | Organic Honeycrisp Apples (each) | Acceptable | Incorrect |
| r143 / 1742136 / 22747549348 | three pounds Honeycrisp apples | Honeycrisp Apple | Acceptable | Incorrect |
| r143 / 24325284 / 7935230420 | three pounds Honeycrisp apples | Organic Honeycrisp Apple (each) | Acceptable | Incorrect |
| r144 / 1042759 / 1000040270769002 | 5 oz can of tuna, any brand | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r144 / 1742136 / 18313620307 | 5 oz can of tuna, any brand | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r144 / 1042759 / 1000011054468004 | 5 oz can of tuna, any brand | Starkist Chunk Light Tuna in Oil Can (5 oz) | Incorrect | Acceptable |
| r144 / 35802549 / 1000013334011006 | 5 oz can of tuna, any brand | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r144 / 35802549 / 44208371799 | 5 oz can of tuna, any brand | Starkist Chunk Light Tuna in Water Can (5 oz) | Incorrect | Acceptable |
| r145 / 29631686 / 22646326552 | 12 oz frozen broccoli florets, any brand is fine | Broccoli Florets (12 oz) | Acceptable | Incorrect |
| r149 / 24325284 / 33881865907 | 16 oz honey ham | Sprouts Honey Ham (by pound) | Acceptable | Incorrect |
| r149 / 24325284 / 9507991311 | 16 oz honey ham | Sprouts Honey Ham Pre-Sliced Pack | Acceptable | Incorrect |
| r149 / 29631686 / 1000030409614589 | 16 oz honey ham | Lunch Mate Premium Honey Smoked Deli Sliced Ham (16 oz) | Needs clarification | Acceptable |
| r149 / 29631686 / 41448177281 | 16 oz honey ham | Lunch Mate Premium Honey Smoked Ham Value Pack (16 oz) | Needs clarification | Acceptable |
| r150 / 29631686 / 1000032999710139 | 15 oz Lunch Mate Lower Sodium Smoked Honey Ham | Lunch Mate Lower Sodium Oven Roasted Turkey (15 oz) | Acceptable | Incorrect |
| r151 / 29631686 / 22646303929 | a 12 fl oz x 12 ct case of La Croix Razz-Cranberry Sparkling Water | La Croix Razz-Cranberry Sparkling Water Cans (12 fl oz x 12 ct) | Incorrect | Acceptable |
| r151 / 24325284 / 21040431450 | a 12 fl oz x 12 ct case of La Croix Razz-Cranberry Sparkling Water | La Croix Sparkling Water Lime (12 oz x 12 ct) | Needs clarification | Incorrect |
| r153 / 29631686 / 1000033272212023 | 24 oz Reggano Roasted Garlic Pasta Sauce | Reggano Meat Pasta Sauce (24 oz) | Needs clarification | Incorrect |
| r153 / 29631686 / 22646325869 | 24 oz Reggano Roasted Garlic Pasta Sauce | Reggano Traditional Pasta Sauce (24 oz) | Needs clarification | Incorrect |
| r154 / 35802549 / 30994851727 | I need 100 ct of granola bars | Chewy Granola Bars 100% Whole Grains Chocolate Chip Granola Bars (6.7 oz) | Acceptable | Needs clarification |
| r154 / 1742136 / 25836986384 | I need 100 ct of granola bars | Chewy Granola Bars S'mores Granola Bars (0.84 oz x 8 ct) | Acceptable | Incorrect |
| r154 / 35802549 / 30994851726 | I need 100 ct of granola bars | Chewy Granola Bars S'mores Granola Bars (0.84 oz x 8 ct) | Acceptable | Incorrect |
| r154 / 1742136 / 25836986386 | I need 100 ct of granola bars | Chewy Granola Bars Peanut Butter Chocolate Chip Granola Bars (0.84 oz x 8 ct) | Acceptable | Incorrect |
| r154 / 35802549 / 30994851728 | I need 100 ct of granola bars | Chewy Granola Bars Peanut Butter Chocolate Chip Granola Bars (0.84 oz x 8 ct) | Acceptable | Incorrect |
| r154 / 1742136 / 23598313944 | I need 100 ct of granola bars | Quaker Oats Chewy Granola Bars Big Chocolate Chip Granola Bars (1.48 oz x 5 ct) | Acceptable | Incorrect |
| r154 / 1042759 / 10199849891 | I need 100 ct of granola bars | Nature Valley Crunchy Oats 'n Honey Granola Bars Pouches (1.49 oz x 6 ct) | Acceptable | Incorrect |
| r154 / 1042759 / 12649276025 | I need 100 ct of granola bars | Nature Valley Sweet & Salty Nut Peanut Granola Bars (1.2 oz x 6 ct) | Acceptable | Incorrect |
| r154 / 1042759 / 15040347666 | I need 100 ct of granola bars | Chewy Granola Bars Variety Pack (0.84 oz x 18 ct) | Acceptable | Incorrect |
| r154 / 1042759 / 26047649087 | I need 100 ct of granola bars | Chewy Chocolate Chip Granola Bars Value Pack (0.84 oz x 18 ct) | Acceptable | Incorrect |
| r154 / 1042759 / 26461382000 | I need 100 ct of granola bars | Chewy Granola Bars Dipps Covered Chocolate Chip Granola Bars (1.09 oz x 6 ct) | Acceptable | Incorrect |
