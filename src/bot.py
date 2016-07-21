from pgoapi import PGoApi
from pgoapi.utilities import f2i, h2f
import yaml
import os
import json
from s2sphere import Cell, CellId, LatLng
from google.protobuf.internal import encoder

def load_config():
    file = "config.json"
    if os.path.isfile(file):
        with open(file) as data:
            return json.load(data)
    raise Error

    
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


def find_pokemon(client, lat, long):
    client.set_position(lat, long, 0)
    cell_ids = get_cell_ids(lat, long)
    timestamps = [0,] * len(cell_ids)
    client.get_map_objects(latitude=f2i(lat), longitude=f2i(long), since_timestamp_ms=timestamps, cell_id=cell_ids)

    response = client.call()
    print(response)
    
if __name__ == '__main__':
    config = load_config()
    client = PGoApi()
    
    logged_in = client.login(config['auth_service'], config['username'], config['password'])
    if not logged_in:
        print("Could not login")
        exit()
    
    #client.get_player()
    #response = client.call()
    #print(response)
    #print(json.dumps(response))
    
    find_pokemon(client, config['lat'], config['long'])