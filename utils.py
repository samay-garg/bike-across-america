import re
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv
import requests
import json

load_dotenv()

geolocator = Nominatim(user_agent="my_gps_app")

def quickfilter(folder, *args):
    allfiles = os.listdir(folder)
    allfiles.sort()
    filtered = []
    for f in allfiles:
        flag = False
        if f.startswith('.'):
            flag=True
        else:
            for a in args:
                if a not in f:
                    flag=True
                    break
        if not flag:
            filtered.append(os.path.join(folder, f))
    return filtered

def try_serialize(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)

def coerce(v):
    if v is None:
        return None
    for cast in (int, float):
        try:
            return cast(v)
        except (TypeError, ValueError):
            pass
    if v.lower() == 'true':
        return True
    if v.lower() == 'false':
        return False
    return v

# convert xml tree to a dict that can be parsed as json
def xml_to_dict(element):
    if len(element) == 0:
        return coerce(element.text)
    children = list(element)
    if len(children) == 1 and children[0].tag.split('}')[-1] == 'value':
        return coerce(children[0].text)
    return {child.get('name', child.tag): xml_to_dict(child) for child in children}

# function to determine the namespace of an xml file
def get_namespace(root):
    #if root has namespace, it will match: {namespace}:key
    regex = re.compile(r'\{(.*)\}(\w+)')
    result = regex.match(root.tag)
    if result:
        return {result[2]: result[1]}
    return {}

# reads gpx files and returns a list of tuples containing (latitude, longitude, elevation)
def read_gpx(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    NS = get_namespace(root)
    points = []
    for trk in root.findall('gpx:trk', NS):
        name = trk.findtext('gpx:name', default='N/A', namespaces=NS)
        for trkseg in trk.findall('gpx:trkseg', NS):
            for trkpt in trkseg.findall('gpx:trkpt', NS):
                lat = float(trkpt.get('lat'))
                lon = float(trkpt.get('lon'))
                ele = float(trkpt.findtext('gpx:ele', default='N/A', namespaces=NS))
                points.append((lat, lon, ele))
    return name, points

def gpx_to_geojson(filepath):
    name, points = read_gpx(filepath)
    return {
        "type": "Feature",
        "properties": {"name": name},
        "geometry": {
            "type": "LineString",
            "coordinates": [[lon, lat, ele] for lat, lon, ele in points]
        }
    }

# determines the city from latitude/longitude coordinates
def get_city(lat, lon, retries=3):
    for attempt in range(retries):
        try:
            location = geolocator.reverse(f"{lat}, {lon}", language="en")
            address = location.raw['address']
            city = (
                address.get('city') or
                address.get('town') or
                address.get('village') or
                address.get('county') or
                "Unknown"
            )
            state = address.get('ISO3166-2-lvl4', '')
            state = state.split('-')[-1] if state else ''
            return f"{city}, {state}" if state else city
        except GeocoderTimedOut:
            if attempt < retries - 1:
                time.sleep(1)
                continue
            return "Timeout"
        except Exception as e:
            return f"Error: {e}"

# pulls current location from inreach
def pull_inreach():
    inreach_url = f"https://share.garmin.com/Feed/Share/{os.getenv('INREACH_ID')}"
    response = requests.get(inreach_url)
    root = ET.fromstring(response.text)
    NS = get_namespace(root)
    document = root.find('kml:Document', NS)
    folder = document.find('kml:Folder', NS)
    for placemark in folder.findall('kml:Placemark', NS):
        desc = placemark.find('kml:description', NS).text
        if not desc:
            break
    extended_data = placemark.find('kml:ExtendedData', NS)
    lat, lon, elev, timeval = 0, 0, 0, datetime.fromtimestamp(0, tz=timezone.utc)
    return xml_to_dict(extended_data)


if __name__ == '__main__':
    data = pull_inreach()
    for this_file in os.listdir('route_files'):
        if '.gpx' in this_file:
            geojson = gpx_to_geojson(os.path.join('route_files', this_file))
            new_filename = this_file.replace('.gpx', '.json')
            with open(os.path.join('route_files', new_filename), 'w') as f:
                json.dump(geojson, f)
    
    for x in quickfilter('route_files', '.json'):
        print(x)