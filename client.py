#!/usr/bin/python

import curses, locale, select, signal, socket, struct, sys, time

SALT = (33, '.')
CRACKER = (34, '#')
TOBASCO = (35, 'i')
SNACK_BREAD = (36, 'B')
OMLET = (37, '_')
WATER = (38, 'U')


class snekception(Exception): pass

class renderer:
    screen = None
    game_window = None
    message_window = None
    sidebar_window = None

    def init_curses(self):

        locale.setlocale(locale.LC_ALL, '')
        self.screen = curses.initscr()



        height, width = self.screen.getmaxyx()

#        if height < 56 or width < 96:
#            raise snekception('Sorry, Snek requires a 96x56 console window.  Go big or go home.\n')

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
        curses.init_pair(1, 9, curses.COLOR_BLACK)
        curses.init_pair(2, 10, curses.COLOR_BLACK)
        curses.init_pair(3, 11, curses.COLOR_BLACK)
        curses.init_pair(4, 12, curses.COLOR_BLACK)
        curses.init_pair(5, 13, curses.COLOR_BLACK)
        curses.init_pair(6, 14, curses.COLOR_BLACK)
        curses.init_pair(7, 15, curses.COLOR_BLACK)
        curses.init_pair(8, 238, curses.COLOR_BLACK)
        curses.init_pair(9, 160, curses.COLOR_BLACK)
        curses.init_pair(10, 155, curses.COLOR_BLACK)
        curses.init_pair(11, 220, curses.COLOR_BLACK)
        curses.init_pair(12, 21, curses.COLOR_BLACK)
        curses.init_pair(13, 129, curses.COLOR_BLACK)
        curses.init_pair(14, 159, curses.COLOR_BLACK)
        curses.init_pair(15, 252, curses.COLOR_BLACK)
        curses.init_pair(16, 243, curses.COLOR_BLACK)

        # init food colors
        curses.init_pair(33, 231, curses.COLOR_BLACK)
        curses.init_pair(34, 227, curses.COLOR_BLACK)
        curses.init_pair(35, 124, curses.COLOR_BLACK)
        curses.init_pair(36, 180, curses.COLOR_BLACK)
        curses.init_pair(37, 185, curses.COLOR_BLACK)
        curses.init_pair(38, 123, curses.COLOR_BLACK)

        # init game window
        self.game_window = curses.newwin(42,83,0,0)
        self.game_window.scrollok(False)
        self.sidebar = curses.newwin(42,43,0,83)
        self.messagebar = curses.newwin(22,125,42,0)

    def shutdown(self):
        curses.endwin()

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
    board = [[ord(' ') for x in range(0,80)] for y in range(0,40)]

    def draw_game(self):
        self.draw_board()
        self.draw_sidebar()
        self.draw_messagebar()

    def draw_board(self):
        if self.dirty:
            self.my_renderer.game_window.erase()
            self.my_renderer.game_window.addstr(0,0,u'\u2500'.encode('UTF-8'))
            y = 1
            for y_line in self.board:
                x = 1
                self.my_renderer.game_window.addch(y,0,'*')
                for x_elem in y_line:
                    # draw sneks
                    sys.stderr.write(repr(str(x_elem)) + repr(type(x_elem)))
                    if x_elem > 0 and x_elem < 17:
                        self.my_renderer.game_window.attron(curses.color_pair(x_elem))
                        self.my_renderer.game_window.attron(curses.A_BOLD)
                        self.my_renderer.game_window.addch(y, x, '@')
                        self.my_renderer.game_window.attroff(curses.color_pair(x_elem))
                        self.my_renderer.game_window.attroff(curses.A_BOLD)
                    # draw foodz
                    elif x_elem > 32 and x_elem < 64:
                        self.my_renderer.game_window.attron(curses.color_pair(2))
                        self.my_renderer.game_window.attron(curses.A_BOLD)
                        self.my_renderer.game_window.addch(y, x, '#')
                        self.my_renderer.game_window.attroff(curses.color_pair(2))
                        self.my_renderer.game_window.attroff(curses.A_BOLD)
                    x += 1
                self.my_renderer.game_window.addch(y,81,'*')
                y += 1
            self.my_renderer.game_window.addnstr(41,0,'*'*82, 82)
            self.my_renderer.game_window.refresh()
            self.dirty = False

    def draw_sidebar(self):
        self.my_renderer.sidebar.erase()
        for y in range(0, 42):
            if y == 0 or y == 41:
                self.my_renderer.sidebar.addstr(y,0,'*'*42)
            else:
                if y > 0 and y < 17:
                    self.my_renderer.sidebar.attron(curses.color_pair(y))
                    self.my_renderer.sidebar.attron(curses.A_BOLD)
                    self.my_renderer.sidebar.addstr(y,0,'* ' + ('Snek ' + str(y) + ': !!!!!!!! ' + str(self.sneks[y-1].score)).ljust(39) + '*')
                    self.my_renderer.sidebar.attroff(curses.color_pair(y))
                    self.my_renderer.sidebar.attron(curses.A_BOLD)
                else:
                    self.my_renderer.sidebar.addstr(y,0,'*' + (' ' * 40) + '*')
        self.my_renderer.sidebar.refresh()

    def draw_messagebar(self):
        self.my_renderer.messagebar.erase()
        for y in range(0,13):
            if y == 0 or y == 12:
                self.my_renderer.messagebar.addstr(y,0,'*'*125)
            else:
                if len(self.messages) > y - 1 and self.messages[y-1]:
                    self.my_renderer.messagebar.addstr(y,0,'*' + (' ' + self.messages[y-1]).ljust(123) + '*')
                else:
                    self.my_renderer.messagebar.addstr(y,0,'*' + ''.ljust(123) + '*')
        self.my_renderer.messagebar.refresh()

    def process_msg(self, msg):
        num_sneks = msg[0]
        sys.stderr.write('Num_sneks: ' + str(num_sneks) + '\r\n')
        sneks = msg[1:1 + num_sneks * 5]
        board_changes = msg[1 + num_sneks * 5:]
        for i in range(0, num_sneks):
            # process sneks
            pass
        for update in [board_changes[i:i+3] for i in range(0, len(board_changes), 3)]:
            sys.stderr.write('Board_update: ' + str(update[0]) + ' ' + str(update[1]) + ' ' + str(update[2]) + '\r\n')
            self.board[update[1]][update[0]] = int(update[2])
            self.dirty = True

    def turn_up(self):
        self.sock.send(chr(self.my_snek.snek_id) + '\x01')

    def turn_right(self):
        self.sock.send(chr(self.my_snek.snek_id) + '\x02')

    def turn_down(self):
        self.sock.send(chr(self.my_snek.snek_id) + '\x03')

    def turn_left(self):
        self.sock.send(chr(self.my_snek.snek_id) + '\x04')

