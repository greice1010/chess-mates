import chess


class Game:
    def __init__(self, game_id: str, white: str, black: str):
        self.id = game_id
        self.players = {chess.WHITE: white, chess.BLACK: black}
        self.board = chess.Board()
        self.result = None  # e.g. "1-0"
        self.reason = None

    def color_of(self, username: str):
        for color, name in self.players.items():
            if name == username:
                return color
        return None

    def move(self, username: str, uci: str):
        """Apply a move; return an error string or None."""
        if self.result:
            return "Game is over"
        if self.color_of(username) != self.board.turn:
            return "Not your turn"
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return "Invalid move"
        if move not in self.board.legal_moves:
            return "Illegal move"
        self.board.push(move)
        outcome = self.board.outcome(claim_draw=True)
        if outcome:
            self.result = outcome.result()
            self.reason = outcome.termination.name.lower().replace("_", " ")
        return None

    def resign(self, username: str):
        color = self.color_of(username)
        if self.result or color is None:
            return
        self.result = "0-1" if color == chess.WHITE else "1-0"
        self.reason = "resignation"

    def state(self):
        return {
            "type": "state",
            "game_id": self.id,
            "fen": self.board.fen(),
            "white": self.players[chess.WHITE],
            "black": self.players[chess.BLACK],
            "turn": "white" if self.board.turn else "black",
            "check": self.board.is_check(),
            "result": self.result,
            "reason": self.reason,
            "moves": [m.uci() for m in self.board.move_stack],
        }
