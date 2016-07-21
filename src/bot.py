from pgoapi import PGoApi
from pgoapi.utilities import f2i, h2f
import yaml
import os
import time
import json
import random
from s2sphere import Cell, CellId, LatLng
from google.protobuf.internal import encoder


def load_config():
    file = "config.json"
    if os.path.isfile(file):
        with open(file) as data:
            return json.load(data)
    raise Error


def load_pokemon():
    file = "src/pokemon.yaml"
    if os.path.isfile(file):
        with open(file) as data:
            return yaml.load(data)

CONFIG = load_config()
POKEMON_DB = load_pokemon()


def encode(cellid):
    output = []
    encoder._VarintEncoder()(output.append, cellid)
    return ''.join(output)
    
    
def get_cell_ids(lat, long, radius = 10):
    origin = CellId.from_lat_lng(LatLng.from_degrees(lat, long)).parent(15)
    walk = [origin.id()]
    right = origin.next()
    left = origin.prev()

    # Search around provided radius
    for i in range(radius):
        walk.append(right.id())
        walk.append(left.id())
        right = right.next()
        left = left.prev()

    # Return everything
    return sorted(walk)
  

def generate_spiral(starting_lat, starting_lng, step_size, step_limit):
    coords = [{'lat': starting_lat, 'lng': starting_lng}]
    steps,x,y,d,m = 1, 0, 0, 1, 1
    rlow = 0.0
    rhigh = 0.0005

    while steps < step_limit:
        while 2 * x * d < m and steps < step_limit:
            x = x + d
            steps += 1
            lat = x * step_size + starting_lat + random.uniform(rlow, rhigh)
            lng = y * step_size + starting_lng + random.uniform(rlow, rhigh)
            coords.append({'lat': lat, 'lng': lng})
        while 2 * y * d < m and steps < step_limit:
            y = y + d
            steps += 1
            lat = x * step_size + starting_lat + random.uniform(rlow, rhigh)
            lng = y * step_size + starting_lng + random.uniform(rlow, rhigh)
            coords.append({'lat': lat, 'lng': lng})

        d = -1 * d
        m = m + 1
    return coords

    
def format_pokemon(pokemon):
    id = pokemon['pokemon_data']['pokemon_id']
    return {
        'id': id,
        'name': POKEMON_DB['pokemon'][id-1]['name'],
        'icon': POKEMON_DB['pokemon'][id-1]['src'],
        'lat': pokemon['latitude'],
        'long': pokemon['longitude'],
        'time_till_hidden': pokemon['time_till_hidden_ms']/1000
    }
  
def find_pokemon(client, lat, long):
    step_size = 0.0015
    step_limit = 100
    coords = generate_spiral(lat, long, step_size, step_limit)
    pokemons = []
    seen = set()

    for coord in coords:
        lat = coord['lat']
        lpng = coord['lng']
        client.set_position(lat, long, 0)
        
        cell_ids = get_cell_ids(lat, long)
        timestamps = [0,] * len(cell_ids)
        client.get_map_objects(latitude=f2i(lat), longitude=f2i(long), since_timestamp_ms=timestamps, cell_id=cell_ids)
        
        response = client.call()
        if response['responses']['GET_MAP_OBJECTS']['status'] == 1:
            for map_cell in response['responses']['GET_MAP_OBJECTS']['map_cells']:
                if 'wild_pokemons' in map_cell:
                    for pokemon in map_cell['wild_pokemons']:
                        encounter_id = pokemon['encounter_id']
                        if encounter_id in seen:
                            continue
                        else:
                            seen.add(encounter_id)
                        print(pokemon)
                        pokemons.append(pokemon)
    
    return list(map(format_pokemon, pokemons))
                    
if __name__ == '__main__':
    client = PGoApi()
    
    logged_in = client.login(CONFIG['auth_service'], CONFIG['username'], CONFIG['password'])
    if not logged_in:
        print("Could not login")
        exit()

    pokemon = find_pokemon(client, CONFIG['lat'], CONFIG['long'])
    print(pokemon)