# Code associated w/: https://youtu.be/6_GXTbTL9Uc
import math, sys
from lux import game
from lux.game import Game
from lux.game_map import Cell, RESOURCE_TYPES
from lux.constants import Constants
from lux.game_constants import GAME_CONSTANTS
from lux import annotate
import numpy as np
from collections import deque
import random

logfile = "agent.log"
citylog = "city.log"

testfile = "test.txt"

open(logfile,"w")

DIRECTIONS = Constants.DIRECTIONS
game_state = None
build_location = None

unit_to_city_dict = {}
unit_to_resource_dict = {}
unit_to_build_dict = {}
worker_positions = {}
city_to_units_dict = {}
city_capacity_dict = {}
build_city_list = []

statsfile = "agent.txt"

def getKey(item):
    return item[1]

def get_resource_tiles(game_state, width, height):
    resource_tiles: list[Cell] = []
    for y in range(height):
        for x in range(width):
            cell = game_state.map.get_cell(x, y)
            if cell.has_resource():
                resource_tiles.append(cell)
    return resource_tiles

def get_resource_range(game_state, player, width, height, x, y, search=3, ignore_city=False):
   #     with open(testfile,"a") as f:
   #         f.write(f"entered get_resource_range checking {type(x)},{type(y)}\n")
   #         f.write(f"checking from {max(0, (y-search))} to {min(height, (y+search))}\n")
        fuel_amount = 0
        y_min = max(0, (y-search))
        y_max = min(height, (y+search))
        for sub_y in range(y_min, y_max):
            for sub_x in range(max(0, (x-search)), min(width, (x+search))):
                if sub_x == x and sub_y == y:
                    continue
                cell = game_state.map.get_cell(sub_x, sub_y)
                with open(testfile,"a") as f:
                    f.write(f"checking cell: {sub_x},{sub_y}\n")
                if cell.citytile is not None and not ignore_city:
                    with open(testfile,"a") as f:
                        f.write(f"{x},{y}:{fuel_amount}\n")
                    return (game_state.map.get_cell(x,y), 0)
                elif cell.has_resource():
                    if cell.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal(): continue
                    if cell.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium(): continue
                    if cell in unit_to_resource_dict.values(): continue    
                    fuel_amount += cell.resource.amount
        with open(testfile,"a") as f:
            f.write(f"{x},{y}:{fuel_amount}\n")
        return  (game_state.map.get_cell(x,y), fuel_amount)


def get_resource_map(game_state, player, width, height):
    resource_tiles: list[(Cell, int)] = []
    #with open(testfile,"a") as f:
    #    f.write("entered get_resource_map\n")
    for y in range(height):
        for x in range(width):
            possible_empty_tile = game_state.map.get_cell(x,y)
            if possible_empty_tile.resource == None and possible_empty_tile.road == 0 and possible_empty_tile.citytile == None:
                #with open(testfile,"a") as f:
                #    f.write("empty tile!\n")
                resource_tiles.append(get_resource_range(game_state, player, width, height, x, y))
    return resource_tiles

def get_close_resource(unit, resource_tiles, player):
    closest_dist = math.inf
    closest_resource_tile = None
    # if the unit is a worker and we have space in cargo, lets find the nearest resource tile and try to mine it
    for resource_tile in resource_tiles:
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.COAL and not player.researched_coal(): continue
        if resource_tile.resource.type == Constants.RESOURCE_TYPES.URANIUM and not player.researched_uranium(): continue
        if resource_tile in unit_to_resource_dict.values(): continue    

        dist = resource_tile.pos.distance_to(unit.pos)
        if dist < closest_dist:
            closest_dist = dist
            closest_resource_tile = resource_tile
    return closest_resource_tile

def get_new_city(game_state, player, unit, width, height):
    with open(testfile,"a") as f:
        f.write("entered get_new_city\n")
    closest_heuristic = 0
    closest_city_tile = None
    possible_tiles = get_resource_map(game_state, player, width, height)
    with open(testfile,"a") as f:
        f.write("Resource map completed\n")
    for empty_cell, resource_amount in possible_tiles:
        dist = empty_cell.pos.distance_to(unit.pos)
        if (resource_amount/dist) > closest_heuristic:
            closest_heuristic = (resource_amount/dist)
            closest_city_tile = empty_cell

    with open(testfile,"a") as f:
        f.write(f"Found a new build location:{closest_city_tile.pos}\n")
    return closest_city_tile

