#!/usr/bin/env python3

import curses, locale, select, signal, socket, struct, sys, time

locale.setlocale(locale.LC_ALL, '')

MSG_TYPE_JOIN = 0
MSG_TYPE_BOARD = 1
MSG_TYPE_UPDATE = 2
MSG_TYPE_INFO = 3
MSG_TYPE_TXT = 4

INFO_TYPE_JOIN = 0
INFO_TYPE_KILL = 1

NAME = 0
SYMBOL = 1
COLOR = 2

the_foods = {
        33: ('SALT', '.', 231),
        34: ('CRACKER', '#', 227),
        35: ('TABASCO', 'i', 124),
        36: ('SNACK_BREAD', 'B', 180),
        37: ('OMLET', '_', 185),
        38: ('WATER', 'U', 123)
        }

the_sneks = {
        0: ('Bob', 'O@', 9),
        1: ('Alice', 'O@', 9),
        2: ('Fred', 'O@', 10),
        3: ('Karen', 'O@', 11),
        4: ('Chris', 'O@', 12),
        5: ('Mary', 'O@', 13),
        6: ('Pete', 'O@', 14),
        7: ('Janice', 'O@', 15),
        8: ('Snuffy', 'O&', 238),
        9: ('Jody', 'O&', 160),
        10: ('Leo', 'O&', 155),
        11: ('Tricia', 'O&', 220),
        12: ('Scott', 'O&', 21),
        13: ('Matt', 'O&', 129),
        14: ('Morne', 'O&', 159),
        15: ('Tammi', 'O&', 252),
        16: ('Dave', 'O&', 56)
        }

WHITEONGRAY = 128

helpmsg = '''
Welcome to Snek 0.001 Alpha Early Access
==========================================================
Snek is a multiplayer highly competitive snek on
snek action game.  Only the most highly motivated,
battle focused, and hydrated snek will survive.

It would behoove you to read the following instructions:
==========================================================
1. Use the arrow keys to maneuver your snek around
the battle space.

2. Maintain situational awareness at all times,
collisions with other sneks or walls will reduce your
combat power to 0.  You will fail.

3. Consume food to multiply your combat power.  Make
sure to do PT.

4. DRINK WATER.

5. Press 'q' to pay respects to your inner weakness.

Food:
=========================================================
. = MRE Salt.  Consume lightly, will reduce your
hydration level.
# = MRE Cracker.  Try to eat it all without drinking.
i = MRE Tabasco.  Will make you immune to poison for
a short time.
B = MRE Snack Bread.  Yum.
_ = MRE Omlet.  Only the finest for your snek.
U = MRE Water.  Drink it.
$ = MRE Jalepeno Cheese Spread.  Basically money.

~~~ Press SPACE to begin game! ~~~~
'''

class snekception(Exception): pass

class renderer:
    screen = None
    game_window = None
    messagebar = None
    sidebar = None
    helpbox = None

    def init_curses(self):

        self.screen = curses.initscr()
        height, width = self.screen.getmaxyx()

        if height < 56 or width < 96:
            raise snekception('Sorry, Snek requires a 96x56 console window.  Go big or go home.\n')

        curses.cbreak()
        curses.noecho()

        # don't show the cursor
        curses.curs_set(0)
        self.screen.keypad(1)

        # don't delay on keyboard input
        self.screen.nodelay(1)

        # init color
        curses.start_color()
        curses.use_default_colors()

        # init snek colors
        for i in the_sneks.keys():
            curses.init_pair(i, the_sneks[i][COLOR], curses.COLOR_BLACK)

        # init food colors
        for i in the_foods.keys():
            curses.init_pair(i, the_foods[i][COLOR], curses.COLOR_BLACK)

        # init other colors
        curses.init_pair(WHITEONGRAY, curses.COLOR_WHITE, 234)

        # init game window
        self.game_window = curses.newwin(42,83,0,0)
        self.game_window.scrollok(False)
        self.sidebar = curses.newwin(42,43,0,83)
        self.messagebar = curses.newwin(22,125,42,0)
        self.helpbox = curses.newwin(41,62,5,30)

    def shutdown(self):
        curses.endwin()

# recv n characters from the socket
def recv_n(sock, recv_len):
    try:
        buf = b''
        while len(buf) < recv_len:
            r, w, e = select.select([sock], [], [], 0)
            if sock in r:
                t_buf = sock.recv(recv_len - len(buf))
            if not t_buf: # disconnected
                raise Exception('Connection lost.')
            buf += t_buf

            if len(buf) != recv_len: # recv error
                sock.close()
                raise Exception('Recieve error.')

    except Exception as e:
        sys.stderr.write(str(e))

    return buf

