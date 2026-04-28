import re
import os
import time
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from dotenv import load_dotenv, set_key
import requests
import json
from stravalib import Client
from polyline import decode

load_dotenv()

geolocator = Nominatim(user_agent="my_gps_app")

# filter and sort files
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

# check if an input can be serialized for JSON output
# def try_serialize(v):
#     try:
#         json.dumps(v)
#         return v
#     except (TypeError, ValueError):
#         return str(v)

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

# convert gpx file to a geojson dict
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
    return xml_to_dict(extended_data)

def serialize_strava(v):
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        if hasattr(v, 'model_dump'):
            dumped = v.model_dump()
            if isinstance(dumped, dict):
                return {k: serialize_strava(val) for k, val in dumped.items()}
            return serialize_strava(dumped)
        if hasattr(v, '__iter__') and not isinstance(v, (str, bytes)):
            try:
                return [serialize_strava(i) for i in v]
            except Exception:
                return str(v)
        if hasattr(v, '__dict__'):
            return {k: serialize_strava(val) for k, val in vars(v).items()}
        return str(v)

def strava_to_json(activity):
    details = {k: serialize_strava(v) for k, v in vars(activity).items() if k != 'id'}
    return {str(activity.id): details}

def compute_map_hash(route):
    map_data = route['map']
    if isinstance(map_data, dict):
        polyline_str = map_data.get('summary_polyline') or map_data.get('polyline', '')
    else:
        match = re.search(r"summary_polyline='(.*?)'", str(map_data))
        polyline_str = match[1] if match else ''
    if not polyline_str:
        return None
    coords = decode(polyline_str)
    lats = [c[0] for c in coords]
    lons = [c[1] for c in coords]
    center_lat = (min(lats) + max(lats)) / 2
    center_lon = (min(lons) + max(lons)) / 2
    span = max(max(lats) - min(lats), max(lons) - min(lons))
    zoom = round(math.log2(360 / span), 2)
    return f"{zoom}/{center_lat:.3f}/{center_lon:.3f}"

def make_strava_client():
    CLIENT_ID = os.getenv('STRAVA_CLIENT_ID')
    CLIENT_SECRET = os.getenv('STRAVA_CLIENT_SECRET')
    access_token = os.getenv('STRAVA_ACCESS_TOKEN')
    refresh_token = os.getenv('STRAVA_REFRESH_TOKEN')
    expires_at = os.getenv('STRAVA_TOKEN_EXPIRES_AT')

    client = Client()

    if not access_token:
        # First-time setup: generate auth URL, exchange code for tokens
        url = client.authorization_url(
            client_id=CLIENT_ID,
            redirect_uri='http://localhost',
            scope=['read', 'activity:read_all']
        )
        print("Open this URL in your browser:\n", url)
        code = input("\nPaste the 'code' from the redirect URL: ").strip()

        token_response = client.exchange_code_for_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            code=code
        )
        access_token = token_response['access_token']
        refresh_token = token_response['refresh_token']
        expires_at = str(token_response['expires_at'])

        set_key('.env', 'STRAVA_ACCESS_TOKEN', access_token)
        set_key('.env', 'STRAVA_REFRESH_TOKEN', refresh_token)
        set_key('.env', 'STRAVA_TOKEN_EXPIRES_AT', expires_at)
        print("Tokens saved to .env")

    client.access_token = access_token
    client.refresh_token = refresh_token
    client.token_expires = int(expires_at)
    return client

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