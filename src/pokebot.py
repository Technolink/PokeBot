from slacker import Slacker
from pgoapi import PGoApi
from pgoapi.utilities import f2i, h2f
import yaml
import os
import time
import re
import sys
from datetime import datetime, timedelta
from tzlocal import get_localzone
from pytz import timezone
import json
import random
from s2sphere import Cell, CellId, LatLng
from google.protobuf.internal import encoder

path = os.path.dirname(os.path.realpath(__file__))


def load_config(file=None):
    if file is None:
        file = path+"/../config.json"
    with open(file) as data:
        return json.load(data)


def load_pokemon():
    file = path+"/pokemon.yaml"
    with open(file) as data:
        return yaml.load(data)

CONFIG = {}
POKEMON_DB = load_pokemon()
POKEMON_NAME_TO_ID = {}

for i in range(1,len(POKEMON_DB['pokemon'])):
    POKEMON_NAME_TO_ID[POKEMON_DB['pokemon'][i-1]['name']] = i

   
class Pokemon(object):
    @classmethod
    def from_data(cls, pokemon_data):
        return cls(pokemon_data['pokemon_data']['pokemon_id'],
                      pokemon_data['latitude'],
                      pokemon_data['longitude'],
                      pokemon_data['encounter_id'],
                      pokemon_data['time_till_hidden_ms'])

    def __init__(self, id, lat, long, encounter_id, time_till_hidden_ms):
        self.id = id
        self.name = POKEMON_DB['pokemon'][self.id-1]['name']
        self.icon = POKEMON_DB['pokemon'][self.id-1]['src']
        self.rarity = POKEMON_DB['pokemon'][self.id-1]['rarity']
        self.encounter_id = encounter_id
        self.lat = lat
        self.long = long
        self.time_till_hidden = time_till_hidden_ms/1000
        datetime_hidden = (datetime.now() + timedelta(0, self.time_till_hidden))
        datetime_hidden = get_localzone().localize(datetime_hidden).astimezone(timezone(CONFIG['timezone']))
        
        self.datetime_hidden = datetime_hidden.strftime("%I:%M:%S %p")

    def __lt__(self, other):
        return self.id < other.id
    
    def __eq__(self, other):
        return self.encounter_id == other.encounter_id
        
    def __hash__(self):
        return self.encounter_id
    
    def __repr__(self):
        return "[id: {}, name: {}, lat: {}, long: {}, encounter_id: {}]".format(self.id, self.name, self.lat, self.long, self.encounter_id)
        
    def to_dict(self):
        return {
            'id': self.id,
            'lat': self.lat,
            'long': self.long,
            'name': self.name,
            'encounter_id': self.encounter_id,
            'time_till_hidden': self.time_till_hidden
        }

    
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

    
def generate_location_steps(starting_lat, startin_lng, step_size, step_limit):
    pos, x, y, dx, dy = 1, 0, 0, 0, -1
    while -step_limit / 2 < x <= step_limit / 2 and -step_limit / 2 < y <= step_limit / 2:
        yield {'lat': x * step_size + starting_lat, 'lng': y * step_size + startin_lng}
        if x == y or (x < 0 and x == -y) or (x > 0 and x == 1 - y):
            dx, dy = -dy, dx
        x, y = x + dx, y + dy


def find_pokemon(client, starting_lat, starting_long):
    step_size = 0.0015
    step_limit = 2
    coords = generate_location_steps(starting_lat, starting_long, step_size, step_limit)
    pokemons = []
    seen = set()

    for coord in coords:
        lat = coord['lat']
        long = coord['lng']
        client.set_position(lat, long, 0)
        
        cell_ids = get_cell_ids(lat, long)
        timestamps = [0,] * len(cell_ids)
        response = client.get_map_objects(latitude=f2i(lat), longitude=f2i(long), since_timestamp_ms=timestamps, cell_id=cell_ids)
        
        if response['responses']['GET_MAP_OBJECTS']['status'] == 1:
            for map_cell in response['responses']['GET_MAP_OBJECTS']['map_cells']:
                if 'wild_pokemons' in map_cell:
                    for pokemon in map_cell['wild_pokemons']:
                        encounter_id = pokemon['encounter_id']
                        if encounter_id in seen:
                            continue
                        else:
                            seen.add(encounter_id)
                        pokemons.append(Pokemon.from_data(pokemon))
        time.sleep(5)
    
    return pokemons

    
def save_and_filter_pokemon(pokemons, db_path=None):
    if db_path is None:
        db_path = path+"/../pokemon_db.json"

    existing = {}
    if os.path.isfile(db_path):
        with open(db_path) as data:
            existing = json.load(data)

    filtered_pokemons = [pokemon for pokemon in pokemons if str(pokemon.encounter_id) not in existing]
    for pokemon in filtered_pokemons:
        existing[pokemon.encounter_id] = pokemon.to_dict()
    
    with open(db_path, 'w') as data:
        json.dump(existing, data)
    
    return filtered_pokemons


def post_to_slack(pokemons):
    slack = Slacker(CONFIG['slackToken'])
    for pokemon in pokemons:
        message = 'You can find ' + pokemon.name + ' <http://maps.google.com/maps?q=' + str(pokemon.lat) + \
            ',' + str(pokemon.long) + '&ll=' + str(pokemon.lat) + ',' + str(pokemon.long) + \
            '&z=18|' + 'here' + \
            '> until ' + pokemon.datetime_hidden
        if (pokemon.rarity >= CONFIG['channel_rarity']):
            message = '<!channel> ' + message
        elif (pokemon.rarity >= CONFIG['here_rarity']):
            message = '<!here> ' + message
        elif (pokemon.raritiy == 0):
            return # Do not post for really common pokemon
        slack.chat.post_message(CONFIG['slackChannel'], message, username=pokemon.name, icon_emoji=":pokemon-{}:".format(pokemon.name))


if __name__ == '__main__':
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    CONFIG = load_config(config_path)

    client = PGoApi()
    encrypt_file = path+"/../encrypt.so"

    client.activate_signature(encrypt_file)
    client.set_position(CONFIG['lat'], CONFIG['long'], 0)

    logged_in = client.login(CONFIG['auth_service'], CONFIG['username'], CONFIG['password'])
    pokemons = []
    if logged_in:
        pokemons = find_pokemon(client, CONFIG['lat'], CONFIG['long'])
        pokemons.sort()
        print(pokemons)
    
    post_to_slack(save_and_filter_pokemon(pokemons, CONFIG['db_path']))

