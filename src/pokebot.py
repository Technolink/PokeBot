from slacker import Slacker
from pgoapi import PGoApi
from pgoapi.utilities import f2i, h2f
import yaml
import os
from datetime import datetime, timedelta
import json
import random
from s2sphere import Cell, CellId, LatLng
from google.protobuf.internal import encoder

path = os.path.dirname(os.path.realpath(__file__))


def load_config():
    file = path+"/../config.json"
    with open(file) as data:
        return json.load(data)


def load_pokemon():
    file = path+"/pokemon.yaml"
    with open(file) as data:
        return yaml.load(data)


CONFIG = load_config()
POKEMON_DB = load_pokemon()
BOT_ICON = ""

class Pokemon(object):
    def __init__(self, pokemon_data):
        self.id = pokemon_data['pokemon_data']['pokemon_id']
        self.name = POKEMON_DB['pokemon'][self.id-1]['name']
        self.icon = POKEMON_DB['pokemon'][self.id-1]['src']
        self.rarity = POKEMON_DB['pokemon'][self.id-1]['rarity']
        self.lat = pokemon_data['latitude']
        self.long = pokemon_data['longitude']
        self.time_till_hidden = pokemon_data['time_till_hidden_ms']/1000

    def __lt__(self, other):
        return self.id < other.id
    
    def __eq__(self, other):
        return self.id < other.id
    
    def __repr__(self):
        return "id: {}, name: {}, lat: {}, long: {}, time_till_hidden: {}".format(self.id, self.name, self.lat, self.long, self.time_till_hidden)

    
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
    step_limit = 1
    #coords = generate_spiral(lat, long, step_size, step_limit)
    coords = generate_location_steps(starting_lat, starting_long, step_size, step_limit)
    pokemons = []
    seen = set()

    for coord in coords:
        lat = coord['lat']
        long = coord['lng']
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
                        pokemons.append(Pokemon(pokemon))
    
    return pokemons


def post_to_slack(pokemons):
    slack = Slacker(CONFIG['slackToken'])
    for pokemon in pokemons:
        message = 'You can find me <https://pokevision.com/#/@' + str(pokemon.lat) + \
            ',' + str(pokemon.long) + \
            '|' + 'here' + \
            '> until ' + (datetime.now() + timedelta(0, pokemon.time_till_hidden)).strftime("%-I:%M:%S %p")
        if (pokemon.rarity >= CONFIG['channel_rarity']):
            message = '<!channel> ' + message
        elif (pokemon.rarity >= CONFIG['here_rarity']):
            message = '<!here> ' + message
        slack.chat.post_message('@alan.goldman', message, username=pokemon.name, icon_emoji=":pokemon-{}:".format(pokemon.name))


if __name__ == '__main__':
    client = PGoApi()
    logged_in = client.login(CONFIG['auth_service'], CONFIG['username'], CONFIG['password'])
    pokemons = []
    if logged_in:
        pokemons = find_pokemon(client, CONFIG['lat'], CONFIG['long'])
        pokemons.sort()
        print(pokemons)

    post_to_slack(pokemons)
    
    
