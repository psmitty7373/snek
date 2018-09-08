#!/usr/bin/env python3

import curses, locale, select, signal, socket, struct, sys, time, traceback

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
        1: ('Alice', 'O@', 10),
        2: ('Fred', 'O@', 11),
        3: ('Karen', 'O@', 12),
        4: ('Chris', 'O@', 13),
        5: ('Mary', 'O@', 14),
        6: ('Pete', 'O@', 15),
        7: ('Janice', 'O@', 19),
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

TICKS_PER_SECOND_INPUT = 60
TICKS_PER_SECOND_FPS = 7

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
_ = MRE Omelet.  Only the finest for your snek.
U = MRE Water.  Drink it.
$ = MRE Jalapeno Cheese Spread.  Basically money.

~~~ Press SPACE to begin game! ~~~~
'''

class snekception(Exception): pass

class renderer:
    screen = None
    game_window = None
    messagebar = None
    sidebar = None
    msgbox = None

    def init_curses(self):

        self.screen = curses.initscr()
        height, width = self.screen.getmaxyx()

#        if width < 96: # or height < 56
#            raise snekception('Sorry, Snek requires a 96x54 console window.  Go big or go home.\n')

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

        # init colors
        for i in range(0,255):
            curses.init_pair(i, i, curses.COLOR_BLACK)

        # init other colors
        curses.init_pair(WHITEONGRAY, curses.COLOR_WHITE, 234)

        # init game window
        self.game_window = curses.newwin(42,83,0,0)
        self.game_window.scrollok(False)
        self.sidebar = curses.newwin(42,43,0,83)
        self.messagebar = curses.newwin(13,126,42,0)
        self.msgbox = curses.newwin(41,62,5,30)

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
        sys.stderr.write('Rx error:' + str(e))

    return buf

class snek:
    health = 0
    score = 0
    snek_id = 0
    color = 0
    symbol = 'O@'
    name = ''

    def __init__(self, snek_id = None, color = 0, symbol = 'O@', name = ''):
        if snek_id != None:
            self.snek_id = snek_id
        if color != 0:
            self.color = color
        if symbol != 'O@':
            self.symbol = symbol
        if name != '':
            self.name = name

class game:
    sock = None
    my_snek = snek()
    sneks = []
    for i in range(0,16):
        sneks.append(snek(i, the_sneks[i][COLOR], the_sneks[i][SYMBOL], the_sneks[i][NAME]))
    my_renderer = renderer()
    messages = []
    messages.insert(0, 'Welcome to Snek!')
    dirty = True
    wipe = True
    sidebar_dirty = True
    messagebar_dirty = True
    join_sent = False
    board = [[0 for x in range(0,80)] for y in range(0,40)]
    board_buff = [[0 for x in range(0,80)] for y in range(0,40)]
    show_msg = True
    current_msg = helpmsg

    def get_sneks_by_highscore(self):
        return sorted(self.sneks, key=lambda x: x.score, reverse=True)

    def draw_msg(self):
        if self.show_msg:
            self.my_renderer.msgbox.erase()
            msg_lines = self.current_msg.split('\n')
            for y in range(0,40):
                if y == 0 or y == 39:
                    self.my_renderer.msgbox.addstr(y,0,'+' + '-' * 60 + '+', curses.color_pair(WHITEONGRAY))
                elif y == 1 or y == 38:
                    self.my_renderer.msgbox.addstr(y,0,'++' + '-' * 58 + '++', curses.color_pair(WHITEONGRAY))
                elif y - 2 < len(msg_lines):
                    self.my_renderer.msgbox.addstr(y,0,'||' + msg_lines[y-2].center(58) + '||', curses.color_pair(WHITEONGRAY))
                else:
                    self.my_renderer.msgbox.addstr(y,0,'||' + ''.ljust(58) + '||', curses.color_pair(WHITEONGRAY))
            self.my_renderer.msgbox.noutrefresh()

    def draw_game(self):
        # prepare the display
        self.draw_board()
        self.draw_sidebar()
        self.draw_messagebar()
        self.draw_msg()
        # redraw
        curses.doupdate()

    def draw_board(self):
        if self.dirty:
            # if wiping, clear and draw borders
            if self.wipe:
                self.my_renderer.game_window.erase()
                self.my_renderer.game_window.addstr(0,0,'+' + '-=' * 40 + '+', curses.color_pair(self.sneks[self.my_snek.snek_id].color))
                self.my_renderer.game_window.addstr(41,0,'+' + '=-' * 40 + '+', curses.color_pair(self.sneks[self.my_snek.snek_id].color))
            y = 1
            for y_line in self.board_buff:
                x = 1
                # if wiping, draw borders
                if self.wipe:
                    self.my_renderer.game_window.addstr(y,0,'|', curses.color_pair(self.sneks[self.my_snek.snek_id].color))
                    self.my_renderer.game_window.addstr(y,81,'|', curses.color_pair(self.sneks[self.my_snek.snek_id].color))
                for x_elem in y_line:
                    if self.board[y-1][x-1] != x_elem or self.wipe:
                        self.board[y-1][x-1] = x_elem
                        # clear previously used squares
                        if x_elem == 0:
                            self.my_renderer.game_window.addstr(y, x, ' ')
                        # draw sneks
                        elif x_elem > 0 and x_elem < 33:
                            snek_id = (x_elem if x_elem % 2 == 0 else x_elem + 1) // 2 - 1
                            self.my_renderer.game_window.addstr(y, x, self.sneks[snek_id].symbol[x_elem % 2], curses.color_pair(self.sneks[snek_id].color))
                        # draw foodz
                        elif x_elem > 32 and x_elem < 64:
                            self.my_renderer.game_window.addstr(y, x, the_foods[x_elem][SYMBOL], curses.color_pair(the_foods[x_elem][COLOR]))
                    x += 1
                y += 1
            # move the cursor out of the play area
            self.my_renderer.game_window.addstr(41, 81, '+', curses.color_pair(self.sneks[self.my_snek.snek_id].color))
            # refresh without redrawing
            self.my_renderer.game_window.noutrefresh()
            self.dirty = False
            self.wipe = False

    def draw_sidebar(self):
        if self.sidebar_dirty:
            sneks_sorted = self.get_sneks_by_highscore()
            self.my_renderer.sidebar.erase()
            for y in range(0, 42):
                # draw header and footer
                if y == 0 or y == 41:
                    self.my_renderer.sidebar.addstr(y, 0, '+' + '-' * 40 + '+')
                # draw body of side bar
                else:
                    if y > 0 and y < 17:
                        self.my_renderer.sidebar.addstr(y, 0, '| ')
                        self.my_renderer.sidebar.addstr(sneks_sorted[y-1].name.ljust(13) + '!!!!!!!!'.ljust(13) + str('{:010}'.format(sneks_sorted[y-1].score)).rjust(12), curses.color_pair(sneks_sorted[y-1].color))
                        self.my_renderer.sidebar.addstr(' | ')
                    else:
                        self.my_renderer.sidebar.addstr(y, 0, '|' + (' ' * 40) + '|')
            self.my_renderer.sidebar.noutrefresh()
            self.sidebar_dirty = False

    def draw_messagebar(self):
        if self.messagebar_dirty:
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
            self.my_renderer.messagebar.noutrefresh()
            self.messagebar_dirty = False

    def add_message(self, msg):
        self.messages.insert(0, msg[:100])
        self.messages = self.messages[:10]
        self.messagebar_dirty = True

    def process_msg(self, msg_type, msg):
        if msg_type == MSG_TYPE_JOIN:
            pass

        elif msg_type == MSG_TYPE_BOARD or msg_type == MSG_TYPE_UPDATE:
            num_sneks = msg[0]
            sneks = msg[1:1 + num_sneks * 5]
            board_changes = msg[1 + num_sneks * 5:]
            # process sneks
            for snek in [sneks[i:i+5] for i in range(0, len(sneks), 5)]:
                snek_id = snek[0]
                score = struct.unpack('!h', snek[1:3])[0]
                health = struct.unpack('!h', snek[3:5])[0]
                if score != self.sneks[snek_id].score:
                    self.sneks[snek_id].score = score
                    self.sidebar_dirty = True
                if health != self.sneks[snek_id].health:
                    self.sneks[snek_id].health = health
                    self.sidebar_dirty = True

            if msg_type == MSG_TYPE_BOARD:
                # process board whole
                cnt = 0
                for v in board_changes:
                    self.board_buff[cnt // 80][cnt % 80] = int(v)
                    cnt += 1
            # process board updates
            elif msg_type == MSG_TYPE_UPDATE: 
                for update in [board_changes[i:i+3] for i in range(0, len(board_changes), 3)]:
                    self.board_buff[update[1]][update[0]] = int(update[2])
            self.dirty = True

        elif msg_type == MSG_TYPE_INFO:
            if msg[0] == INFO_TYPE_JOIN:
                self.add_message(self.sneks[msg[1]].name + ' has joined the fight.')
            elif msg[0] == INFO_TYPE_KILL:
                self.add_message(self.sneks[msg[1]].name + ' has met an untimely death.  Mediocre.')
                if msg[1] == self.my_snek.snek_id:
                    self.current_msg = ('\n\n\n\n\n\n\n\n\n\nYOU ARE DEAD\n\n\n\n\n\n\nPress SPACE to respawn.')
                    self.show_msg = True
                    self.join_sent = False

        elif msg_type == MSG_TYPE_TXT:
            pass

    def turn_up(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x00')

    def turn_right(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x01')

    def turn_down(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x02')

    def turn_left(self):
        self.sock.send(bytes([self.my_snek.snek_id]) + b'\x03')

def sig_handler(s, f):
    print('\r\nQuitting! Thanks for playing snek.')
    curses.endwin()
    sys.exit(1)

def main():
    signal.signal(signal.SIGINT, sig_handler)
    connected = False
    time.sleep(2)

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
    current_time = last_time = time.time()
    imm_redraw = True
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
                my_game.show_msg = not my_game.show_msg
                my_game.sidebar_dirty = True
                my_game.messagebar_dirty = True
                my_game.dirty = True
                my_game.wipe = True
            elif key == ord(' '):
                my_game.show_msg = False
                my_game.sidebar_dirty = True
                my_game.messagebar_dirty = True
                my_game.dirty = True
                my_game.wipe = True
                if not my_game.join_sent:
                    my_game.sock.send(b'\xff\xff')
                    my_game.join_sent = True
            elif key == ord('q'):
                break

            # process socket io
            r, w, e = select.select([my_game.sock], [], [], 0)
            if my_game.sock in r:
                # joined game, process messages normally
                msg_type = my_game.sock.recv(1)[0]
                if msg_type == MSG_TYPE_JOIN:
                    my_game.my_snek.snek_id = my_game.sock.recv(1)[0]
                    my_game.dirty = True
                    my_game.wipe = True

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
                    my_game.process_msg(msg_type, msg)

                imm_redraw = True

            # draw the game
            current_time = time.time()
            if (current_time - last_time) > (1 / TICKS_PER_SECOND_FPS) or imm_redraw:
                my_game.draw_game()
                last_time = current_time
                imm_redraw = False

            # don't busy wait... despite what maixner says about you, sleep
            time.sleep(1/TICKS_PER_SECOND_INPUT)

        except Exception as e:
            my_game.my_renderer.shutdown()
            sys.stderr.write('Error: ' + str(e))
            print(traceback.format_exc())
            break

    my_game.my_renderer.shutdown()
    print('Thanks for playing Snek.')
    my_game.sock.close()

if __name__ == '__main__':
    main()