def sig_handler(s, f):
    print('\r\nQuitting! Thanks for playing snek.')
    curses.endwin()
    sys.exit(1)

def main():
    signal.signal(signal.SIGINT, sig_handler)
    connected = False

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
        my_game.sock.connect(('localhost', 55553))
        my_game.sock.setblocking(0)
    except:
        my_game.my_renderer.shutdown()
        sys.stderr.write('Error! Could not connect to the Snek server.\r\n')
        sys.exit(1)

    # connected to the snek server
    print('Connected!\r')
    connected = True

    # join the game, maybe
    print('Joining game...\r')
    my_game.sock.send(b'\x00\x00')

    # check for response to join, timeout after 60s
    r, w, e = select.select([my_game.sock],[],[],60)
    if my_game.sock in r:
        # got a response, get our id
        rx = my_game.sock.recv(2)
        sys.stderr.write(repr(rx))
        my_game.my_snek.snek_id = rx[0]
        my_game.messages.insert(0, 'My snek is: ' + str(my_game.my_snek.snek_id))
        sys.stderr.write('Got this snek id: ' + str(my_game.my_snek.snek_id) + '\r\n')

        # server told us it was full of sneks
        if my_game.my_snek.snek_id == 255:
            my_game.my_renderer.shutdown()
            print('Server full of sneks.')
            sys.exit(1)
    else:
        # timed out waiting for a snek id
        my_game.my_renderer.shutdown()
        print('Error! Joining server timed out...')
        sys.exit(1)

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
            elif key == ord('q'):
                break

            # process socket io
            r, w, e = select.select([my_game.sock], [], [], 0)
            if my_game.sock in r:
                msg_len = struct.unpack('!i', my_game.sock.recv(4))[0]
                sys.stderr.write('Msg_len: ' + str(msg_len) + '.\r\n')
                msg = recv_n(my_game.sock, msg_len)
                my_game.process_msg(msg)
            
            # draw the game
            my_game.draw_game()

            # don't busy wait... despite what maixner says about you, sleep
            time.sleep(0.05)

        except Exception as e:
            sys.stderr.write(str(e))
            break

    my_game.my_renderer.shutdown()
    print('Thanks for playing Snek.')
    my_game.sock.close()

if __name__ == '__main__':
    main()