class snek:
    health = 0
    score = 0
    snek_id = 0

    def __init__(self, snek_id = None):
        if snek_id != None:
            self.snek_id = snek_id

class game:
    sock = None
    my_snek = snek()
    sneks = [snek(s) for s in range(0,16)]
    my_renderer = renderer()
    messages = []
    messages.insert(0, 'Welcome to Snek!')
    dirty = True
    board = [[0 for x in range(0,80)] for y in range(0,40)]
    show_help = True

    def draw_help(self):
        if self.show_help:
            self.my_renderer.helpbox.erase()
            helplines = helpmsg.split('\n')
            for y in range(0,40):
                if y == 0 or y == 39:
                    self.my_renderer.helpbox.addstr(y,0,'+' + '-' * 60 + '+', curses.color_pair(WHITEONGRAY))
                elif y == 1 or y == 38:
                    self.my_renderer.helpbox.addstr(y,0,'++' + '-' * 58 + '++', curses.color_pair(WHITEONGRAY))
                elif y - 2 < len(helplines):
                    self.my_renderer.helpbox.addstr(y,0,'||' + helplines[y-2].center(58) + '||', curses.color_pair(WHITEONGRAY))
                else:
                    self.my_renderer.helpbox.addstr(y,0,'||' + ''.ljust(58) + '||', curses.color_pair(WHITEONGRAY))
            self.my_renderer.helpbox.refresh()

    def draw_game(self):
        self.draw_board()
        self.draw_sidebar()
        self.draw_messagebar()
        self.draw_help()

    def draw_board(self):
        if self.dirty:
            self.my_renderer.game_window.erase()
            self.my_renderer.game_window.addstr(0,0,'+' + '-' * 80 + '+')
            y = 1
            for y_line in self.board:
                x = 1
                self.my_renderer.game_window.addch(y,0,'|')
                for x_elem in y_line:
                    # draw sneks
                    if x_elem > 0 and x_elem < 33:
                        snek_id = (x_elem if x_elem % 2 == 0 else x_elem + 1) // 2
                        self.my_renderer.game_window.addstr(y, x, the_sneks[snek_id][SYMBOL][x_elem % 2], curses.color_pair(snek_id))
                    # draw foodz
                    elif x_elem > 32 and x_elem < 64:
                        self.my_renderer.game_window.addstr(y, x, the_foods[x_elem][SYMBOL], curses.color_pair(x_elem))
                    x += 1
                self.my_renderer.game_window.addch(y,81,'|')
                y += 1
            self.my_renderer.game_window.addnstr(41,0,'+' + '-' * 80 + '+', 82)
            self.my_renderer.game_window.refresh()
            self.dirty = False

    def draw_sidebar(self):
        self.my_renderer.sidebar.erase()
        for y in range(0, 42):
            # draw header and footer
            if y == 0 or y == 41:
                self.my_renderer.sidebar.addstr(y,0,'+' + '-' * 40 + '+')
            # draw body of side bar
            else:
                if y > 0 and y < 17:
                    self.my_renderer.sidebar.addstr(y,0,'| ')
                    self.my_renderer.sidebar.addstr(the_sneks[y][NAME].ljust(13) + '!!!!!!!!'.ljust(13) + str('{:010}'.format(self.sneks[y-1].score)).rjust(12), curses.color_pair(y))
                    self.my_renderer.sidebar.addstr(' | ')
                else:
                    self.my_renderer.sidebar.addstr(y,0,'|' + (' ' * 40) + '|')
        self.my_renderer.sidebar.refresh()

    def draw_messagebar(self):
        self.my_renderer.messagebar.erase()
        for y in range(0,13):
            # draw header and footer
            if y == 0 or y == 12:
                self.my_renderer.messagebar.addstr(y,0,'+' + '-' * 123 + '+')
            # draw body of message body
            else:
                if len(self.messages) > y - 1 and self.messages[y-1]:
                    self.my_renderer.messagebar.addstr(y,0,'|' + (' ' + self.messages[y-1]).ljust(123) + '|')
                else:
                    self.my_renderer.messagebar.addstr(y,0,'|' + ''.ljust(123) + '|')
        self.my_renderer.messagebar.refresh()

    def process_msg(self, msg_type, msg):
        if msg_type == MSG_TYPE_JOIN:
            pass
        elif msg_type == MSG_TYPE_BOARD or msg_type == MSG_TYPE_UPDATE:
            num_sneks = msg[0]
            sys.stderr.write('Num_sneks: ' + repr(num_sneks) + '\n')
            sneks = msg[1:1 + num_sneks * 5]
            board_changes = msg[1 + num_sneks * 5:]
            # process sneks
            for snek in [sneks[i:i+5] for i in range(0, len(sneks), 5)]:
                snek_id = snek[0]
                self.sneks[snek_id].score = struct.unpack('!h', snek[1:3])[0]
                self.sneks[snek_id].health = struct.unpack('!h', snek[3:5])[0]
            if msg_type == MSG_TYPE_BOARD:
                # process board whole
                cnt = 0
                for v in board_changes:
                    self.board[cnt // 80][cnt % 80] = int(v)
                    cnt += 1
            # process board updates
            elif msg_type == MSG_TYPE_UPDATE: 
                for update in [board_changes[i:i+3] for i in range(0, len(board_changes), 3)]:
                    self.board[update[1]][update[0]] = int(update[2])
            self.dirty = True

        elif msg_type == MSG_TYPE_UPDATE:
            pass
        elif msg_type == MSG_TYPE_INFO:
            pass
        elif msg_type == MSG_TYPE_TXT:
            pass

    def turn_up(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x01')

    def turn_right(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x02')

    def turn_down(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x03')

    def turn_left(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x04')

def sig_handler(s, f):
    print('\r\nQuitting! Thanks for playing snek.')
    curses.endwin()
    sys.exit(1)

def main():
    signal.signal(signal.SIGINT, sig_handler)
    connected = False
    join_sent = False
    time.sleep(0)

    # init the game
    my_game = game()

    # init the curses window
    try:
        my_game.my_renderer.init_curses()
    except snekception as e:
        my_game.my_renderer.shutdown()
        sys.stderr.write(str(e))
        sys.exit(1)
    except:
        my_game.my_renderer.shutdown()
        sys.stderr.write('Sorry, you ain\'t got curses or something.\n')
        sys.exit(1)

    print('Welcome to Snek.\r')
    print('Connecting to Snek server...\r')

    try:
        my_game.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        my_game.sock.connect(('localhost', 55555))
        my_game.sock.setblocking(0)
    except:
        my_game.my_renderer.shutdown()
        sys.stderr.write('Error! Could not connect to the Snek server.\r\n')
        sys.exit(1)

    # connected to the snek server
    print('Connected!\r')
    connected = True

    # main loop
    key = ''
    while connected:
        try:
            # get input from keyboard
            key = my_game.my_renderer.screen.getch()

            # process key
            if key == curses.KEY_LEFT:
                my_game.turn_left()
            elif key == curses.KEY_RIGHT:
                my_game.turn_right()
            elif key == curses.KEY_UP:
                my_game.turn_up()
            elif key == curses.KEY_DOWN:
                my_game.turn_down()
            elif key == ord('h'):
                my_game.show_help = not my_game.show_help
                my_game.dirty = True
            elif key == ord(' '):
                my_game.show_help = False
                my_game.dirty = True
                if not join_sent:
                    my_game.sock.send(b'\x00\x00')
                    join_sent = True
            elif key == ord('q'):
                break

            # process socket io
            r, w, e = select.select([my_game.sock], [], [], 0)
            if my_game.sock in r:
                # joined game, process messages normally
                msg_type = my_game.sock.recv(1)[0]
                sys.stderr.write('Got msg type: ' + repr(msg_type) + ' ' + repr(type(msg_type)) + '\n')
                if msg_type == MSG_TYPE_JOIN:
                    sys.stderr.write('Got Join.\n')
                    my_game.my_snek.snek_id = my_game.sock.recv(1)[0]
                    my_game.messages.insert(0, 'My snek is: ' + str(my_game.my_snek.snek_id))

                    # server told us it was full of sneks
                    if my_game.my_snek.snek_id == 255:
                        my_game.my_renderer.shutdown()
                        print('Server full of sneks.')
                        sys.exit(1)

                elif msg_type == MSG_TYPE_BOARD or msg_type == MSG_TYPE_UPDATE or msg_type == MSG_TYPE_TXT:
                    msg_len = struct.unpack('!i', my_game.sock.recv(4))[0]
                    msg = recv_n(my_game.sock, msg_len)
                    my_game.process_msg(msg_type, msg)

                elif msg_type == MSG_TYPE_INFO:
                    msg = recv_n(my_game.sock, 2)
                    sys.stderr.write(repr(msg) + '\n')
                    my_game.process_msg(msg_type, msg)

            # draw the game
            my_game.draw_game()

            # don't busy wait... despite what maixner says about you, sleep
            time.sleep(0.10)

        except Exception as e:
            sys.stderr.write(str(e))
            break

    my_game.my_renderer.shutdown()
    print('Thanks for playing Snek.')
    my_game.sock.close()

if __name__ == '__main__':
    main()
