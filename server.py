#!/usr/bin/env python3

import asyncio
import json
import argparse
from datetime import datetime
import struct 
import random

CLIENT_MSG_LEN = 2
SNEK_SERVER = None

NORTH = 1
EAST = 2
SOUTH = 3
WEST = 4

FOOD = 33

MAX_FOOD = 4

class Snek():
    def __init__(self, snek_id):
        self.snek_id = snek_id
        direction = random.randint(1, 4)
        self.direction = direction
        # [block type (head, body), x, y, direction]
        x = random.randint(5, 75)
        y = random.randint(5, 35)
        self.blocks = [(snek_id*2+1, x, y, self.direction)]
        if NORTH == direction:
            y += 1 
        elif EAST == direction:
            x -= 1 
        elif SOUTH == direction:
            y -= 1 
        elif WEST == direction:
            x += 1

        self.blocks.append((0, x, y, direction))
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

        # Convert the old head to be a body block. If the snek is just a head, it will get truncated later.
        old_head = old_blocks[0]
        self.blocks[0] = (self.snek_id*2, old_head[1], old_head[2], old_head[3])
        
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

        self.blocks = [(self.snek_id*2+1, new_x, new_y, self.direction)] + self.blocks

        # Store the old tail as a blank block to:
        #   1) enable restoring it if the snek ate this move,
        #   2) transmit the update to the snek server.
        old_tail = self.blocks[-2]
        self.blocks = self.blocks[:-2] + [(0, old_tail[1], old_tail[2], old_tail[3])]
        print("blocks: "  + str(self.blocks))
        # Return the changes
        return [block for block in self.blocks if block not in set(old_blocks)] # Say that five times fast.

    def change_direction(self, direction):
        self.direction = direction

    def die(self):
        self.blocks = list()

    def eat(self):
        self.score += 1
        tail = self.blocks[-1]
        print("blocks....: " + str(self.blocks))
        self.blocks = self.blocks[:-1]
        new_x = tail[1]
        new_y = tail[2]
        direction = tail[3]
        self.blocks.append((self.snek_id*2+2, new_x, new_y, direction))
        if NORTH == direction:
            new_y += 1 
        elif EAST == direction:
            new_x -= 1 
        elif SOUTH == direction:
            new_y -= 1 
        elif WEST == direction:
            new_x += 1

        self.blocks.append((0, new_x, new_y, direction))
        print("blocks after eat: " + str(self.blocks))

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
        
        # Assign a snek id, iff the server isn't full of sneks.
        if 0 != len(self.available_snek_ids):
            assigned_snek_id = self.available_snek_ids[0]
            self.available_snek_ids = self.available_snek_ids[1:]
            new_snek = Snek(assigned_snek_id)
            self.sneks[assigned_snek_id] = new_snek
            self.snek = new_snek
            self.transport.write(bytes([assigned_snek_id])*2)
            self.connections += [transport]

        # Close failed requests.
        else:
            self.transport.write(b'\xff\xff')
            self.transport.close()

    def connection_lost(self, exc):
        self.connections.remove(self.transport)
        if exc:
            print(exc)
        err = "{}:{} disconnected".format(*self.peername)
        if self.snek:
            self.snek.die()
        print(err)

    def data_received(self, data):
        if data and CLIENT_MSG_LEN == len(data):
            print("got: " + str(data))
            snek_id = int(data[0])
            cmd = int(data[1])
            print("snek id = %i"%snek_id)
            print("cmd = %i"%cmd)
            if self.snek:
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

                # Detect other types of conflicts
                applicable_diffs = [d for d in diffs if d != diff and d[1] == new_x and d[2] == new_y]
                if 0 == len(applicable_diffs):
                    applicable_diffs.append((self.board[new_y][new_x], new_x, new_y, 0))

                # The only conflict is a blank square. Do nothing exciting.
                if 1 == len(applicable_diffs) and 0 == applicable_diffs[0][0]:
                    continue

                print(applicable_diffs)
                for applicable_diff in applicable_diffs:
                    square_type = applicable_diff[0]
                    # Head hit body square or head square
                    if 16 >= square_type and 0 < square_type:
                        print("bar")
                        sneks_to_kill.append(self.sneks[snek_id])
                    # Head hit food square
                    elif 32 < square_type:
                        sneks_to_feed.append(self.sneks[snek_id])

        sneks_to_feed = [s for s in sneks_to_feed if s not in set(sneks_to_kill)] # snek

        for snek in sneks_to_kill:
            self._kill_snek(snek)

        for snek in sneks_to_feed:
            self._feed_snek(snek)

        self._commit_sneks()
        self._spawn_food()

    def _commit_sneks(self):
        for snek in self.sneks.values():
            print("commit these blocks: " + str(snek.blocks))
            for block in snek.blocks:
                x = block[1]
                y = block[2]
                self.board[y][x] = block[0]
                print("%i, %i is now %i"%(x,y,self.board[y][x]))

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

    def _kill_snek(self, snek):
        print("killin snek %i"%snek.snek_id)
        return
        for block in snek.blocks:
            if 0 != block[0]:
                x = block[1]
                y = block[2]
                self.board[x][y] = FOOD
        snek.die()
        self.available_snek_ids.append(snek.snek_id)
        del self.sneks[snek.snek_id]

    def _feed_snek(self, snek):
        snek.eat()
        tail = snek.blocks[-1]
        self.board[tail[2]][tail[1]] = tail[0]
        self.food_count -= 1

    def _spawn_food(self):
        while MAX_FOOD > self.food_count:
            x = random.randint(0, 79)
            y = random.randint(0, 39)
            if 0 == self.board[y][x]:
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
    available_snek_ids = [i for i in range(0, 16)]
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
