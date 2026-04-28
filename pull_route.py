import os
import pandas as pd
import time
import json
from dotenv import load_dotenv
from stravalib import unit_helper
from jinja2 import Environment, FileSystemLoader
import utils

load_dotenv()
CACHE_FILE = 'route_cache.json'
CACHE_MAX_AGE = 60 * 60 # 1 hour in seconds

client = utils.make_strava_client()

route_ids = [
    3478539852550458596,
    3478541079657983600,
    3478520238922346934,
    3478535424723217292,
    3478522735067789196,
    3478522735067333516,
    3478551128413981296
]

# Load from cache if fresh, otherwise fetch from Strava
cache_valid = (os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_MAX_AGE)
if cache_valid:
    with open(CACHE_FILE, 'r') as f:
        content = f.read()
        routes = json.loads(content) if content.strip() else {}
    print(f'Loaded {len(routes)} routes from cache')
else:
    print('Pulling routes from Strava')
    routes = {}
existing_routes = list(map(int, routes.keys()))
for this_id in route_ids:
    if this_id not in existing_routes:
        this_route = client.get_route(this_id)
        routes.update(utils.strava_to_json(this_route))
        this_id_str = str(this_id)
        routes[this_id_str]['distance_mi'] = unit_helper.miles(this_route.distance).magnitude
        routes[this_id_str]['elevation_gain_ft'] = unit_helper.feet(this_route.elevation_gain).magnitude
with open(CACHE_FILE, 'w') as f:
    json.dump(routes, f, indent=2)
print(f"Saved {len(routes) - len(existing_routes)} new routes to {CACHE_FILE}")

itinerary_df = pd.read_excel('transamerica_planning.xlsx', sheet_name='Itinerary')
itinerary_df = itinerary_df.loc[:, ['Segment', 'Day']]
itinerary_df = itinerary_df.groupby('Segment').agg(len)

route_list = []
for i, this_id in enumerate(route_ids):
    this_route = routes[str(this_id)]
    route_list.append({
        'id': this_id,
        'name': this_route['name'].replace('-', ' to '),
        'distance_mi': f"{this_route['distance_mi']:.0f}",
        'elevation_gain_ft': f"{this_route['elevation_gain_ft']:,.0f}",
        'days': itinerary_df.loc[i + 1, 'Day'],
        'map_hash': utils.compute_map_hash(this_route)
    })

env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('routes.html')
with open('routes.html', 'w') as f:
    f.write(template.render(routes=route_list))