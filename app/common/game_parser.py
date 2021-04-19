import pgn
import json
from app import db, models

class GameParser:
    """Init with a pgn to parse into an object that is db ready.
    Populate the Game table with parsed games.
    Unparse games and return them as pgns or strings."""

    def __init__(self, pgn_string=None, game_id=None, verbose=False, delimiter=None):
        """Init the GameParser either with a pgn string or with a game id.
        Game id should correspond with the Game.id in the database."""
        if pgn_string:
            self.pgn = '\n'.join(pgn_string.split(delimiter))
        else:
            self.pgn = None
        self.game_id = game_id
        self.parsed_games = pgn.loads(self.pgn) if self.pgn else None
        self.verbose = verbose

        if not self.parsed_games:
            self.__print("Parsed games, 0 in total.")
        else:
            self.__print("Parsed games, {} in total".format(len(self.parsed_games)))

    def unparse_game(self, return_type='pgn'):
        """If GameParser initialized with game_id rather than string,
        this method should return the game as a pgn string or dict as per return_type.
        Default return_type is pgn"""
        if not self.game_id:
            print('No Game Id Provided')
            return None
        game = models.Game.query.get(self.game_id)

        return self.format_game(game, return_type=return_type)

    def format_game(self, game, return_type='pgn'):
        """Formats a game model into a pgn or dictionary"""

        players = self.__unparse_players_with_color(players=game.players,
                                                    game_id=game.id)
        # Preparing the game object for a pgn dumps
        game.white = players['white'].full_name()
        game.black = players['black'].full_name()

        if return_type in ('dict', 'json'):
            game_dict = {}
            game_dict['event'] = game.event
            game_dict['site'] = game.site
            game_dict['date'] = game.date
            game_dict['round'] = game.match_round
            game_dict['white_elo'] = game.white_elo
            game_dict['black_elo'] = game.black_elo
            game_dict['white'] = game.white
            game_dict['black'] = game.black
            game_dict['moves'] = game.moves
            game_dict['eco'] = game.eco
            return_obj = game_dict
            db.session.expunge_all()
            return return_obj
        else:
            game.moves = game.moves.split(',')
            game.round = game.match_round
            game.whiteelo = game.white_elo
            game.blackelo = game.black_elo
            # Fields not in our db but required by pgn (parser)
            game.annotator = ''
            game.plycount = ''
            game.timecontrol = ''
            game.time = ''
            game.termination = ''
            game.mode = ''
            game.fen = ''
            pgn_game = pgn.dumps(game)
            db.session.expunge_all()
            return pgn_game

    def format_games(self, games, return_type='pgn'):
        """Returns a list of games formatted either in a dictionary or pgn"""
        return [self.format_game(game, return_type=return_type) for game in games]

    def add_games(self):
        """If pgn was provided and parsed, adds games from pgn to the db"""

        if self.parsed_games:
            for game in self.parsed_games:

                self.__print("Adding game {} vs {} {}".format(game.white, game.black, game.date))

                # Returns dict like: {white: <id>, black: <id>}
                db_player_ids = self.__add_players(white=game.white,
                                                    black=game.black)
                db_game_id = self.__add_game(game)
                self.__add_pairings(game_id=db_game_id,
                                    player_ids=db_player_ids)
                db.session.expunge_all()

    def get_games(self, request_args={}):
        """Return all games from DB as models"""
        games = models.Game.query.all()
        if any(request_args):
            games = list(filter(lambda g: self.__game_match(g, request_args), games))

        return games

    def get_game(self, id=1):
        """TODO(Returns a single game from DB as a model)"""
        return models.Game.query.get(id)

    def player_in_db(self, player, stringified=False):
        """Takes a player name and checks if player in db
        If present, it returns the player id, else returns None.
        If player is stringified, it parses the name into a dict.
        """

        if stringified:
            player = self.__parse_player_name(player)
        player_in_db = models.Player.query.filter_by(
                        first_name=player['first_name'],
                        last_name=player['last_name'])

        if player_in_db.count() > 0:
            return player_in_db.first().id
        else:
            return None

    def __unparse_players_with_color(self, players, game_id):
        """Takes an array of db Player objects and the game_id.
        Returns players with colors in the game"""

        players_obj = {}
        pairing_1 = models.Pairing.query.filter_by(player_id=players[0].id,
                                            game_id=game_id).first()
        pairing_2 = models.Pairing.query.filter_by(player_id=players[1].id,
                                            game_id=game_id).first()
        if pairing_1.color == 'white':
            players_obj['white'] = players[0]
            players_obj['black'] = players[1]
        elif pairing_2.color == 'white':
            players_obj['white'] = players[1]
            players_obj['black'] = players[0]

        return players_obj

    def __add_game(self, game):
        """Takes a single game object and adds it to the Game table in the db"""

        moves_string = (',').join(game.moves)
        db_game = models.Game(
                event=game.event,
                site=game.site,
                date=game.date,
                match_round=game.round,
                result=game.result,
                white_elo=game.whiteelo,
                black_elo=game.blackelo,
                moves=moves_string,
                eco = game.eco
            )
        db.session.add(db_game)
        db.session.commit()
        return db_game.id

    def __add_players(self, white, black):
        """Adds players to db if players not in db.
        Returns dict like {'white': <id>, 'black': <id>}"""

        white_parsed = self.__parse_player_name(white)
        black_parsed = self.__parse_player_name(black)

        white_id = self.player_in_db(white_parsed)
        black_id = self.player_in_db(black_parsed)

        if not white_id:
            db_white = models.Player(
                    first_name= white_parsed['first_name'],
                    last_name = white_parsed['last_name']
                    )
            db.session.add(db_white)

        if not black_id:
            db_black = models.Player(
                    first_name= black_parsed['first_name'],
                    last_name = black_parsed['last_name']
                    )
            db.session.add(db_black)

        db.session.commit()

        if not white_id:
            white_id = db_white.id
        if not black_id:
            black_id = db_black.id

        return {'white': white_id, 'black': black_id}


    def __parse_player_name(self, name_string):
        """Takes a player name string and returns a dict as:
        {'first_name': <string>, last_name': <string>}
        String argument excpected to follow the format:
        'LastName, FirstName M' or 'LastName, FirstName'
        first_name field includes middle name at the end.
        """
        name_dict = {}
        # Split by comma. First name may include middle name.
        name_array = name_string.split(',')
        name_dict['first_name'] = name_array[1].strip() if len(name_array) > 1 else ''
        name_dict['last_name'] = name_array[0].strip()
        return name_dict

    def __add_pairings(self, game_id, player_ids):
        """Receives a game_id and a dict with player ids,
        adds two pairings for white and black"""

        black_pairing = models.Pairing(game_id=game_id,
                                        player_id=player_ids['black'],
                                        color='black')
        white_pairing = models.Pairing(game_id=game_id,
                                        player_id = player_ids['white'],
                                        color='white')
        db.session.add(black_pairing)
        db.session.add(white_pairing)
        db.session.commit()

    def __game_match(self, game, request_args):
        """Match games based on filters defined in games.py"""
        if 'name' in request_args:
            players = self.__unparse_players_with_color(
                players=game.players,
                game_id=game.id)

            if request_args['name'] not in players['white'].full_name().lower() and \
                request_args['name'] not in players['black'].full_name().lower():
                return False

        if 'eco' in request_args:
            if request_args['eco'].lower() != game.eco.lower():
                return False

        return True

    def __print(self, output):
        """Print output if verbose is set to True"""

        if self.verbose:
            print(output)
