"""
CivicMind — Synthetic Data Seed Script
=======================================
Generates all synthetic data deterministically (seeded RNG).
Run: python data/seed.py

Generates:
  1. SQLite database with civic records (respiratory complaints, transit metrics, waste sensors)
  2. Unstructured text documents (citizen complaints, meeting minutes, news articles)
  3. Photo metadata JSON sidecars (photos themselves are placed manually or generated)

All data tells one consistent story:
  - Riverside neighborhood has rising respiratory complaints
  - Bus Route 14 (serving Riverside) has worsening congestion/delays
  - Air quality near Route 14 corridor is degrading
  - Several citizen complaints and news articles mention both issues
"""

import os
import sys
import json
import random
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

# Deterministic seed
SEED = 42
random.seed(SEED)

# Paths
BASE_DIR = Path(__file__).parent
STRUCTURED_DIR = BASE_DIR / "structured"
UNSTRUCTURED_DIR = BASE_DIR / "unstructured"
COMPLAINTS_DIR = UNSTRUCTURED_DIR / "complaints"
MINUTES_DIR = UNSTRUCTURED_DIR / "meeting_minutes"
NEWS_DIR = UNSTRUCTURED_DIR / "news"
PHOTOS_DIR = BASE_DIR / "photos"
CHROMADB_DIR = BASE_DIR / "chromadb"

DB_PATH = STRUCTURED_DIR / "civic_records.db"

# --- Configuration ---
NEIGHBORHOODS = ["Riverside", "Downtown", "Greenfield", "Lakeside", "Hilltop"]
BUS_ROUTES = [
    ("RT-14", "Route 14 - Riverside Express"),
    ("RT-07", "Route 7 - Downtown Loop"),
    ("RT-21", "Route 21 - Lakeside Connector"),
    ("RT-03", "Route 3 - Greenfield Shuttle"),
    ("RT-11", "Route 11 - Hilltop Line"),
    ("RT-09", "Route 9 - Cross-City Express"),
    ("RT-16", "Route 16 - University Circle"),
    ("RT-22", "Route 22 - Industrial Corridor"),
]

# Date range: 6 months of daily data
END_DATE = datetime(2026, 6, 30)
START_DATE = END_DATE - timedelta(days=180)

# ============================================================
# 1. STRUCTURED DATA — SQLite
# ============================================================