def get_city_capacity(game_state, player, width, height, x, y, days_remaing):
    cell, amount = get_resource_range(game_state, player, width, height, x, y, ignore_city=True)
    #print(type(amount))
    projection = min(int(amount/(2*days_remaing)), 9)
    
    # with open(logfile,"a") as f:
    #     f.write(f"fuel range:{amount}\n")
    #     f.write(f"days remaining:{days_remaing}\n")
    #     f.write(f"projected city capactiy:{projection}\n")
   
    return max(2, projection)

def get_close_city(player, unit):
    closest_dist = math.inf
    closest_city_tile = None
    for k, city in player.cities.items():
        for city_tile in city.citytiles:
            dist = city_tile.pos.distance_to(unit.pos)
            if dist < closest_dist:
                closest_dist = dist
                closest_city_tile = city_tile
    return closest_city_tile

def get_close_build_city(player, unit, build_list):
    closest_dist = math.inf
    closest_city_tile = None
    for k, city in player.cities.items():
        if k in build_list:
            for city_tile in city.citytiles:
                dist = city_tile.pos.distance_to(unit.pos)
                if dist < closest_dist:
                    closest_dist = dist
                    closest_city_tile = city_tile
    
    with open(citylog, "a") as f:
        if city is not None:
            f.write(f"Building city at {city}\n")
        else:
            f.write(f"couldnt find a place to build\n")

    return city, closest_city_tile

def find_empty_tile_next(near_what, game_state, observation):

    build_location = None

    dirs = [(1,0), (0,1), (-1,0), (0,-1)]
    # may later need to try: dirs = [(1,-1), (-1,1), (-1,-1), (1,1)] too.
    for d in dirs:
        try:
            possible_empty_tile = game_state.map.get_cell(near_what.pos.x+d[0], near_what.pos.y+d[1])
            #logging.INFO(f"{observation['step']}: Checking:{possible_empty_tile.pos}")

            if possible_empty_tile.resource == None and possible_empty_tile.road == 0 and possible_empty_tile.citytile == None and possible_empty_tile not in list(unit_to_build_dict.values()):
                build_location = possible_empty_tile
                with open(citylog,"a") as f:
                    f.write(f"{observation['step']}: Found build location:{build_location.pos}\n")

                return build_location
        except Exception as e:
            with open(citylog,"a") as f:
                f.write(f"{observation['step']}: While searching for empty tiles:{str(e)}\n")

    return build_location


def find_empty_tile_near(near_what, game_state, observation):

    build_location = None

    dirs = [(1,0), (0,1), (-1,0), (0,-1)]
    # may later need to try: dirs = [(1,-1), (-1,1), (-1,-1), (1,1)] too.
    for d in dirs:
        try:
            possible_empty_tile = game_state.map.get_cell(near_what.pos.x+d[0], near_what.pos.y+d[1])
            #logging.INFO(f"{observation['step']}: Checking:{possible_empty_tile.pos}")
            if possible_empty_tile.resource == None and possible_empty_tile.road == 0 and possible_empty_tile.citytile == None:
                build_location = possible_empty_tile
                with open(logfile,"a") as f:
                    f.write(f"{observation['step']}: Found build location:{build_location.pos}\n")

                return build_location
        except Exception as e:
            with open(logfile,"a") as f:
                f.write(f"{observation['step']}: While searching for empty tiles:{str(e)}\n")


    with open(logfile,"a") as f:
        f.write(f"{observation['step']}: Couldn't find a tile next to, checking diagonals instead...\n")

    dirs = [(1,-1), (-1,1), (-1,-1), (1,1)] 
    # may later need to try: dirs = [(1,-1), (-1,1), (-1,-1), (1,1)] too.
    for d in dirs:
        try:
            possible_empty_tile = game_state.map.get_cell(near_what.pos.x+d[0], near_what.pos.y+d[1])
            #logging.INFO(f"{observation['step']}: Checking:{possible_empty_tile.pos}")
            if possible_empty_tile.resource == None and possible_empty_tile.road == 0 and possible_empty_tile.citytile == None:
                build_location = possible_empty_tile
                with open(logfile,"a") as f:
                    f.write(f"{observation['step']}: Found build location: {build_location.pos}\n")

                return build_location
        except Exception as e:
            with open(logfile,"a") as f:
                f.write(f"{observation['step']}: While searching for empty tiles:{str(e)}\n")


    # PROBABLY should continue our search out with something like dirs = [(2,0), (0,2), (-2,0), (0,-2)]...
    # and so on


    with open(logfile,"a") as f:
        f.write(f"{observation['step']}: Something likely went wrong, couldn't find any empty tile\n")
    return None




