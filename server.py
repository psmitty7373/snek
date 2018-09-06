#!/usr/bin/env python3

import asyncio
import json
import argparse
from datetime import datetime
import struct 
import random

CLIENT_MSG_LEN = 2
SNEK_SERVER = None

# Directions
NORTH = 1
EAST = 2
SOUTH = 3
WEST = 4

# Square types
FOOD  = 33
BLANK = 0

STARTING_MIN_FOOD = 4
MAX_SNEKS = 16

# Causes of death
DISCONNECT = 0
OTHER      = 1

class Snek():
    def __init__(self, snek_id, board):
        self.snek_id = snek_id
        self.head_value = snek_id*2+1
        self.body_value = snek_id*2+2
        direction = random.randint(1, 4)
        self.direction = direction

        # Cache the direction from the begining of the move to ignore turning back on self
        self.last_direction = direction

        # Don't spawn on top of things
        x = random.randint(15, 65)
        y = random.randint(15, 25)
        while 0 != board[y][x]:
            x = random.randint(15, 65)
            y = random.randint(15, 25)

        # [block type (head, body), x, y, direction]
        self.blocks = [(self.head_value, x, y, direction)]

        self._append_null_tail()
        self.score = 0
        self.hydration = 50
        self.salt = 50
        self.tabasco = False
        self.poisoned = False

    def poison(self):
        self.poisoned = True

    def unpoison(self):
        self.poisoned = False

    def armor(self):
        self.tabasco = True

    def unarmor(self):
        self.tabasco = False

    def hydrate(self, camelbaks):
        self.hydration += camelbaks

    def dehydrate(self, camelbaks):
        self.hydration -= camelbaks
    
    def slither(self):
        old_blocks = self.blocks

        if not old_blocks:
            return []

        old_head = old_blocks[0]
        
        # New head
        new_x = old_head[1]
        new_y = old_head[2]

        if NORTH == self.direction:
            new_y -= 1 
        elif EAST == self.direction:
            new_x += 1 
        elif SOUTH == self.direction:
            new_y += 1 
        elif WEST == self.direction:
            new_x -= 1

        new_head = (self.head_value, new_x, new_y, self.direction)

        tail = self.blocks[-2]
        new_null_tail = (BLANK, tail[1], tail[2], tail[3])

        if 2 == len(old_blocks):
            self.blocks = [new_head] + [new_null_tail]
        else:
            new_neck = (self.body_value, old_head[1], old_head[2], old_head[3])
            self.blocks = [new_head] + [new_neck] + self.blocks[1:-2] + [new_null_tail]

        self.last_direction = self.direction

        # Return the changes
        return [block for block in self.blocks if block not in set(old_blocks) and BLANK != block[0]] # Say that five times fast.

    def change_direction(self, direction):
        # Ignore turning back on self
        if 0 != (direction + self.last_direction) % 2:
            self.direction = direction

    def die(self):
        self.blocks = None

    def eat(self):
        self.score += 1
        terminal_block = self.blocks[-1]
        if BLANK != terminal_block[0]:
            self._append_null_tail()
            terminal_block = self.blocks[-1]

        x = terminal_block[1]
        y = terminal_block[2]
        direction = terminal_block[3]

        self.blocks = self.blocks[:-1]
        self.blocks.append((self.body_value, x, y, direction))
        self._append_null_tail()

    # The null block at the end of a snek.blocks serves as a placeholder for growth
    def _append_null_tail(self):
        terminal_block = self.blocks[-1]
        # Null block already exists
        if BLANK == terminal_block[0]:
            return

        # Position null block based on direction of terminal block
        
        direction = terminal_block[3]
        x = terminal_block[1]
        y = terminal_block[2]
        if NORTH == direction:
            y += 1
        elif EAST == direction:
            x -= 1 
        elif SOUTH == direction:
            y -= 1 
        elif WEST == direction:
            x += 1

        self.blocks.append((BLANK, x, y, direction))
 

class SnekProtocol(asyncio.Protocol):
    def __init__(self, connections, sneks, available_snek_ids, food_count, board):
        self.connections = connections
        self.sneks = sneks
        self.available_snek_ids = available_snek_ids
        self.food_count = food_count
        self.board = board
        self.peername = ""
        self.snek = None

    def connection_made(self, transport):
        self.peername = transport.get_extra_info('sockname')
        self.transport = transport
        
    def connection_lost(self, exc):
        self.connections.remove(self.transport)
        if exc:
            print(exc)
        err = "{}:{} disconnected".format(*self.peername)
        if self.snek and self.snek.blocks:
            SNEK_SERVER.kill_snek(self.snek, DISCONNECT)
        print(err)

    def data_received(self, data):
        if data and CLIENT_MSG_LEN == len(data):
            snek_id = int(data[0])
            cmd = int(data[1])
            if 0 == snek_id and 0 == cmd and not self.snek:
                # Assign a snek id, iff the server isn't full of sneks.
                if 0 != len(self.available_snek_ids):
                    assigned_snek_id = self.available_snek_ids.pop()
                    print("assigning snek id %i"%assigned_snek_id)
                    new_snek = Snek(assigned_snek_id, self.board)
                    self.sneks[assigned_snek_id] = new_snek
                    self.snek = new_snek
                    self.transport.write(bytes([assigned_snek_id])*2)
                    self.connections += [self.transport]

                # Close failed requests.
                else:
                    self.transport.write(b'\xff\xff')
                    self.transport.close()

            elif self.snek:
                if snek_id != self.snek.snek_id or cmd < 1 or cmd > 4:
                    print("ignoring bad command")
                    return

                # Handle directional commands.
                self.snek.change_direction(cmd)