def generate_structured_data():
    """Generate SQLite database with 3 tables of civic records."""
    STRUCTURED_DIR.mkdir(parents=True, exist_ok=True)

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # --- respiratory_complaints ---
    cur.execute("""
        CREATE TABLE respiratory_complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            neighborhood TEXT NOT NULL,
            complaint_count INTEGER NOT NULL,
            avg_aqi REAL NOT NULL,
            dominant_pollutant TEXT NOT NULL
        )
    """)

    pollutants = ["PM2.5", "PM10", "O3", "NO2", "SO2"]
    date = START_DATE
    while date <= END_DATE:
        for hood in NEIGHBORHOODS:
            day_offset = (date - START_DATE).days

            if hood == "Riverside":
                # Rising trend — starts ~5, ends ~25+ with noise
                base = 5 + (day_offset / 180) * 20
                noise = random.gauss(0, 3)
                count = max(0, int(base + noise))
                aqi = 80 + (day_offset / 180) * 70 + random.gauss(0, 10)
                pollutant = random.choices(["PM2.5", "NO2", "PM10"], weights=[0.6, 0.3, 0.1])[0]
            elif hood == "Downtown":
                # Moderate, stable
                count = max(0, int(random.gauss(8, 2)))
                aqi = random.gauss(65, 8)
                pollutant = random.choice(["PM2.5", "O3", "NO2"])
            elif hood == "Hilltop":
                # Slight upward (spillover from Riverside)
                base = 3 + (day_offset / 180) * 5
                count = max(0, int(base + random.gauss(0, 1.5)))
                aqi = 50 + (day_offset / 180) * 20 + random.gauss(0, 5)
                pollutant = random.choice(pollutants)
            else:
                # Stable, low
                count = max(0, int(random.gauss(3, 1.5)))
                aqi = random.gauss(45, 7)
                pollutant = random.choice(pollutants)

            aqi = max(20, min(300, round(aqi, 1)))
            cur.execute(
                "INSERT INTO respiratory_complaints (date, neighborhood, complaint_count, avg_aqi, dominant_pollutant) VALUES (?, ?, ?, ?, ?)",
                (date.strftime("%Y-%m-%d"), hood, count, aqi, pollutant)
            )
        date += timedelta(days=1)

    # --- transit_metrics ---
    cur.execute("""
        CREATE TABLE transit_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            route_id TEXT NOT NULL,
            route_name TEXT NOT NULL,
            ridership INTEGER NOT NULL,
            avg_delay_minutes REAL NOT NULL,
            congestion_score REAL NOT NULL
        )
    """)

    date = START_DATE
    while date <= END_DATE:
        for route_id, route_name in BUS_ROUTES:
            day_offset = (date - START_DATE).days
            day_of_week = date.weekday()
            weekend_factor = 0.6 if day_of_week >= 5 else 1.0

            if route_id == "RT-14":
                # Route 14 — worsening delays, high ridership
                ridership = int((2800 + random.gauss(0, 200)) * weekend_factor)
                delay = 4 + (day_offset / 180) * 12 + random.gauss(0, 2)
                congestion = 0.4 + (day_offset / 180) * 0.5 + random.gauss(0, 0.05)
            elif route_id == "RT-07":
                ridership = int((3500 + random.gauss(0, 300)) * weekend_factor)
                delay = random.gauss(5, 1.5)
                congestion = random.gauss(0.5, 0.08)
            else:
                ridership = int((1500 + random.gauss(0, 250)) * weekend_factor)
                delay = random.gauss(3, 1)
                congestion = random.gauss(0.3, 0.06)

            ridership = max(200, ridership)
            delay = max(0, round(delay, 1))
            congestion = max(0.05, min(1.0, round(congestion, 2)))

            cur.execute(
                "INSERT INTO transit_metrics (date, route_id, route_name, ridership, avg_delay_minutes, congestion_score) VALUES (?, ?, ?, ?, ?, ?)",
                (date.strftime("%Y-%m-%d"), route_id, route_name, ridership, delay, congestion)
            )
        date += timedelta(days=1)

    # --- waste_sensors ---
    cur.execute("""
        CREATE TABLE waste_sensors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            bin_id TEXT NOT NULL,
            neighborhood TEXT NOT NULL,
            fill_percentage REAL NOT NULL,
            last_collected TEXT NOT NULL
        )
    """)

    bin_ids = {hood: [f"BIN-{hood[:3].upper()}-{i:03d}" for i in range(1, 6)] for hood in NEIGHBORHOODS}

    date = START_DATE
    while date <= END_DATE:
        for hood in NEIGHBORHOODS:
            for bin_id in bin_ids[hood]:
                day_offset = (date - START_DATE).days
                # Bins fill up over 5-7 days, get collected, reset
                cycle = (day_offset + hash(bin_id) % 7) % 7
                fill = min(100, max(5, (cycle / 6) * 85 + random.gauss(0, 8)))

                if hood == "Riverside" and day_offset > 120:
                    # Waste collection disrupted in Riverside late in dataset
                    fill = min(100, fill + 15)

                last_collected = date - timedelta(days=cycle)
                cur.execute(
                    "INSERT INTO waste_sensors (date, bin_id, neighborhood, fill_percentage, last_collected) VALUES (?, ?, ?, ?, ?)",
                    (date.strftime("%Y-%m-%d"), bin_id, hood, round(fill, 1), last_collected.strftime("%Y-%m-%d"))
                )
        date += timedelta(days=1)

    conn.commit()
    conn.close()
    print(f"  [OK] SQLite database created: {DB_PATH}")
    print(f"    - respiratory_complaints: ~{181 * 5} rows")
    print(f"    - transit_metrics: ~{181 * 8} rows")
    print(f"    - waste_sensors: ~{181 * 25} rows")


