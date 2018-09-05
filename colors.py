import curses

def main(stdscr):
    curses.start_color()
    curses.use_default_colors()
    for i in range(0, curses.COLORS):
        curses.init_pair(i, i, -1)
    try:
        for i in range(0, 255):
            stdscr.addstr(str(i) + '  ', curses.color_pair(i))
            if i > 15 and (i - 1) % 7 == 0:
                stdscr.addstr('\n')
    except curses.ERR:
        # End of screen reached
        pass
    stdscr.getch()

curses.wrapper(main)