# The SnekServer has the connections, the sneks, and runs the game.
class SnekServer():
    def __init__(self, connections, sneks, available_snek_ids, food_count, board):
        self.connections = connections
        self.sneks = sneks
        self.available_snek_ids = available_snek_ids
        self.food_count = food_count
        self.board = board

    def _slither_the_sneks(self):
        diffs = list()
        sneks_to_kill = list()
        sneks_to_feed = list()

        # Advance the sneks!
        for snek in self.sneks.values():
            diffs += snek.slither()

        # Process the changes
        for diff in diffs:
            # If the diff is a head block
            if 1 == diff[0] % 2:
                snek_id = diff[0] // 2
                new_x = diff[1]
                new_y = diff[2]

                # Border
                if new_x < 0 or new_x >= 80 or new_y < 0 or new_y >= 40:
                    sneks_to_kill.append(self.sneks[snek_id])
                    continue

                # Detect other types of conflicts
                conflicts = [d for d in diffs if d != diff and d[1] == new_x and d[2] == new_y]
                if 0 == len(conflicts):
                    conflicts.append((self.board[new_y][new_x], new_x, new_y, 0))

                # The only conflict is a blank square. Do nothing exciting.
                if 1 == len(conflicts) and BLANK == conflicts[0][0]:
                    continue

                for conflict in conflicts:
                    square_type = conflict[0]
                    # Head hit body square or head square
                    if MAX_SNEKS*2 >= square_type and 0 < square_type:
                        sneks_to_kill.append(self.sneks[snek_id])
                        continue
                    # Head hit food square
                    elif 32 < square_type:
                        sneks_to_feed.append(self.sneks[snek_id])

        sneks_to_feed = [s for s in sneks_to_feed if s not in set(sneks_to_kill)] # snek

        for snek in sneks_to_kill:
            self.kill_snek(snek, OTHER)

        for snek in sneks_to_feed:
            self._feed_snek(snek)

        self._commit_sneks()
        self._spawn_food()

    def _commit_sneks(self):
        for snek in self.sneks.values():
            for block in snek.blocks:
                x = block[1]
                y = block[2]
                self.board[y][x] = block[0]

    def _broadcast_update(self):
        msg = bytes()
        msg += bytes([len(self.sneks.keys())])
        for snek in self.sneks.values():
            msg += bytes([snek.snek_id])
            msg += snek.score.to_bytes(2, byteorder='big')
            msg += b'\x00\x00'
        for y in range(len(self.board)):
            for x in range(len(self.board[0])):
                msg += bytes([x, y, self.board[y][x]])

        msg = len(msg).to_bytes(4, byteorder='big') + msg 
            
        for connection in self.connections:
            connection.write(msg)

    def kill_snek(self, snek, cause_of_death):
        snek_id = snek.snek_id
        for block in snek.blocks:
            if (BLANK != block[0] and DISCONNECT == cause_of_death) or (snek.head_value != block[0] and DISCONNECT != cause_of_death):
                x = block[1]
                y = block[2]
                if random.randint(0, 1):
                    self.board[y][x] = FOOD
                    self.food_count += 1
                else:
                    self.board[y][x] = BLANK
        self.available_snek_ids.insert(0, snek.snek_id)
        snek.die()
        self.sneks.pop(snek.snek_id)

    def _feed_snek(self, snek):
        snek.eat()
        tail = snek.blocks[-1]
        self.board[tail[2]][tail[1]] = tail[0]
        self.food_count -= 1

    def _spawn_food(self):
        MIN_FOOD = max(len(self.sneks.keys()) * 1.5, STARTING_MIN_FOOD)
        while MIN_FOOD > self.food_count:
            x = random.randint(0, 79)
            y = random.randint(0, 39)
            if BLANK == self.board[y][x]:
                self.board[y][x] = FOOD
                self.food_count += 1

    def _update(self):
        self._slither_the_sneks()
        self._broadcast_update()

@asyncio.coroutine
def update_periodically():
    while True:
        yield from asyncio.sleep(0.2)
        SNEK_SERVER._update()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Server settings")
    parser.add_argument("--addr", default="127.0.0.1", type=str)
    parser.add_argument("--port", default=55555, type=int)
    args = vars(parser.parse_args())

    connections = list()
    sneks = dict()
    available_snek_ids = [i for i in range(MAX_SNEKS-1, -1, -1)]
    food_count = 0
    board = [[0 for i in range(80)] for j in range(40)]

    SNEK_SERVER = SnekServer(connections, sneks, available_snek_ids, food_count, board)

    loop = asyncio.get_event_loop()
    coro = loop.create_server(lambda: SnekProtocol(connections, sneks, available_snek_ids, food_count, board), args["addr"], args["port"])
    server = loop.run_until_complete(coro)

    print('Serving on {}:{}'.format(*server.sockets[0].getsockname()))
    asyncio.async(update_periodically())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass

    server.close()
    loop.run_until_complete(server.wait_closed())
    loop.close()
