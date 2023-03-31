import logging
import sys
import json

from sonrai_api import token

# globals
logger = logging.getLogger("sonrai_api")
api_token = token.verify_token()

# Create the Logger for use with all modules
# https://docs.python.org/3/library/logging.html#logrecord-objects
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] -- %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

# Set ERROR for initial loading of information
level = logging.getLevelName('ERROR')
logger.setLevel(level)

# Constants from config
try:
    with open('sonrai_api/config.json') as json_file:
        config = json.load(json_file)
except json.decoder.JSONDecodeError:
    logging.error("Unable to parse the config.json file")
    exit(255)
except FileNotFoundError:
    logging.error("Unable to find the config.json file")
    exit(254)


# define Python user-defined exceptions
class SonraiAPIException(Exception):
    """Base class for other exceptions"""
    pass


# Set level according to the config file.
level = logging.getLevelName(config['sonrai-token-log-level'])
logger.setLevel(level)
