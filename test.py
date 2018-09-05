import curses
import locale
locale.setlocale(locale.LC_ALL,"")
stdscr = curses.initscr()
stdscr.addstr(u'\u2019'.encode('utf_8'))
stdscr.getch()
curses.endwin()
