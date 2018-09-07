#!/usr/bin/env python3

import asyncio
import json
import argparse
from datetime import datetime
import struct 
import random
from copy import deepcopy

CLIENT_MSG_LEN = 2
SNEK_SERVER = None

# Message types
MSG_TYPE_JOIN   = 0
MSG_TYPE_BOARD  = 1
MSG_TYPE_UPDATE = 2
MSG_TYPE_INFO   = 3
MSG_TYPE_TXT    = 4

JOIN_REJECT = 255

INFO_TYPE_JOIN = 0
INFO_TYPE_KILL = 1

# Directions
NORTH = 1
EAST = 2
SOUTH = 3
WEST = 4

# Square types
FOOD  = 33
BLANK = 0

STARTING_MIN_FOOD = 4
FOOD_MULTIPLIER = 2
MAX_SNEKS = 16

# Causes of death
DISCONNECT = 0
OTHER      = 1

# Game parameters
TICKS_PER_SECOND = 10

class Snek():
    def __init__(self, snek_id, board, transport):
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
        self.transport = transport

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
        self.peername = transport.get_extra_info('peername')
        print('{}:{} connected.'.format(*self.peername))
        self.transport = transport
        
    def connection_lost(self, exc):
        if exc:
            print(exc)
        if self.snek and self.snek.blocks:
            SNEK_SERVER.kill_snek(self.snek, DISCONNECT)
        print("{}:{} disconnected.".format(*self.peername))

    # Got message from client.
    def data_received(self, data):
        if data and CLIENT_MSG_LEN == len(data):

            # Parse command
            snek_id = int(data[0])
            cmd = int(data[1])

            # Command is a join request.
            if 0 == snek_id and 0 == cmd:

                # Connection already has a snek but requested a new one. 
                # That is not legitimate.
                if self.snek and self.snek.blocks:
                    print("ignoring bad join request")
                    return

                # Assign a snek id, iff the server isn't full of sneks.
                if 0 != len(self.available_snek_ids):

                    assigned_snek_id = self.available_snek_ids.pop()
                    print("assigning snek id %i"%assigned_snek_id)

                    # Spawn or respawn snek
                    new_snek = Snek(assigned_snek_id, self.board, self.transport)
                    self.snek = new_snek

                    self.sneks[assigned_snek_id] = new_snek

                    # Send client its assigned snek id
                    msg = self._msg_join_accept(assigned_snek_id)
                    self.transport.write(msg)

                    # Send whole board one time
                    msg = self._msg_board()
                    self.transport.write(msg)
                    
                    # Add this connection to the list of connections
                    # so that is starts receiving board updates
                    self.connections += [self.transport]

                # Server is full of sneks. Close failed request.
                else:
                    msg = self._msg_join_reject()
                    self.transport.write(msg)
                    self.transport.close()

            elif self.snek and self.snek.blocks:
                if snek_id != self.snek.snek_id or cmd < 1 or cmd > 4:
                    print("ignoring bad command")
                    return

                # Handle directional commands.
                self.snek.change_direction(cmd)

    def _msg_join_accept(self, snek_id):
        return bytes([MSG_TYPE_JOIN, snek_id])

    def _msg_join_reject(self):
        return bytes([MSG_TYPE_JOIN, JOIN_REJECT])

    # Snek data goes in board messages and update messages
    def _msg_field_snek_data(self):
        msg = bytes([len(self.sneks.keys())])
        for snek in self.sneks.values():
            msg += bytes([snek.snek_id])
            msg += snek.score.to_bytes(2, byteorder='big')
            msg += b'\x00\x00'
        return msg

    def _msg_board(self):
        msg = self._msg_field_snek_data()
        for y in range(len(self.board)):
            for x in range(len(self.board[0])):
                msg += bytes([self.board[y][x]])

        msg = bytes([MSG_TYPE_BOARD]) + len(msg).to_bytes(4, byteorder='big') + msg 
        return msg


# The SnekServer has the connections, the sneks, and runs the game.
class SnekServer():
    def __init__(self, connections, sneks, available_snek_ids, food_count, board):
        self.connections = connections
        self.sneks = sneks
        self.available_snek_ids = available_snek_ids
        self.food_count = food_count
        self.board = board
        self.last_board = board

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

    def _broadcast(self, msg):
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
        msg = self._msg_info(INFO_TYPE_KILL, snek.snek_id)
        self._broadcast(msg)
        self.available_snek_ids.insert(0, snek.snek_id)
        self.connections.remove(snek.transport)
        snek.die()
        self.sneks.pop(snek.snek_id)

    def _feed_snek(self, snek):
        snek.eat()
        tail = snek.blocks[-1]
        self.board[tail[2]][tail[1]] = tail[0]
        self.food_count -= 1

    def _spawn_food(self):
        MIN_FOOD = max(len(self.sneks.keys()) * FOOD_MULTIPLIER, STARTING_MIN_FOOD)
        while MIN_FOOD > self.food_count:
            x = random.randint(0, 79)
            y = random.randint(0, 39)
            if BLANK == self.board[y][x]:
                self.board[y][x] = FOOD
                self.food_count += 1

    # This will advance the game one "tick" and tell the clients about it.
    def _update(self):
        self._cache_board()
        self._slither_the_sneks()
        msg = self._msg_update()
        self._broadcast(msg)

    # Snek data goes in board messages and update messages
    def _msg_field_snek_data(self):
        msg = bytes([len(self.sneks.keys())])
        for snek in self.sneks.values():
            msg += bytes([snek.snek_id])
            msg += snek.score.to_bytes(2, byteorder='big')
            msg += b'\x00\x00'
        return msg

    def _msg_update(self):
        msg = self._msg_field_snek_data()
        for y in range(len(self.board)):
            for x in range(len(self.board[0])):
                new_square = self.board[y][x]
                old_square = self.last_board[y][x]
                if old_square != new_square:
                    msg += bytes([x, y, new_square])

        msg = bytes([MSG_TYPE_UPDATE]) + len(msg).to_bytes(4, byteorder='big') + msg 
        return msg
    
    # Caching the board from the last game tick enables sending 
    # board updates to clients rather than the entire board.
    def _cache_board(self):
        self.last_board = deepcopy(self.board)

    def _msg_info(self, info_type, snek_id):
       msg = bytes([MSG_TYPE_INFO, info_type, snek_id])
       return msg

@asyncio.coroutine
def update_periodically():
    while True:
        yield from asyncio.sleep(1/TICKS_PER_SECOND)
        SNEK_SERVER._update()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Server settings")
    parser.add_argument("--addr", default="127.0.0.1", type=str)
    parser.add_argument("--port", default=55555, type=int)
    args = vars(parser.parse_args())

    # Initialize the server.
    connections = list()
    sneks = dict()
    available_snek_ids = [i for i in range(MAX_SNEKS-1, -1, -1)]
    food_count = 0
    board = [[0 for i in range(80)] for j in range(40)]

    SNEK_SERVER = SnekServer(connections, sneks, available_snek_ids, food_count, board)

    # Run the server.
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
