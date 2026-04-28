import os
import time
from dotenv import load_dotenv
import utils
import json
from jinja2 import Environment, FileSystemLoader
from datetime import datetime
import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import LineString
import contextily as ctx


load_dotenv()

CACHE_FILE = 'activity_cache.json'
CACHE_MAX_AGE = 60 * 60 * 24
IMG_DIR = 'images'

os.makedirs(IMG_DIR, exist_ok=True)

client = utils.make_strava_client()

cache_valid = (os.path.exists(CACHE_FILE) and time.time() - os.path.getmtime(CACHE_FILE) < CACHE_MAX_AGE)

if cache_valid:
    with open(CACHE_FILE) as f:
        content = f.read()
        activities = json.loads(content) if content.strip() else {}
    print(f'Loaded {len(activities)} activities from cache')
else:
    activities = {}
    for summary in client.get_activities(limit=10):
        if 'ride' not in str(summary.sport_type).lower():
            continue
        detailed = client.get_activity(summary.id)
        activities.update(utils.strava_to_json(detailed))
    with open(CACHE_FILE, 'w') as f:
        json.dump(activities, f, indent=2)
    print("Fetched from Strava and cached")

activity_list = []
for activity_id, a in activities.items():
    img_path = os.path.join(IMG_DIR, f'{activity_id}.png')
    if not os.path.exists(img_path):
        streams = client.get_activity_streams(int(activity_id), types=['latlng'])
        latlng = streams['latlng'].data if 'latlng' in streams else None
        if latlng:
            start_lat, start_lon = latlng[0]
            end_lat, end_lon = latlng[-1]
            start_city = utils.get_city(start_lat, start_lon)
            end_city = utils.get_city(end_lat, end_lon)

            line = LineString([(lon, lat) for lat, lon in latlng])
            gdf = gpd.GeoDataFrame(geometry=[line], crs="EPSG:4326").to_crs(epsg=3857)
            projected = gdf.geometry[0]
            start_xy = projected.coords[0]
            end_xy = projected.coords[-1]

            fig, ax = plt.subplots(figsize=(6, 4), dpi=100)
            gdf.plot(ax=ax, color='#127573', linewidth=1.5)
            ax.scatter(*start_xy, color='green', s=30, zorder=5)
            ax.scatter(*end_xy, color='red', s=30, zorder=5)
            ax.annotate(start_city, xy=start_xy, xytext=(6, 6), textcoords='offset points',
                        fontsize=7, color='#1f364b', fontweight='bold')
            ax.annotate(end_city, xy=end_xy, xytext=(6, 6), textcoords='offset points',
                        fontsize=7, color='#1f364b', fontweight='bold')
            ctx.add_basemap(ax, source=ctx.providers.CartoDB.Voyager, alpha=0.35, attribution=False)
            ax.set_axis_off()
            plt.tight_layout()
            fig.savefig(img_path, dpi=100)
            plt.close(fig)
        else:
            img_path = None

    moving_time = a['moving_time']
    hours, remainder = divmod(moving_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    activity_list.append({
        'id': activity_id,
        'name': a['name'],
        'date': datetime.strptime(a['start_date_local'], '%Y-%m-%d %H:%M:%S').strftime('%B %d, %Y'),
        'distance_mi': f"{a['distance'] / 1609.34:.0f} mi",
        'elevation_gain_ft': f"{a['total_elevation_gain'] * 3.28084:,.0f} ft",
        'moving_time': f"{int(hours)}h {int(minutes)}m",
        'description': a.get('description') or '',
        'img': img_path
    })

GOAL_MILES = 5400
total_miles = sum(a['distance'] / 1609.34 for a in activities.values())
# total_miles=1000
progress_pct = round(min(total_miles / GOAL_MILES * 100, 100), 1)

env = Environment(loader=FileSystemLoader('templates'))

template = env.get_template('activities.html')
with open('activities.html', 'w') as f:
    f.write(template.render(activities=activity_list))

template = env.get_template('index.html')
with open('index.html', 'w') as f:
    f.write(template.render(total_miles=f"{total_miles:,.0f}", progress_pct=progress_pct))