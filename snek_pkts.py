CLIENT_MSG_LEN = 2

# Message types
MSG_TYPE_JOIN   = 0
MSG_TYPE_BOARD  = 1
MSG_TYPE_UPDATE = 2
MSG_TYPE_INFO   = 3
MSG_TYPE_TXT    = 4

JOIN_REJECT = 255

INFO_TYPE_JOIN = 0
INFO_TYPE_KILL = 1

# Snek data goes in board messages and update messages
def _msg_field_snek_data(snek_list):
    msg = bytes([len(snek_list)])
    for snek in snek_list:
        msg += bytes([snek.snek_id])
        msg += snek.score.to_bytes(2, byteorder='big')
        msg += b'\x00\x00'
    return msg

def msg_join_accept(snek_id):
    return bytes([MSG_TYPE_JOIN, snek_id])

def msg_join_reject():
    return bytes([MSG_TYPE_JOIN, JOIN_REJECT])

def msg_board(board, snek_list):
    msg = _msg_field_snek_data(snek_list)
    for y in range(len(board)):
        for x in range(len(board[0])):
            msg += bytes([board[y][x]])

    msg = bytes([MSG_TYPE_BOARD]) + len(msg).to_bytes(4, byteorder='big') + msg 
    return msg

# Generate board update message
def msg_update(board, last_board, snek_list):
    msg = _msg_field_snek_data(snek_list)
    for y in range(len(board)):
        for x in range(len(board[0])):
            new_square = board[y][x]
            old_square = last_board[y][x]
            if old_square != new_square:
                msg += bytes([x, y, new_square])

    msg = bytes([MSG_TYPE_UPDATE]) + len(msg).to_bytes(4, byteorder='big') + msg 
    return msg

# Generate info message
def msg_info(info_type, snek_id):
   msg = bytes([MSG_TYPE_INFO, info_type, snek_id])
   return msg
