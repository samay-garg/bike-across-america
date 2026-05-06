import folium
import json
import os
import re
import utils
from datetime import datetime, timezone
def colorgen():
    yield from ["#de324c", "#f4895f", "#f8e16f", "#95cf92", "#369acc", "#9656a2", "#6c584c"] * 5

# pull current location and stats from inreach
inreach_data = utils.pull_inreach()
lat = inreach_data['Latitude']
lon = inreach_data['Longitude']
current_city = utils.get_city(lat, lon)
elevation = float(inreach_data['Elevation'].split()[0]) * 3.281
velocity = float(inreach_data['Velocity'].split()[0]) / 1.609
timeval = datetime.strptime(inreach_data['Time'], "%m/%d/%Y %I:%M:%S %p")

# intialize map at the current coordinates
m = folium.Map(location=[lat, lon], zoom_start=5, tiles=None, prefer_canvas=True)

colors = colorgen()
route_files = utils.quickfilter('route_files', '.json')

for this_file in route_files:
    if len(os.path.basename(this_file).split('_')[0]) == 2:
        this_color = next(colors)
        this_weight = 4
    else:
        this_weight = 1.5
    with open(this_file) as f:
        geojson = json.load(f)
    folium.GeoJson(
        geojson,
        style_function=lambda f, c=this_color, w=this_weight: {
            "color": c,
            "weight": w,
            "opacity": 0.85
        },
        highlight_function=lambda f, c=this_color: {
            "color":c,
            "weight": 9,
            "opacity": 1.0
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["name"],
            aliases=[""],
            class_name="route-tooltip"
        ),
        control=False
    ).add_to(m)

    # gain = 0
    # for i in range(1, len(points)):
    #     diff = points[i][2] > points[i-1][2]
    #     if diff > 0:
    #         gain += diff
    first_point = geojson['geometry']['coordinates'][0]
    city_loc = (first_point[1], first_point[0])
    this_city = utils.get_city(*city_loc)
    folium.Marker(
        location=city_loc,
        popup=folium.Popup(
            html=f"<div class='popup-title'>{this_city}</div>",
            max_width=200
        ),
        icon=folium.Icon(color='green')
    ).add_to(m)
last_point = geojson['geometry']['coordinates'][-1]
city_loc = (last_point[1], last_point[0])
this_city = utils.get_city(*city_loc)
folium.Marker(
    location=city_loc,
    popup=folium.Popup(
        html=f"<div class='popup-title'>{this_city}</div>",
        max_width=200
    ),
    icon=folium.Icon(color='red')
).add_to(m)

folium.Marker(
    location=(lat, lon),
    popup=folium.Popup(
        html=f"""
            <div class='popup-title'>Samay Garg</div>
            <div class='popup-detail'>{current_city}</div>
            <div class='popup-detail'>{elevation:,.0f} ft</div>
            <div class='popup-detail'>{velocity:.0f} mi/h</div>
        """,
        max_width=200
    ),
    icon=folium.Icon(color='blue', icon='bicycle', prefix='fa')
).add_to(m)

folium.TileLayer("OpenStreetMap", name="Street Map").add_to(m)
folium.TileLayer("Esri WorldImagery", name="Satellite").add_to(m)
folium.TileLayer("CartoDB Voyager", name="Minimal").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer("Esri WorldTopoMap", name="Topo Map").add_to(m)

folium.LayerControl(position='topright', collapsed=False).add_to(m)

m.get_root().html.add_child(folium.Element('<link rel="stylesheet" href="css/folium-style.css">'))

m.save("routemap.html")

timestamp = datetime.now().strftime('%B %d, %Y at %I:%M %p')
with open('index.html') as f:
    index = f.read()
index = re.sub(r'Last updated: .*', f'Last updated: {timestamp}', index)
with open('index.html', 'w') as f:
    f.write(index)

print(f'map generated successfully at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')