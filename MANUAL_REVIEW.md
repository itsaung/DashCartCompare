# Manual Review — Checkpoint 1/2 sample verification

20 products per store, sampled with a fixed seed (20260916) from `normalized_catalog.csv`. Rows start as `unreviewed` and only change when `record_decision()` is actually called -- this file does not manufacture "OK" for rows nobody has checked. `source_url` is the live DoorDash product page, checked independently of this project's own stored data, not just re-reading the CSV back at itself.

| Store | Product ID | Title | Price | Size | Status | Notes |
|---|---|---|---:|---|---|---|
| ALDI | 1000030409614345 | Cosmic Crisp Apples Bag (2 lb) | $3.89 | 2 lb | unreviewed |  |
| ALDI | 22646305662 | Bake Shop Raspberry Strip Danish (14 oz) | $3.99 | 14 oz | verified | Live re-fetch of Bakery category (2026-09-16): name and price match exactly ($3.99, Bake Shop Raspberry Strip Danish 14 oz). |
| ALDI | 1000030409614372 | Simply Nature Benner Organic Mixed Greens (5 oz) | $2.65 | 5 oz | unreviewed |  |
| ALDI | 1000030409614529 | Stonemill Spice Mill | $1.89 | (none) | unreviewed |  |
| ALDI | 1000042024938204 | Specially Selected Assorted Salami, Pepper Coated  | $4.99 | 8 oz | unreviewed |  |
| ALDI | 1000030409614546 | Little Salad Bar Italian Salad | $3.29 | (none) | unreviewed |  |
| ALDI | 22646303714 | El Mexicano Queso Fresco Casero (14 oz) | $4.89 | 14 oz | unreviewed |  |
| ALDI | 1000035806129002 | Power Force Liquid Dish Detergent (75 fl oz) | $6.89 | 75 fl oz | unreviewed |  |
| ALDI | 22646326115 | Earthly Grains Couscous Mix Roasted Garlic & Olive | $1.99 | 5.8 oz | unreviewed |  |
| ALDI | 1000030409614219 | Appetitos Mozzarella Cheese Sticks (11 oz) | $3.39 | 11 oz | verified | Live re-fetch of Frozen category (2026-09-16): name and price match exactly ($3.39, Appetitos Mozzarella Cheese Sticks 11 oz). |
| ALDI | 1000030409614417 | Park Street Deli Medium Fresh Cut Salsa | $2.89 | (none) | unreviewed |  |
| ALDI | 1000033990923001 | Stonemill Assorted Bagel Seasoning Salt Free (2.4  | $1.99 | 2.4 oz | unreviewed |  |
| ALDI | 1000038340833322 | Crane Football | $10.49 | (none) | unreviewed |  |
| ALDI | 1000030409614326 | Cilantro (bunch) | $0.84 | bunch | verified | Live re-fetch of Produce category (2026-09-16): name and price match exactly ($0.84, Cilantro bunch). |
| ALDI | 1000032999710019 | Simply Nature Organic Maple Brown Sugar Instant Oa | $2.89 | 11.29 oz | unreviewed |  |
| ALDI | 1000030409614092 | Sweet Harvest Peach Slices in Heavy Syrup (15.25 o | $1.79 | 15.25 oz | unreviewed |  |
| ALDI | 22646325978 | Dakota's Pride Pinto Beans (30 oz) | $1.89 | 30 oz | unreviewed |  |
| ALDI | 22646327115 | Elevation by Millville Maxx Bar Blueberry (4 ct) | $5.79 | 4 ct | unreviewed |  |
| ALDI | 1000030409614012 | Simply Nature Avocado Oil (17 oz) | $8.99 | 17 oz | unreviewed |  |
| ALDI | 1000030409614030 | Tuscan Garden Ranch Dressing Dressing and Dip (36  | $4.39 | 36 fl oz | unreviewed |  |
| DashMart | 41033426281 | Signature Select Black Beans (15 oz) | $1.79 | 15 oz | unreviewed |  |
| DashMart | 8776541321 | Auntie Anne's All Beef Classic Pretzel Dogs (4 ct) | $10.39 | 4 ct | unreviewed |  |
| DashMart | 27211830562 | Birds Eye Steamfresh Frozen Broccoli Florets (10.8 | $3.89 | 10.8 oz | unreviewed |  |
| DashMart | 32409646179 | Essentia Water Ionized Alkaline Water (1.5 L) | $4.29 | 1.5 L | unreviewed |  |
| DashMart | 8776503172 | Banza Gluten Free Chickpea Penne Pasta (8 oz) | $7.59 | 8 oz | unreviewed |  |
| DashMart | 38789557429 | Jeni's Gooey Butter Cake Ice Cream (1 pt) | $11.39 | 1 pt | unreviewed |  |
| DashMart | 37178292465 | Signature Select Strawberry Jelly (18 oz) | $4.69 | 18 oz | unreviewed |  |
| DashMart | 41243690353 | Signature Kitchen Frozen Red Green & Yellow Pepper | $3.69 | 14 oz | unreviewed |  |
| DashMart | 8776502941 | Campbell's Condensed Cream of Chicken Soup (10.5 o | $3.29 | 10.5 oz | unreviewed |  |
| DashMart | 8776509780 | Halls Cough & Throat Relief Mentho-Lyptus Cough Dr | $5.19 | 30 ct | unreviewed |  |
| DashMart | 10547898695 | Roma Tomato (1 ea) | $0.89 | 1 ea | verified | Live re-fetch of Produce category (2026-09-16): name and price match exactly ($0.89, Roma Tomato 1 ea). |
| DashMart | 8776509757 | Mucinex Maximum Strength 12-Hour Chest Congestion  | $17.89 | 14 ct | unreviewed |  |
| DashMart | 42635532583 | Rap Snacks Rick Ross Lemon Pepper Chicken Flavor R | $2.19 | 2.25 oz | unreviewed |  |
| DashMart | 33161426245 | CVS Health Nausea Relief Cherry Flavor Liquid (4 f | $8.59 | 4 fl oz | unreviewed |  |
| DashMart | 8816075624 | Nesquik Low Fat Strawberry Flavored Milk Bottle (1 | $2.29 | 14 fl oz | unreviewed |  |
| DashMart | 38787096399 | Jet Puffed Marshmallow Creme (7 oz) | $4.29 | 7 oz | unreviewed |  |
| DashMart | 32298403941 | Neutrogena Ultra Soft Makeup Remover Cleansing Wip | $22.09 | 2 pk x 25 ct | unreviewed |  |
| DashMart | 9816839246 | Glacéau Smartwater Vapor Distilled Water (33.8 fl  | $23.19 | 33.8 fl oz x 6 ct | unreviewed |  |
| DashMart | 20202953508 | Grillo's Dill Pickle Chips (16 fl oz) | $8.49 | 16 fl oz | unreviewed |  |
| DashMart | 36550292878 | One+Other Nail Clipper Duo | $6.99 | (none) | unreviewed |  |
| Ralphs | 30994833724 | Band-Aid Tough Strips Extra Large Adhesive Bandage | $7.59 | 10 ct | unreviewed |  |
| Ralphs | 30819681214 | Kozy Shack Gluten Free Original Recipe Rice Puddin | $6.29 | 22 oz | unreviewed |  |
| Ralphs | 30994842704 | Temptations Creamy Dairy Flavor Cat Treats (6.3 oz | $5.19 | 6.3 oz | unreviewed |  |
| Ralphs | 30994826369 | Banquet Apple Pie (7 oz) | $1.99 | 7 oz | unreviewed |  |
| Ralphs | 30994662966 | Huggies Natural Care Unscented Fragrance Free & Se | $9.79 | 184 ct | unreviewed |  |
| Ralphs | 31447232884 | Albanese Candy Gluten Free Berry Flavored Gummi Be | $4.99 | 9 oz | unreviewed |  |
| Ralphs | 40125380549 | Duffy's Artisan Sandwich Roll (12 oz) | $4.89 | 12 oz | unreviewed |  |
| Ralphs | 30994838612 | Kroger No Sugar Added Yellow Cling Sliced Peaches  | $2.89 | 14.5 oz | unreviewed |  |
| Ralphs | 30994663287 | Enfamil Nutramigen 0-12 Months Hypoallergenic Infa | $74.99 | 19.8 oz | unreviewed |  |
| Ralphs | 30994841613 | Barilla Rotini Pasta (16 oz) | $2.29 | 16 oz | unreviewed |  |
| Ralphs | 31447233822 | Purina Tidy Cats 24/7 Performance Continuous Odor  | $25.29 | 35 lb | unreviewed |  |
| Ralphs | 30994828838 | Kroger Soft & Strong Toilet Paper Mega Roll Big De | $23.19 | 30 ct | unreviewed |  |
| Ralphs | 37923852316 | Vigo Saffron Yellow Rice (10 oz) | $3.69 | 10 oz | unreviewed |  |
| Ralphs | 31447193556 | Guerrero Sonora Style Burrito Flour Tortillas (8 c | $5.39 | 8 ct | unreviewed |  |
| Ralphs | 30994836353 | Old Spice Deodorant Aluminum-Free Men Deep Sea wit | $10.99 | 3 oz | unreviewed |  |
| Ralphs | 30994851326 | La Mexicana Pico de Gallo (16 oz) | $7.49 | 16 oz | unreviewed |  |
| Ralphs | 30994833617 | Halls Honey Lemon Flavor Cough & Throat Relief Dro | $7.59 | 80 ct | unreviewed |  |
| Ralphs | 1000013611094004 | Yoo-hoo Chocolate Drink Boxes (6.5 fl oz x 10 ct) | $4.99 | 6.5 fl oz x 10 ct | verified | Live re-fetch of Dairy & Eggs category (2026-09-16): name and price match exactly ($4.99, Yoo-hoo Chocolate Drink Boxes 6.5 fl oz x 10 ct). |
| Ralphs | 30994828207 | Ripple Kids Plant Based Original Unsweetened Milk  | $7.29 | 48 oz | unreviewed |  |
| Ralphs | 30994674093 | Mini White Cupcake (12 ct) | $5.39 | 12 ct | unreviewed |  |
| Sprouts | 43681990206 | Solely Organic Mango & Passionfruit Fruit Jerky (0 | $1.79 | 0.8 oz | unreviewed |  |
| Sprouts | 18101338114 | Bluebonnet Triple Boron Vcaps 3 Mg (90 ct) | $14.99 | 90 ct | unreviewed |  |
| Sprouts | 44214036894 | Sea-el Miracle Kelp Eye Cream (1 oz) | $28.49 | 1 oz | unreviewed |  |
| Sprouts | 38945336765 | Just Ingredients Strawberry Limeade Clear Protein  | $3.49 | 16 fl oz | unreviewed |  |
| Sprouts | 10290662140 | Nasoya Plant-Based Korean BBQ Steak (7 oz) | $7.99 | 7 oz | unreviewed |  |
| Sprouts | 39184285664 | Cora Organic Cotton Tampons Multipack (32 ct) | $18.29 | 32 ct | unreviewed |  |
| Sprouts | 1000038684335002 | Oh Snap! Pure Dillys Dill Pickle Snacking Chips (3 | $2.29 | 3.25 oz | unreviewed |  |
| Sprouts | 7182185006 | Belgioioso Grated Parmesan Cheese Cup (5 oz) | $6.19 | 5 oz | unreviewed |  |
| Sprouts | 9952216249 | Modelo Especial Pilsner Cans (12 oz x 12 ct) | $15.99 | 12 oz x 12 ct | unreviewed |  |
| Sprouts | 21647761185 | Traditional Medicinals Organic Nettle Leaf Tea Bag | $7.49 | 16 ct | unreviewed |  |
| Sprouts | 44182213764 | Organic Pitted Prunes PLU #6638 (by pound) | $9.99 | by pound | unreviewed |  |
| Sprouts | 15053558127 | Aura Cacia Pure Relaxing Essential Oil Lavender (0 | $15.39 | 0.5 oz | unreviewed |  |
| Sprouts | 43856595185 | Simple Mills Soft Baked Almond Flour Bars Nutty Ba | $6.49 | 1.19 oz x 5 ct | unreviewed |  |
| Sprouts | 37746776021 | Stellar Snacks Simply Stellar Pretzel Braids Origi | $6.89 | 12 oz | unreviewed |  |
| Sprouts | 10175231026 | Lifeaid Beverage Co FocusAid Melon Mate Energy Dri | $3.49 | 12 oz | unreviewed |  |
| Sprouts | 9713815209 | Earthbound Farm Organic Broccolette | $3.99 | (none) | unreviewed |  |
| Sprouts | 1000014101629011 | Smart Sweets Gummy Worms (1.8 oz) | $4.59 | 1.8 oz | verified | Live re-fetch of Candy category (2026-09-16): name and price match exactly ($4.59, Smart Sweets Gummy Worms 1.8 oz). |
| Sprouts | 29069063166 | Sprouts Keto Garlic Parmesan Cauliflower Rice (1 ( | $12.59 | $12.59/lb | unreviewed |  |
| Sprouts | 9165097970 | Sprouts Organic Grade A Large Brown Eggs (12 ct) | $5.49 | 12 ct | unreviewed |  |
| Sprouts | 21755699271 | Makoto Dressing Honey Ginger (9 fl oz) | $4.99 | 9 fl oz | unreviewed |  |
| Vons | 10109272023 | Rockstar Original Energy Drink (16 fl oz) | $2.39 | 16 fl oz | unreviewed |  |
| Vons | 9706264925 | Jim Beam Kentucky Straight Bourbon Whiskey (1.75 L | $20.69 | 1.75 L | unreviewed |  |
| Vons | 10109210439 | Pillsbury Chocolate Chip Cookie Dough (16.5 oz) | $4.69 | 16.5 oz | unreviewed |  |
| Vons | 27124150933 | Old El Paso Carb Advantage Crunchy Taco Shells (4. | $6.39 | 4.6 oz | unreviewed |  |
| Vons | 17610022912 | Signature Select Pork Luncheon Meat (12 oz) | $5.19 | 12 oz | unreviewed |  |
| Vons | 17585440593 | Starbucks Pike Place Medium Roast Whole Bean Coffe | $19.69 | 18 oz | unreviewed |  |
| Vons | 9336386390 | Signature Select Colombia Medium Roast Ground Coff | $31.29 | 32 oz | unreviewed |  |
| Vons | 9876969962 | Nature's Truth Gluten Free Vegan 600 mg Apple Cide | $17.39 | 75 ct | unreviewed |  |
| Vons | 10109279042 | Arm & Hammer Double Duty Clumping Cat Litter (20 l | $14.99 | 20 lb | unreviewed |  |
| Vons | 9336387030 | Signature Care Women Shave Gel Moisturizing (7 oz) | $4.69 | 7 oz | unreviewed |  |
| Vons | 17110579258 | Outshine No Sugar Added Strawberry Tangerine & Ras | $7.59 | 18 oz | unreviewed |  |
| Vons | 29703840667 | Skyn Elite Condoms (10 ct) | $17.39 | 10 ct | unreviewed |  |
| Vons | 17585440597 | Starbucks Blonde Roast Veranda Blend Coffee Capsul | $16.19 | 8 ct | unreviewed |  |
| Vons | 23206657638 | Gatorade Thirst Quencher Fruit Punch Natural Flavo | $3.49 | 28 fl oz | unreviewed |  |
| Vons | 9741813990 | Purina Tidy Cats x Glade Clear Springs Clumping Mu | $13.89 | 20 lb | unreviewed |  |
| Vons | 1000023462504245 | Readymeals Roast Beef & Cheddar Bistro Sliders (9. | $10.39 | 9.5 oz | unreviewed |  |
| Vons | 25156882084 | First Response Early Result Pregnancy Tests (3 ct) | $28.89 | 3 ct | unreviewed |  |
| Vons | 1000001955462038 | Overjoyed Boutique Artisan Rose Arrangement | $19.69 | (none) | verified | Live re-fetch of Flowers & Plants category (2026-09-16): name and price match exactly ($19.69, Overjoyed Boutique Artisan Rose Arrangement). |
| Vons | 21423431567 | USDA Choice Beef Petite Sirloin Steak Value Pack | $34.97 | $9.99/lb | unreviewed |  |
| Vons | 12124901890 | Horizon Organic Half & Half Carton (1 qt) | $7.99 | 1 qt | unreviewed |  |

## Status: 7 verified, 0 discrepancy, 93 unreviewed (of 100)

Discrepancies, if any, are recorded with their `expected` values in `manual_review_decisions.json` (source of truth for review state; this file is a rendered view of it).