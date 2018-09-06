#!/usr/bin/python

import socket, struct, time, random

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('localhost', 55553))
sock.listen(5)
def get_fake_sneks():
    sneks = '\x16'
    for i in range(1,17):
        sneks += chr(i) + '\x00\x00\x00\x00'
    return sneks

def get_fake_board():
    board = ''
    for r in range(0, random.randint(1,50)):
        x = random.randint(0,79)
        y = random.randint(0,39)
        c = random.randint(1,32)
        board += chr(x) + chr(y) + chr(c)
    return board

while True:
    conn, addr = sock.accept()
    conn.send('\x01\x01')
    while True:
        try:
            msg = get_fake_sneks() + get_fake_board()
            msg = struct.pack('!i', len(msg)) + msg
            conn.send(msg)
            time.sleep(0.25)
        except Exception as e:
            print e
            break

sock.close()   