def agent(observation, configuration):
    global game_state
    global build_location
    global unit_to_city_dict
    global unit_to_resource_dict
    global unit_to_build_dict
    global worker_positions
    global city_to_units_dict
    global city_capacity_dict
    global build_city_list

    ### Do not edit ###
    if observation["step"] == 0:
        game_state = Game()
        game_state._initialize(observation["updates"])
        game_state._update(observation["updates"][2:])
        game_state.id = observation.player
    else:
        game_state._update(observation["updates"])
    
    actions = []
    ### AI Code goes down here! ### 

    player = game_state.players[observation.player]
    opponent = game_state.players[(observation.player + 1) % 2]
    width, height = game_state.map.width, game_state.map.height
    resource_tiles = get_resource_tiles(game_state, width, height)
    workers = [u for u in player.units if u.is_worker()]

    turns_left = 360 - game_state.turn

    for w in workers:

        if w.id in worker_positions:
            worker_positions[w.id].append((w.pos.x, w.pos.y))
        else:
            worker_positions[w.id] = deque(maxlen=3)
            worker_positions[w.id].append((w.pos.x, w.pos.y))

        if w.id not in unit_to_city_dict:
            with open(logfile, "a") as f:
                f.write(f"{observation['step']} Found worker unaccounted for {w.id}\n")
            city_assignment = get_close_city(player, w)

            unit_to_city_dict[w.id] = city_assignment
        if w.id not in unit_to_build_dict:
            unit_to_build_dict[w.id] = None

    with open(logfile, "a") as f:
        f.write(f"{observation['step']} Worker Positions {worker_positions}\n")


    for w in workers:
        if w.id not in unit_to_resource_dict:
            with open(logfile, "a") as f:
                f.write(f"{observation['step']} Found worker w/o resource {w.id}\n")

            resource_assignment = get_close_resource(w, resource_tiles, player)
            unit_to_resource_dict[w.id] = resource_assignment
    
    with open(citylog, "a") as f:
        f.write(f"{observation['step']} Player cities {player.cities}\n")
    cities = player.cities.values()
    city_tiles = []

    with open(citylog, "a") as f:
        f.write(f"{observation['step']} Player build cities {build_city_list}\n")


    build_new_city = True
    #for city in cities:
    #    if len(city.citytiles) <= 2:
    #       build_new_city = False
    #    for c_tile in city.citytiles:
    #        city_tiles.append(c_tile)


    #remove cities that no longer exist
    remove_list = []
    build_city_object_list = []
    for city in build_city_list:
        if not player.cities.get(city):
            remove_list.append(city)
        else:
            build_city_object_list.append(player.cities[city])


    for city in remove_list:
        with open(citylog, "a") as f:
                f.write(f"{observation['step']} city {city} no longer exists... Being removed from build list\n")
        
        build_city_list.remove(city)

    #if city built recently add it to the build list
    #add cities that are under capacity to the build list
    for city in cities:
    #try to reduce these
    #possible issues two workers tring to build a city tile at once
    #expanding cities
        if(not city_capacity_dict.get(city.cityid)):
            x = city.citytiles[0].pos.x
            y = city.citytiles[0].pos.y
            city_capacity_dict[city.cityid] = get_city_capacity(game_state, player, width, height, x, y, turns_left)
            with open(citylog, "a") as f:
                f.write(f"{observation['step']} New city {city.cityid} at location {x},{y}: with capacity{city_capacity_dict[city.cityid]}\n")
        
        if 0 < city_capacity_dict[city.cityid] and city.cityid not in build_city_list:
            with open(citylog, "a") as f:
                f.write(f"{observation['step']} There is capacity at {city.cityid}: with capacity {city_capacity_dict[city.cityid]}\n")
        
            build_city_list.append(city.cityid)
            
        
        for c_tile in city.citytiles:
            city_tiles.append(c_tile)     


    build_city = False

    try:
        if len(workers) / len(city_tiles) >= 0.75:
            build_city = True
            
    except:
        build_city = False

    # we iterate over all our units and do something with them
    for unit in player.units:
        if unit.is_worker() and unit.can_act():
            try:
                last_positions = worker_positions[unit.id]
                if len(last_positions) >=2:
                    hm_positions = set(last_positions)
                    if len(list(hm_positions)) == 1:
                        with open(logfile, "a") as f:
                            f.write(f"{observation['step']} Looks like a stuck worker {unit.id} - {last_positions}\n")

                        actions.append(unit.move(random.choice(["n","s","e","w"])))
                        continue


                
                if unit.get_cargo_space_left() > 0:
                    intended_resource = unit_to_resource_dict[unit.id]
                    cell = game_state.map.get_cell(intended_resource.pos.x, intended_resource.pos.y)

                    if cell.has_resource():
                        actions.append(unit.move(unit.pos.direction_to(intended_resource.pos)))

                    else:
                        intended_resource = get_close_resource(unit, resource_tiles, player)
                        unit_to_resource_dict[unit.id] = intended_resource
                        actions.append(unit.move(unit.pos.direction_to(intended_resource.pos)))





                else:

                    if build_city:
                        #if build_new_city:
                        #    with open(log, "a") as f:
                        #        f.write(f"{observation['step']} We are going to build a new city!\n")

                        try:
                            associated_city_id = unit_to_city_dict[unit.id].cityid
                            unit_city = [c for c in cities if c.cityid == associated_city_id][0]
                            unit_city_fuel = unit_city.fuel
                            unit_city_size = len(unit_city.citytiles)

                            enough_fuel = (unit_city_fuel/unit_city_size) > 300
                        except: continue

                        with open(citylog, "a") as f:
                            f.write(f"{observation['step']} Build city stuff: {associated_city_id}, fuel {unit_city_fuel}, size {unit_city_size}, enough fuel {enough_fuel}\n")

                        if enough_fuel:
                            with open(citylog, "a") as f:
                                f.write(f"{observation['step']} We want to build a city!\n")
                            if unit.is_worker(): 
                                if unit_to_build_dict[unit.id] is None:
                                    while len(build_city_list)>0 or unit_to_build_dict[unit.id] is not None:
                                        city, empty_near = get_close_build_city(player, unit, build_city_object_list)
                                        build_location = find_empty_tile_next(empty_near, game_state, observation)
                                        if build_location is None:
                                            build_city_list.remove(city.cityid)
                                            build_city_object_list.remove(city)
                                            city_capacity_dict[city.cityid] = 0
                                        else:
                                            city_capacity_dict[city.cityid] = city_capacity_dict[city.cityid] -1
                                            if city_capacity_dict[city.cityid] <= 0:
                                                build_city_list.remove(city.cityid)
                                                build_city_object_list.remove(city)

                                if unit_to_build_dict[unit.id] is None:
                                    with open(citylog, "a") as f:
                                        f.write(f"{observation['step']} We are going to build a new city!!!!!\n")

                                    unit_to_build_dict[unit.id] = get_new_city(game_state, player, unit, width, height)
                                

                                if unit.pos == unit_to_build_dict[unit.id].pos:
                                    action = unit.build_city()
                                    actions.append(action)

                                    build_city = False
                                    unit_to_build_dict[unit.id] = None
                                    with open(logfile, "a") as f:
                                        f.write(f"{observation['step']} Built the city!\n")
                                    continue   

                                else:
                                    with open(logfile, "a") as f:
                                        f.write(f"{observation['step']}: Navigating to where we wish to build!\n")

                                    #actions.append(unit.move(unit.pos.direction_to(build_location.pos)))
                                    dir_diff = (unit_to_build_dict[unit.id].pos.x-unit.pos.x, unit_to_build_dict[unit.id].pos.y-unit.pos.y)
                                    xdiff = dir_diff[0]
                                    ydiff = dir_diff[1]

                                    # decrease in x? West
                                    # increase in x? East
                                    # decrease in y? North
                                    # increase in y? South

                                    if abs(ydiff) > abs(xdiff):
                                        # if the move is greater in the y axis, then lets consider moving once in that dir
                                        check_tile = game_state.map.get_cell(unit.pos.x, unit.pos.y+np.sign(ydiff))
                                        if check_tile.citytile == None:
                                            if np.sign(ydiff) == 1:
                                                actions.append(unit.move("s"))
                                            else:
                                                actions.append(unit.move("n"))

                                        else:
                                            # there's a city tile, so we want to move in the other direction that we overall want to move
                                            if np.sign(xdiff) == 1:
                                                actions.append(unit.move("e"))
                                            else:
                                                actions.append(unit.move("w"))

                                    else:
                                        # if the move is greater in the y axis, then lets consider moving once in that dir
                                        check_tile = game_state.map.get_cell(unit.pos.x+np.sign(xdiff), unit.pos.y)
                                        if check_tile.citytile == None:
                                            if np.sign(xdiff) == 1:
                                                actions.append(unit.move("e"))
                                            else:
                                                actions.append(unit.move("w"))

                                        else:
                                            # there's a city tile, so we want to move in the other direction that we overall want to move
                                            if np.sign(ydiff) == 1:
                                                actions.append(unit.move("s"))
                                            else:
                                                actions.append(unit.move("n"))


                                    continue

                        elif len(player.cities) > 0:
                            if unit.id in unit_to_city_dict and unit_to_city_dict[unit.id] in city_tiles:
                                move_dir = unit.pos.direction_to(unit_to_city_dict[unit.id].pos)
                                actions.append(unit.move(move_dir))

                            else:
                                unit_to_city_dict[unit.id] = get_close_city(player,unit)
                                move_dir = unit.pos.direction_to(unit_to_city_dict[unit.id].pos)
                                actions.append(unit.move(move_dir))




                    # if unit is a worker and there is no cargo space left, and we have cities, lets return to them
                    elif len(player.cities) > 0:
                        if unit.id in unit_to_city_dict and unit_to_city_dict[unit.id] in city_tiles:
                            move_dir = unit.pos.direction_to(unit_to_city_dict[unit.id].pos)
                            actions.append(unit.move(move_dir))

                        else:
                            unit_to_city_dict[unit.id] = get_close_city(player,unit)
                            move_dir = unit.pos.direction_to(unit_to_city_dict[unit.id].pos)
                            actions.append(unit.move(move_dir))
            except Exception as e:
                with open(logfile, "a") as f:
                    f.write(f"{observation['step']}: Unit error {str(e)} \n")



    can_create = len(city_tiles) - len(workers)
    #identifies city capacity
    #for city in cities:
        #try to reduce these
        #possible issues two workers tring to build a city tile at once
        #expanding cities
    #    x = city.citytiles[0].pos.x
    #    y = city.citytiles[0].pos.y
    #    if(not city_capacity_dict.get(city.cityid)):
    #        city_capacity_dict[city.cityid] = get_city_capacity(game_state, player, width, height, x, y, turns_left)

    if len(city_tiles) > 0:
        for city_tile in city_tiles:
            if city_tile.can_act():
                if can_create > 0:
                    actions.append(city_tile.build_worker())
                    can_create -= 1
                    with open(logfile, "a") as f:
                        f.write(f"{observation['step']}: Created and worker \n")
                else:
                    actions.append(city_tile.research())
                    with open(logfile, "a") as f:
                        f.write(f"{observation['step']}: Doing research! \n")


    if observation["step"] == 359:
        with open(statsfile,"a") as f:
            f.write(f"{len(city_tiles)}\n")

    
    return actions