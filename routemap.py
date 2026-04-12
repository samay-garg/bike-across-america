import xml.etree.ElementTree as ET
import folium
import json
import os
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
import time

geolocator = Nominatim(user_agent="my_gps_app")

def colorgen():
	yield from ["#9656a2","#369acc","#95cf92","#f8e16f","#f4895f","#de324c","#6c584c"] * 5

def get_namespace(root):
	# Root tag looks like '{http://www.topografix.com/GPX/1/1}gpx'
	# Split on '}' to extract just the namespace URI
	if '}' in root.tag:
		return {'gpx': root.tag.split('}')[0].strip('{')}
	return {}

def read_gpx(filepath):
	tree = ET.parse(filepath)
	root = tree.getroot()
	NS = get_namespace (root)
	points = []
	for trk in root.findall('gpx:trk', NS):
		name = trk.findtext('gpx:name', default='N/A', namespaces=NS)
		# print(f"  Track: {name}")
		for trkseg in trk.findall('gpx:trkseg', NS):
			for trkpt in trkseg.findall('gpx:trkpt', NS):
				lat  = float(trkpt.get('lat'))
				lon  = float(trkpt.get('lon'))
				ele  = float(trkpt.findtext('gpx:ele',  default='N/A', namespaces=NS))
				time = trkpt.findtext('gpx:time', default='N/A', namespaces=NS)
				points.append((lat, lon, ele))
	return name, points

def get_city(lat, lon, retries=3):
	for attempt in range(retries):
		try:
			location = geolocator.reverse(f"{lat}, {lon}", language="en")
			address = location.raw['address']
			return (
				address.get('city') or
				address.get('town') or
				address.get('village') or
				address.get('county') or
				"Unknown"
			)
		except GeocoderTimedOut:
			if attempt < retries - 1:
				time.sleep(1)
				continue
			return "Timeout"
		except Exception as e:
			return f"Error: {e}"

m = folium.Map(location=[44.967243, -103.771556], zoom_start=5, tiles=None, prefer_canvas=True)
colors = colorgen()
gpx_files = os.listdir('gpx')
gpx_files.sort()

for this_file in gpx_files:
	if '.gpx' not in this_file:
		continue
	if len(this_file.split('_')[0]) == 2:
		this_color = next(colors)
		this_weight = 4
	else:
		this_weight = 1.5
	name, points = read_gpx(os.path.join('gpx', this_file))
	geojson = {
		"type": "Feature",
		"properties": {
			"name": name        # store name in properties
		},
		"geometry": {
			"type": "LineString",
			"coordinates": [[lon, lat] for lat, lon, _ in points]  # GeoJSON uses [lon, lat]
		}
	}
	# folium.PolyLine(points, color=this_color, weight=3).add_to(m)
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
			fields=["name"],            # which properties to show
			aliases=[""],
			style="""
				font-size: 14px;
				font-weight: normal;
				font-family: Helvetica;
				color: #000000;
				background-color: white;
				border: 1px solid grey;
				border-radius: 4px;
				padding: 4px;
				text-align: center;
			"""
		),
		control=False
	).add_to(m)
	
	gain = 0
	for i in range(1, len(points)):
		diff = points[i][2] > points[i-1][2]
		if diff > 0:
			gain += diff
	city_loc = (points[0][0], points[0][1])
	this_city = get_city(*city_loc)
	folium.Marker(
	    location=city_loc,
	    popup=folium.Popup(
	        html=f"""
	            <div style='
	                font-size: 14px;
	                font-weight: bold;
	                text-align: center;
	                min-width: 120px;
	                color: #333;
	            '>
	                {this_city}
	            </div>
	            <div style='
	                font-size: 14px;
	                font-weight: bold;
	                text-align: center;
	                min-width: 120px;
	                color: #333;
	            '>
	                {gain} mi
	            </div>
	        """,
	        max_width=200
	    ), 
	    icon=folium.Icon(color='green')
	).add_to(m)
city_loc = (points[-1][0], points[-1][1])
this_city = get_city(*city_loc)
folium.Marker(
	    location=city_loc,
	    popup=folium.Popup(
	        html=f"""
	            <div style='
	                font-size: 14px;
	                font-weight: bold;
	                text-align: center;
	                min-width: 120px;
	                color: #333;
	            '>
	                {this_city}
	            </div>
	        """,
	        max_width=200
	    ),
	    icon=folium.Icon(color='red')
	).add_to(m)
folium.TileLayer("OpenStreetMap", name="Street Map").add_to(m)
folium.TileLayer("Esri WorldImagery", name="Satellite").add_to(m)
folium.TileLayer("CartoDB Voyager", name="Minimal").add_to(m)
folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
folium.TileLayer("Esri WorldTopoMap", name="Topo Map").add_to(m)
folium.LayerControl(
    position='topright',
    collapsed=False
).add_to(m)

m.get_root().html.add_child(folium.Element("""
<style>
  .leaflet-control-layers { font-size: 14px; }
  .leaflet-control-layers-base label { font-size: 14px; }
</style>
"""))

m.save("routemap.html")