# ============================================================
# 2. UNSTRUCTURED DATA — Text Documents
# ============================================================

CITIZEN_COMPLAINTS = [
    {
        "filename": "complaint_001_riverside_air.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-05-15
Complainant: Maria Gonzalez
Phone: 555-0142
Email: maria.gonzalez@email.com
Neighborhood: Riverside
Category: Air Quality / Respiratory

I've been living on Elm Street in Riverside for 12 years. Over the past three months, the air quality has gotten noticeably worse. My daughter has developed a persistent cough and our doctor says it's likely related to particulate matter exposure. I've noticed it's worst during the morning and evening hours — exactly when the buses on Route 14 are backed up bumper-to-bumper outside our building. The diesel fumes are unbearable. Multiple families in our building have complained to each other about the same issues. We need air quality monitoring stations installed in this area ASAP.

SSN mentioned by complainant (redacted before filing): 123-45-6789
"""
    },
    {
        "filename": "complaint_002_route14_delays.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-01
Complainant: James Chen
Neighborhood: Riverside
Category: Transit / Bus Delays

Route 14 has become completely unreliable. I depend on this bus to get to work at the hospital downtown, and over the last two months my commute has gone from 25 minutes to over 50 minutes. The bus is consistently 10-15 minutes late, and sometimes it just doesn't show up. The congestion on Oak Avenue is terrible — I've counted up to 30 vehicles idling between 7:30 and 8:30 AM. This is not just an inconvenience; the exhaust from all those idling vehicles is making people in our neighborhood sick. I've heard from at least five neighbors who have developed breathing problems recently.

Contact: james.chen@hospital.org, Cell: 555-0198
"""
    },
    {
        "filename": "complaint_003_pothole_riverside.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-10
Complainant: Sarah Johnson
Neighborhood: Riverside
Category: Road Infrastructure

There is a massive pothole at the intersection of Oak Avenue and 5th Street in Riverside. It's been there for at least 6 weeks and keeps getting worse. Two of my neighbors have had tire damage from hitting it. The pothole is right on the Route 14 bus corridor, and I suspect it's contributing to the traffic slowdowns we've been experiencing — cars swerve to avoid it and that backs everything up. This intersection is also near Riverside Elementary School, so it's a safety hazard for children.
"""
    },
    {
        "filename": "complaint_004_downtown_noise.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-05-20
Complainant: Robert Williams
Neighborhood: Downtown
Category: Noise

Construction on the new municipal building at 200 Main Street has been generating excessive noise from 6 AM to 8 PM, six days a week. This has been going on for three months. The noise levels make it impossible to work from home, and several elderly residents in the adjacent Parkview Senior Living facility have complained about sleep disruption. I understand the building is needed, but can the working hours be adjusted to start at 8 AM at least?
"""
    },
    {
        "filename": "complaint_005_riverside_asthma.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-18
Complainant: Dr. Priya Patel
Neighborhood: Riverside
Category: Public Health

As a family physician practicing at Riverside Community Clinic, I'm writing to formally report a concerning trend. Over the past quarter, I've seen a 40% increase in patients presenting with respiratory symptoms — persistent coughs, exacerbated asthma, and bronchitis — primarily among residents living along the Oak Avenue corridor where Bus Route 14 operates. Many of my patients, particularly children and elderly individuals, describe worsening symptoms that correlate with the increased traffic congestion we've all observed. I'm requesting that the Department of Health conduct an air quality assessment in the Riverside neighborhood, particularly along the Route 14 corridor, and that the Transit Authority investigate measures to reduce idling vehicles in residential areas.

Clinic: Riverside Community Clinic, 450 Elm Street
"""
    },
    {
        "filename": "complaint_006_greenfield_park.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-05-28
Complainant: Tom Baker
Neighborhood: Greenfield
Category: Parks & Recreation

The playground equipment at Greenfield Community Park has several broken components. The main swing set has two broken chains, and the slide has a crack near the top. I've seen kids playing on both and it's a matter of time before someone gets hurt. Also, the park benches near the pond area need repainting — they're rusted and splintering.
"""
    },
    {
        "filename": "complaint_007_riverside_bins.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-22
Complainant: Linda Martinez
Neighborhood: Riverside
Category: Waste Management

The waste bins on Oak Avenue between 3rd and 7th Street have been overflowing for over a week. Collection seems to have stopped or been severely delayed. The overflowing garbage is attracting pests and creating a terrible smell, which only adds to the air quality problems we're already dealing with in this neighborhood. Between the bus exhaust from Route 14 congestion and now rotting garbage, the air in Riverside is becoming genuinely unhealthy. I've started keeping my windows closed even in this heat.

Phone: 555-0267
"""
    },
    {
        "filename": "complaint_008_lakeside_streetlight.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-05
Complainant: David Park
Neighborhood: Lakeside
Category: Street Infrastructure

Three streetlights on Lakeview Boulevard between Harbor Drive and Marina Way have been out for two weeks. The stretch is completely dark at night, and I've heard from neighbors that there have been two minor car accidents in that area since the lights went out. This is a popular walking path for evening joggers and dog walkers. It's a serious safety concern.
"""
    },
    {
        "filename": "complaint_009_riverside_children.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-25
Complainant: Angela Thompson
Email: angela.t@parentmail.com
Neighborhood: Riverside
Category: Public Health / Children

My son attends Riverside Elementary and has missed 8 school days this month due to respiratory issues. His pediatrician says it's environmentally triggered asthma. I've connected with other parents at the school and at least 12 other children have had similar problems this spring. We believe it's connected to the worsening air quality in Riverside — the constant traffic jams on Route 14 right next to the school mean our kids are breathing diesel exhaust during recess. We're organizing a petition to demand action from the city. This is a public health emergency.
"""
    },
    {
        "filename": "complaint_010_hilltop_drainage.txt",
        "content": """CITIZEN COMPLAINT — Filed 2026-06-12
Complainant: Michael O'Brien
Neighborhood: Hilltop
Category: Infrastructure / Drainage

The storm drains on Summit Road near the Hilltop shopping center are completely blocked. During last week's rain, the road flooded to a depth of about 8 inches. Several cars were damaged and one delivery truck got stuck, blocking traffic for three hours. The flooding also seems to be washing debris downhill toward the Riverside district, which is already dealing with enough problems. Please schedule a drain clearing before the next heavy rain.
"""
    },
]

MEETING_MINUTES = [
    {
        "filename": "council_minutes_2026_04_15.txt",
        "content": """CITY COUNCIL MEETING MINUTES — April 15, 2026
Location: City Hall, Chamber A
Attendees: Mayor Richards, Council Members Davis, Kim, Okafor, Petrov, Singh

AGENDA ITEM 3: Transit Authority Quarterly Report
- Transit Director Julia Barnes presented Q1 ridership numbers
- Route 14 (Riverside Express) ridership up 12% YoY but on-time performance dropped from 82% to 64%
- Director Barnes attributed delays to increased private vehicle traffic on Oak Avenue corridor
- Councilmember Singh raised concerns about the health impacts of increased vehicle idling in Riverside residential areas
- ACTION: Transit Authority to conduct a traffic flow study on Oak Avenue corridor by end of Q2

AGENDA ITEM 5: Public Health Update
- Health Director Dr. Marcus Webb noted an uptick in respiratory-related ER visits from the Riverside zip code
- Data shows 23% increase in respiratory complaints compared to same quarter last year
- Dr. Webb recommended deploying two portable air quality monitoring units to Riverside
- Councilmember Okafor asked whether the respiratory trend correlates with the transit congestion issues discussed earlier
- Dr. Webb: "That's certainly a hypothesis worth investigating. The timing and geography are suggestive."
- ACTION: Joint working group between Transit Authority and Department of Health to investigate correlation

AGENDA ITEM 7: Budget Review
- Annual budget on track, 2.3% under projected spending
- Infrastructure maintenance fund 85% allocated for fiscal year
"""
    },
    {
        "filename": "council_minutes_2026_05_20.txt",
        "content": """CITY COUNCIL MEETING MINUTES — May 20, 2026
Location: City Hall, Chamber A
Attendees: Mayor Richards, Council Members Davis, Kim, Okafor, Petrov, Singh

AGENDA ITEM 2: Route 14 Congestion — Joint Working Group Update
- Transit Director Barnes and Health Director Webb presented preliminary findings
- Air quality samples from Route 14 corridor show PM2.5 levels 2.3x the neighborhood average during peak hours (7-9 AM, 5-7 PM)
- NO2 levels also elevated, consistent with diesel vehicle emissions
- Councilmember Kim asked about short-term mitigation options
- Director Barnes proposed: (1) signal timing optimization on Oak Avenue, (2) addition of a dedicated bus lane on the 3-block stretch near Riverside Elementary
- Estimated cost of bus lane: $180,000 — requires budget reallocation
- Mayor Richards: "This needs to move faster. The data from Dr. Webb's team is concerning, and citizen complaints are mounting."
- ACTION: Transit Authority to present a full remediation plan at the June meeting
- ACTION: Health Department to issue a public advisory for Riverside residents regarding air quality

AGENDA ITEM 4: Waste Management Service Disruption
- Sanitation Director reported a vehicle shortage affecting collection schedules in Riverside and Hilltop
- Two collection trucks out of service; replacement parts on 3-week backorder
- Interim plan: prioritize collections in areas with highest fill-sensor readings
- Councilmember Singh: "Riverside can't catch a break — transit problems, air quality, and now garbage collection delays?"
"""
    },
    {
        "filename": "council_minutes_2026_06_17.txt",
        "content": """CITY COUNCIL MEETING MINUTES — June 17, 2026
Location: City Hall, Chamber A
Attendees: Mayor Richards, Council Members Davis, Kim, Okafor, Petrov, Singh

AGENDA ITEM 1: Route 14 Remediation Plan
- Transit Director Barnes presented the full remediation proposal:
  * Phase 1 (Immediate, 2 weeks): Signal retiming on Oak Ave to prioritize bus throughput
  * Phase 2 (30 days): Temporary dedicated bus lane during peak hours, 5th to 8th Street
  * Phase 3 (60 days): Permanent bus lane with physical barriers, pending community input
- Projected impact: 35-40% reduction in Route 14 delays, 50% reduction in vehicle idling time
- Cost: Phase 1 ($12,000), Phase 2 ($45,000), Phase 3 ($180,000)
- Councilmember Okafor moved to approve Phases 1 and 2 immediately; Phase 3 pending public hearing
- APPROVED unanimously

AGENDA ITEM 2: Riverside Public Health Advisory
- Health Director Webb reported that the advisory was issued May 28
- Portable air quality monitors installed at 3 locations in Riverside on June 1
- Preliminary data confirms elevated PM2.5 and NO2 along Route 14 corridor
- 15 formal health complaints filed since the advisory was published
- Dr. Webb: "We're seeing a clear pattern. The respiratory complaint rate in Riverside is now 3.5x the city average."
- Councilmember Petrov recommended exploring a partnership with the local hospital for a respiratory health screening program

AGENDA ITEM 6: Infrastructure Maintenance Backlog
- 47 open work orders city-wide; 12 classified as high-priority
- Notable: pothole at Oak Ave & 5th Street (Riverside) has been open for 8 weeks
- Director of Public Works committed to addressing all high-priority items within 2 weeks
"""
    },
]

NEWS_ARTICLES = [
    {
        "filename": "news_riverside_health_crisis_2026_05.txt",
        "content": """RIVERSIDE TRIBUNE — May 22, 2026
HEADLINE: "Riverside Residents Report Surge in Respiratory Problems; Bus Route 14 Congestion Eyed as Culprit"
By: Jennifer Walsh, Health Reporter

Residents of the Riverside neighborhood are sounding the alarm over what they describe as a dramatic decline in air quality, and many are pointing to the increasingly congested Bus Route 14 corridor as a primary cause.

Dr. Priya Patel, a family physician at Riverside Community Clinic, says she's seen a 40% jump in patients with respiratory symptoms over the past three months. "I'm seeing children, elderly residents, and even healthy adults presenting with persistent coughs, aggravated asthma, and in some cases, new-onset breathing difficulties," she told the Tribune. "The common thread is that most of these patients live within three blocks of Oak Avenue."

Oak Avenue serves as the main corridor for Route 14, one of the city's busiest bus lines. Transit Authority data shows the route's on-time performance has plummeted from 82% to 64% this year, with average delays nearly tripling. The resulting traffic backups — sometimes stretching 10 blocks during peak hours — mean hundreds of vehicles idling in residential areas.

City air quality data, obtained by the Tribune through a public records request, shows PM2.5 levels along the Route 14 corridor are 2.3 times the neighborhood average during morning and evening rush hours. NO2 levels, a marker of diesel combustion, are similarly elevated.

"This isn't a coincidence," said Councilmember Singh at last week's city council meeting. "We have a transit problem causing a health crisis, and we need to act now."

The City Council has ordered the Transit Authority to present a remediation plan at its June meeting. In the meantime, the Department of Health has issued a public advisory urging Riverside residents — especially those with pre-existing respiratory conditions — to limit outdoor activity during peak traffic hours.

Parents at Riverside Elementary, which sits just one block from Oak Avenue, have started a petition demanding immediate action. Angela Thompson, a parent organizer, told the Tribune: "Our kids are getting sick. Twelve children in my son's grade alone have had respiratory issues this spring."
"""
    },
    {
        "filename": "news_transit_expansion_2026_04.txt",
        "content": """CITY GAZETTE — April 8, 2026
HEADLINE: "City Transit Ridership Hits 5-Year High, But Infrastructure Struggles to Keep Up"
By: Mark Torres, Transportation Reporter

The city's public transit system recorded its highest ridership numbers in five years during Q1 2026, with over 4.2 million passenger trips across all routes. Transit officials say the growth reflects the success of the city's sustainability initiatives and rising fuel costs driving more commuters to public transport.

However, the surge has exposed cracks in the system's aging infrastructure. Route 14, the Riverside Express, has seen the most dramatic impact: ridership is up 12% year-over-year, but the route's on-time performance has fallen to 64% — the lowest of any route in the system.

"Route 14 was designed for a capacity we exceeded two years ago," said Transit Director Julia Barnes. "We're running the same number of buses on roads that are carrying 30% more private vehicles than they were in 2023."

The Transit Authority has requested an additional $2.5 million in its next budget cycle for fleet expansion and route optimization. In the short term, Director Barnes says her team is evaluating signal timing changes and dedicated bus lanes on the most congested corridors.

Route 7 (Downtown Loop) and Route 21 (Lakeside Connector) have also seen ridership increases but have managed to maintain on-time performance above 75%.
"""
    },
    {
        "filename": "news_air_quality_study_2026_06.txt",
        "content": """RIVERSIDE TRIBUNE — June 10, 2026
HEADLINE: "New Air Quality Data Confirms What Riverside Residents Already Knew: The Air Is Making Them Sick"
By: Jennifer Walsh, Health Reporter

Preliminary data from portable air quality monitors installed in Riverside on June 1 confirms what residents have been complaining about for months: the air quality in the neighborhood is significantly worse than city averages, and it's worst along the Bus Route 14 corridor.

The three monitoring stations — placed at Oak Avenue & 3rd Street, Oak Avenue & 6th Street, and Elm Street & 5th Street — recorded average PM2.5 readings of 58 µg/m³ during peak hours, compared to a city average of 25 µg/m³. The World Health Organization guideline for PM2.5 is 15 µg/m³ over a 24-hour period.

"These numbers are troubling but not surprising," said Health Director Dr. Marcus Webb. "They validate the pattern we've been seeing in respiratory complaint data and emergency room visits."

The data also shows a clear temporal pattern: air quality deteriorates sharply between 7:00 and 9:00 AM and again between 5:00 and 7:00 PM — precisely the periods when Route 14 experiences its worst congestion.

Dr. Priya Patel of Riverside Community Clinic has been tracking the health impacts. "I now have 73 patients with documented respiratory symptoms that I believe are linked to local air quality," she said. "That's up from 45 when I first raised the alarm in April."

The City Council approved emergency signal timing changes and a temporary dedicated bus lane on Oak Avenue at its June 17 meeting. Transit officials project these measures will reduce vehicle idling time by up to 50%.

Environmental advocates are calling for longer-term solutions, including transitioning Route 14's fleet to electric buses and implementing a vehicle restriction zone in the densest residential blocks along Oak Avenue.
"""
    },
    {
        "filename": "news_waste_collection_2026_06.txt",
        "content": """CITY GAZETTE — June 5, 2026
HEADLINE: "Vehicle Shortage Forces Waste Collection Delays in Riverside, Hilltop"
By: Sarah Kim, City Reporter

Residents of Riverside and Hilltop neighborhoods may have noticed their garbage lingering longer than usual at the curb. The city's Sanitation Department confirmed this week that a shortage of collection vehicles has disrupted regular service in both neighborhoods.

Two of the department's heavy-duty collection trucks are currently out of service, with replacement parts on a three-week backorder. The remaining fleet has been redistributed to maintain minimum service levels city-wide, but collection frequency in Riverside and Hilltop has dropped from twice-weekly to weekly.

"We understand this is frustrating for residents, and we're working to resolve it as quickly as possible," said Sanitation Director Amy Foster. "We've prioritized collections based on data from our bin fill sensors, focusing on the fullest bins first."

The timing is particularly unfortunate for Riverside, which is already contending with air quality concerns related to Bus Route 14 congestion. Resident Linda Martinez expressed frustration: "Now on top of the bus exhaust, we have overflowing garbage bins attracting pests. It feels like this neighborhood is being neglected."

The Sanitation Department expects to return to normal collection schedules by the end of June once replacement parts arrive.
"""
    },
    {
        "filename": "news_electric_buses_2026_03.txt",
        "content": """CITY GAZETTE — March 15, 2026
HEADLINE: "City Explores Electric Bus Fleet, But Full Transition Could Take Years"
By: Mark Torres, Transportation Reporter

The City Transit Authority has released a feasibility study on transitioning its diesel bus fleet to electric vehicles, a move that environmental groups and health advocates have been pushing for years.

The study estimates the full transition would cost approximately $45 million over five years, including vehicle purchases, charging infrastructure, and maintenance facility upgrades. A partial transition — electrifying the five busiest routes, including Route 14 (Riverside Express) and Route 7 (Downtown Loop) — could be achieved for $18 million within three years.

"Electric buses would eliminate the diesel emissions that are currently a concern in neighborhoods like Riverside," said Transit Director Julia Barnes. "But this is a significant capital investment that requires careful planning."

The report notes that electric buses would reduce per-vehicle operating costs by approximately 40% due to lower fuel and maintenance expenses, potentially offsetting the higher upfront costs over a 10-year horizon.

Environmental advocacy group Clean Air Coalition praised the study but urged faster action. "The health data from Riverside shows we can't afford to wait five years," said spokesperson Ryan Torres. "Every month of delay means more residents exposed to harmful diesel emissions."

The Transit Authority has applied for a $12 million federal grant through the Clean Transit Initiative program, which would cover approximately two-thirds of the partial transition cost. A decision on the grant is expected in Q4 2026.
"""
    },
]

# Photo metadata
PHOTO_METADATA = [
    {
        "filename": "pothole_01.json",
        "image_filename": "pothole_01.jpg",
        "data": {
            "issue_type": "pothole",
            "description": "Large pothole at intersection of Oak Avenue and 5th Street, Riverside",
            "latitude": 40.7589,
            "longitude": -73.9851,
            "neighborhood": "Riverside",
            "timestamp": "2026-06-10T08:45:00Z",
            "submitted_by": "citizen_anonymous",
            "estimated_size_inches": 24,
            "notes": "Located on Route 14 bus corridor. Multiple tire damage reports."
        }
    },
    {
        "filename": "overflowing_bin_01.json",
        "image_filename": "overflowing_bin_01.jpg",
        "data": {
            "issue_type": "overflowing_waste_bin",
            "description": "Overflowing public waste bin on Oak Avenue between 5th and 6th Street, Riverside",
            "latitude": 40.7592,
            "longitude": -73.9848,
            "neighborhood": "Riverside",
            "timestamp": "2026-06-22T14:30:00Z",
            "submitted_by": "citizen_anonymous",
            "notes": "Bin has not been collected for over a week. Pest activity observed."
        }
    },
    {
        "filename": "broken_streetlight_01.json",
        "image_filename": "broken_streetlight_01.jpg",
        "data": {
            "issue_type": "broken_streetlight",
            "description": "Non-functional streetlight on Lakeview Boulevard near Harbor Drive, Lakeside",
            "latitude": 40.7623,
            "longitude": -73.9790,
            "neighborhood": "Lakeside",
            "timestamp": "2026-06-05T21:15:00Z",
            "submitted_by": "citizen_anonymous",
            "notes": "One of three streetlights out on this stretch. Safety concern for pedestrians."
        }
    }
]


def generate_unstructured_data():
    """Generate citizen complaints, meeting minutes, and news articles."""
    for dir_path in [COMPLAINTS_DIR, MINUTES_DIR, NEWS_DIR]:
        dir_path.mkdir(parents=True, exist_ok=True)

    for complaint in CITIZEN_COMPLAINTS:
        path = COMPLAINTS_DIR / complaint["filename"]
        path.write_text(complaint["content"].strip(), encoding="utf-8")
    print(f"  [OK] {len(CITIZEN_COMPLAINTS)} citizen complaints -> {COMPLAINTS_DIR}")

    for minutes in MEETING_MINUTES:
        path = MINUTES_DIR / minutes["filename"]
        path.write_text(minutes["content"].strip(), encoding="utf-8")
    print(f"  [OK] {len(MEETING_MINUTES)} meeting minutes -> {MINUTES_DIR}")

    for article in NEWS_ARTICLES:
        path = NEWS_DIR / article["filename"]
        path.write_text(article["content"].strip(), encoding="utf-8")
    print(f"  [OK] {len(NEWS_ARTICLES)} news articles -> {NEWS_DIR}")


def generate_photo_metadata():
    """Generate photo metadata JSON sidecars."""
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

    for meta in PHOTO_METADATA:
        path = PHOTOS_DIR / meta["filename"]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta["data"], f, indent=2)
    print(f"  [OK] {len(PHOTO_METADATA)} photo metadata files -> {PHOTOS_DIR}")
    print(f"    Note: Place actual .jpg images alongside these JSON files for the multimodal demo.")


def main():
    print("=" * 60)
    print("CivicMind -- Synthetic Data Generator")
    print("=" * 60)
    print(f"Seed: {SEED}")
    print(f"Date range: {START_DATE.date()} -> {END_DATE.date()}")
    print()

    print("[1/3] Generating structured data (SQLite)...")
    generate_structured_data()
    print()

    print("[2/3] Generating unstructured documents...")
    generate_unstructured_data()
    print()

    print("[3/3] Generating photo metadata...")
    generate_photo_metadata()
    print()

    print("=" * 60)
    print("All synthetic data generated successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
