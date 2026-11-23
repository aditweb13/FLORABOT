"""
Curated FloraBOT Botanical Knowledge Base Seed Data.
Real, scientifically accurate horticultural and phytopathological reference data.
"""

KNOWLEDGE_SEED_ENTRIES = [
    {
        "title": "Monstera deliciosa (Swiss Cheese Plant) Care Profile",
        "category": "indoor_plants",
        "plant_species": "Monstera deliciosa",
        "disease_name": "",
        "summary": "Popular tropical climbing epiphyte known for dramatic fenestrated leaves. Thrives in medium to bright indirect sunlight.",
        "details_markdown": """### Botanical Overview
Monstera deliciosa is native to the tropical rainforests of southern Mexico. It climbs host trees via aerial roots and features broad, fenestrated (perforated) foliage.

### Light Requirements
Bright, indirect sunlight. Avoid intense direct afternoon sun which scorches foliage. Survives in medium light but fenestration may reduce.

### Watering & Soil
Water thoroughly once the top 2–3 inches (5–7 cm) of potting mix have dried out. Sensitive to wet feet; use an aroid mix rich in orchid bark, perlite, peat, and compost.

### Humidity & Temperature
Prefers 60%+ relative humidity and temperatures between 18°C and 29°C (65°F–85°F). Keep away from cold air drafts and heating vents.
""",
        "care_data_json": '{"light": "Bright indirect light", "water": "Allow top 2-3 inches to dry", "humidity": "60%+", "soil": "Aroid mix with bark and perlite", "temperature": "18-29°C"}',
        "treatment_plan": "",
        "prevention_tips": "Dust leaves regularly with a damp microfiber cloth to maximize photosynthesis and discourage spider mites.",
        "source_name": "Royal Horticultural Society (RHS) Plant Finder",
        "source_url": "https://www.rhs.org.uk/plants/monstera/growing-guide"
    },
    {
        "title": "Epipremnum aureum (Golden Pothos) Care Profile",
        "category": "indoor_plants",
        "plant_species": "Epipremnum aureum",
        "disease_name": "",
        "summary": "Resilient trailing vine with heart-shaped leaves, tolerant of diverse indoor conditions and low light.",
        "details_markdown": """### Botanical Overview
Golden Pothos is one of the most forgiving indoor plants. It features variegated green and gold leaves on vigorous climbing or cascading stems.

### Light Requirements
Low to bright indirect light. Variegation becomes more prominent under brighter indirect light.

### Watering & Soil
Water every 1–2 weeks, allowing soil to dry out almost completely between waterings. Leaves will droop slightly to signal thirst and recover rapidly once hydrated.

### Care Warning
Toxic to cats and dogs if ingested due to insoluble calcium oxalate crystals.
""",
        "care_data_json": '{"light": "Low to bright indirect", "water": "Dry out between waterings", "humidity": "40-60%", "soil": "Standard peat-based potting soil", "temperature": "15-30°C"}',
        "treatment_plan": "",
        "prevention_tips": "Avoid water accumulation in cachepots; ensure drainage holes are free-flowing.",
        "source_name": "University of Florida IFAS Extension",
        "source_url": "https://edis.ifas.ufl.edu/publication/ep256"
    },
    {
        "title": "Spathiphyllum (Peace Lily) Care Profile",
        "category": "indoor_plants",
        "plant_species": "Spathiphyllum wallisii",
        "disease_name": "",
        "summary": "Graceful flowering indoor plant known for glossy leaves, white spathes, and clear visual signaling when water is needed.",
        "details_markdown": """### Botanical Overview
Peace Lilies are tropical perennials that produce elegant white spathes. They are famous for dramatically drooping when moisture is low, making them excellent indicators for watering.

### Light & Moisture
Prefers low to moderate indirect light. Keep soil consistently lightly moist, never completely desiccated or waterlogged. Sensitive to fluoride and chlorine in tap water; use filtered or resting water if tip browning occurs.
""",
        "care_data_json": '{"light": "Low to medium indirect", "water": "Consistent light moisture", "humidity": "50%+", "soil": "Rich organic soil with perlite", "temperature": "18-27°C"}',
        "treatment_plan": "",
        "prevention_tips": "Wipe leaves gently and trim spent flower stalks at the base.",
        "source_name": "Missouri Botanical Garden Plant Finder",
        "source_url": "https://www.missouribotanicalgarden.org/PlantFinder/PlantFinderDetails.aspx?taxonid=276203"
    },
    {
        "title": "Sansevieria trifasciata (Snake Plant / Dracaena trifasciata)",
        "category": "indoor_plants",
        "plant_species": "Dracaena trifasciata",
        "disease_name": "",
        "summary": "Architectural succulent perennial with upright sword-like foliage, remarkably drought-hardy.",
        "details_markdown": """### Botanical Overview
Native to tropical West Africa, the Snake Plant uses Crassulacean Acid Metabolism (CAM) to conserve water. It can tolerate weeks of neglect.

### Watering Rules
Water very sparingly—only when soil is 100% dry down to the bottom of the pot. Overwatering is the primary cause of decline (leading to soft, mushy leaf bases and root rot).
""",
        "care_data_json": '{"light": "Any light from low to full sun", "water": "Dry completely (every 2-4 weeks)", "humidity": "Low to medium (30-50%)", "soil": "Gritty succulent/cactus mix", "temperature": "15-32°C"}',
        "treatment_plan": "",
        "prevention_tips": "Plant in unglazed terracotta containers with drainage holes to facilitate soil aeration.",
        "source_name": "University of Minnesota Extension",
        "source_url": "https://extension.umn.edu/houseplants/snake-plant"
    },
    {
        "title": "Root Rot (Pythium, Phytophthora, Fusarium spp.) Diagnosis & Treatment",
        "category": "diseases",
        "plant_species": "",
        "disease_name": "Root Rot",
        "summary": "Fungal/oomycete disease caused by stagnant moisture and oxygen starvation in the root system.",
        "details_markdown": """### Etiology & Pathogenesis
Root rot occurs when soil remains saturated, depriving roots of oxygen. Opportunistic pathogens invade the suffocating root tissues, turning them dark brown, mushy, and foul-smelling. Above ground, leaves droop, turn dull yellow, and shed prematurely.

### Visible Symptoms
- Progressive yellowing of lower leaves.
- Wilting despite wet potting substrate.
- Soft, water-soaked petioles at soil level.
- Roots pull apart easily with dark cortex sloughing off.

### Remediation Protocol
1. Unpot the plant immediately and rinse root system clean of old substrate.
2. Using sterile shears, excise all blackened or mushy roots until only firm, healthy white/tan tissue remains.
3. Submerge remaining roots in a diluted 3% hydrogen peroxide solution (1 part H2O2 to 4 parts water) for 5 minutes.
4. Repot in a clean pot with fresh, sterile, porous potting mix containing perlite and bark.
5. Withhold fertilizer for 4 weeks while root hairs regenerate.
""",
        "care_data_json": '{"environmental_factor": "Poor drainage, overwatering, heavy compacted substrate"}',
        "treatment_plan": "Unpot plant, trim necrotic roots with sterile shears, dip in mild hydrogen peroxide dilution, and repot in fresh airy substrate.",
        "prevention_tips": "Always use containers with drainage holes. Never let pots stand in drainage runoff saucers for longer than 20 minutes.",
        "source_name": "Penn State Extension Plant Disease Management",
        "source_url": "https://extension.psu.edu/root-rot-of-houseplants"
    },
    {
        "title": "Leaf Spot & Chlorosis Syndrome (Fungal & Environmental)",
        "category": "diseases",
        "plant_species": "",
        "disease_name": "Leaf Spot / Chlorosis Syndrome",
        "summary": "Localized leaf discoloration, yellow halos, or brown necrotic lesions caused by fungal spore germination or environmental moisture imbalance.",
        "details_markdown": """### Identification & Causes
Fungal leaf spots (Alternaria, Cercospora, Colletotrichum) develop when water sits on leaves for extended periods in stagnant air. Discoloration may also reflect iron or magnesium chlorosis when potting pH locks out micronutrients.

### Treatment
- Remove individual severely affected leaves to reduce spore pressure.
- For fungal lesions, apply an organic copper soap fungicide or biofungicide (Bacillus subtilis).
- For nutrient chlorosis, apply a balanced micronutrient chelate fertilizer at half strength.
- Keep leaves completely dry during watering.
""",
        "care_data_json": '{"environmental_factor": "High canopy humidity, overhead wetting, stagnant air"}',
        "treatment_plan": "Prune severely affected leaves. Apply broad-spectrum copper fungicide or neem oil spray. Avoid overhead watering.",
        "prevention_tips": "Increase room ventilation with a gentle circulating fan. Always water the soil surface, not the leaves.",
        "source_name": "UC IPM - Fungal Leaf Spot Management",
        "source_url": "https://ipm.ucanr.edu/PMG/GARDEN/PLANTS/DISEASES/leafspots.html"
    },
    {
        "title": "Powdery Mildew (Erysiphaceae) Guide",
        "category": "diseases",
        "plant_species": "",
        "disease_name": "Powdery Mildew",
        "summary": "Superficial fungal infection producing distinctive white or pale-gray powdery talc-like patches on foliage.",
        "details_markdown": """### Symptoms
White powdery fungal colonies spreading across leaf upper surfaces, buds, and young stems. Foliage may curl, yellow, and drop prematurely.

### Treatment
1. Isolate the plant from other houseplants immediately.
2. Wipe visible colonies with a solution of 1 teaspoon baking soda and 1/2 teaspoon horticultural oil in 1 quart of warm water.
3. Apply sulfur dust or neem oil emulsion every 7 days until clear.
""",
        "care_data_json": '{"environmental_factor": "Moderate temperatures (15-27°C) and high relative humidity without free water on leaves"}',
        "treatment_plan": "Apply potassium bicarbonate, neem oil, or sulfur-based organic fungicide. Improve ventilation.",
        "prevention_tips": "Provide ample spacing between plants to prevent stagnant microclimates around foliage.",
        "source_name": "Cornell University Plant Disease Diagnostic Clinic",
        "source_url": "http://plantclinic.cornell.edu/factsheets/powderymildew.pdf"
    },
    {
        "title": "Visual Wilting vs Overwatering Diagnostic Guide",
        "category": "care_guides",
        "plant_species": "",
        "disease_name": "Moisture / Root Stress",
        "summary": "How to accurately distinguish thirst-induced leaf droop from root-rot induced wilting in indoor plants.",
        "details_markdown": """### The Wilting Paradox
Both under-hydrated plants and severely over-hydrated plants display drooping, limp leaves.
- **Underwatering Wilting**: Pot feels exceptionally lightweight. Soil shrinks away from the pot rim. Foliage feels papery, crispy at tips. Recovers rapidly (within 4–8 hours) after bottom-watering.
- **Overwatering Wilting**: Pot feels heavy. Soil is damp or soggy. Leaves feel limp and soft/rubbery rather than crispy. Yellowing often starts on lower leaves. Petioles may detach easily. Adding more water will be fatal.

### Diagnostic Rule of Thumb
Always test soil moisture 2 inches below the surface before making a watering decision.
""",
        "care_data_json": '{"diagnostic_key": "Weight of container + probe moisture depth"}',
        "treatment_plan": "Assess soil moisture depth. Water if dry; aerate and dry out if wet.",
        "prevention_tips": "Check plant weight when fully watered versus dry to develop an intuitive feel for hydration status.",
        "source_name": "FloraBOT Botanical Diagnostics Manual",
        "source_url": "https://florabot.local/knowledge/wilting-guide"
    }
]
