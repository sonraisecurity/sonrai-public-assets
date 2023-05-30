import time
import datetime
import os
import logging
import jwt
import sys
import json
import requests

from os import path
from datetime import datetime
from pathlib import Path

# get the calling scripts and this library's path
script_path = os.path.dirname(sys.argv[0])
lib_path = Path(__file__).parent.absolute()


# define Python user-defined exceptions
class SonraiAPIException(Exception):
    """Base class for other exceptions"""
    pass


# globals
logger = logging.getLogger("sonrai-token")
token = str()

# Create the Logger for use with all modules
# https://docs.python.org/3/library/logging.html#logrecord-objects
logging.basicConfig(
    format='[%(asctime)s] [%(levelname)s] - %(message)s',
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

# check for same script
if config['error_240_override'] == 0:
    if str(script_path).lower().strip() == str(lib_path).lower().strip():
        logging.error("Do not run your scripts in the same directory as the API Library, Please see the README.MD file")
        exit(240)

# Constants
_token_store = os.environ.get("SONRAI_API_TOKENSTORE", config['token_store'])
_token_file = os.environ.get("SONRAI_API_TOKENFILE", config['token_file'])
_env_token = os.environ.get("TOKEN", None)
_token_refresh_secs = os.environ.get("SONRAI_TOKEN_REFRESH_SECS", config['token_refresh_threshold_secs'])
_api_server = os.environ.get("SONRAI_API_SERVER", None)
_jwt_options = {"verify_iat": True, "verify_nbf": True, "verify_exp": True, "verify_iss": True, "verify_aud": False, "verify_signature": False}

# Set level according to the config file.
level = logging.getLevelName(config['sonrai-token-log-level'])
logger.setLevel(level)


def store_token():
    if _env_token or config['token_store'] == 'env':
        logger.debug("Storing token in ENV")
        os.environ['TOKEN'] = str(token).strip()
    else:
        logger.debug("Storing token in " + os.path.join(_token_store, _token_file))
        if not (os.path.exists(_token_store)):
            os.mkdir(_token_store)
        with open(os.path.join(_token_store, _token_file), "w") as token_dest:
            token_dest.write(str(token).strip())
            token_dest.close()


def verify_token():
    # Decode token, parse expiration date, and calculate time remaining
    # if within expiration time > 0, renew token
    try:
        decoded_token = jwt.decode(token, options=_jwt_options, algorithms=["RS256"])

    except Exception:
        os.remove(os.path.join(_token_store, _token_file))
        raise SonraiAPIException("Bad Token")

    # ORG and ORGS
    decoded_token['org'] = decoded_token['https://sonraisecurity.com/org']
    decoded_token['orgs'] = decoded_token['https://sonraisecurity.com/orgs']

    # ENV
    decoded_token['env'] = decoded_token['https://sonraisecurity.com/env']

    # URL
    decoded_token['sonrai_url'] = get_graph_url()

    logger.debug("Token Expires: {}".format(datetime.fromtimestamp(decoded_token.get('exp', 0))))
    decoded_token['human_expires'] = datetime.fromtimestamp(decoded_token.get('exp', 0))

    if token_expiring():
        renew_token()

    return decoded_token


def get_graph_url():
    if _api_server is None:
        decoded_token = jwt.decode(token, options=_jwt_options, algorithms=["RS256"])
        org = decoded_token['https://sonraisecurity.com/org']
        env = decoded_token['https://sonraisecurity.com/env']

        if env == 'stage':
            domain = '.s.sonraisecurity.com'
        elif env == 'dev':
            domain = '.de.sonraisecurity.com'
        else:
            domain = ".sonraisecurity.com"

        s = str(org).strip() + str(domain).strip()

    else:
        s = str(_api_server).strip()

    URL = "https://{}/graphql".format(s)
    logger.debug("API server: " + URL)

    return URL


def renew_token():
    global token
    logger.debug("Renewing token")

    _query = '''
        mutation renewToken {
            GenerateSonraiUserToken (input:{ expiresIn: ''' + str(config['token_length_secs']) + ''' name: "pythonAPIToken" }) { expireAt token } 
        }
    '''

    _query_name = "SonraiAPIClient_TokenRenew"
    _post_fields = json.dumps({"query": _query, "variables": "{}"})
    _headers = {"authorization": "Bearer " + token, "Content-type": "application/json", "query-name": _query_name, "Cache-Control": "no-cache"}
    _verify = True
    _proxy_server = None

    if config['verify_ssl'] == 0:
        _verify = False
        logger.debug("ssl verification disabled by config")

    if config['proxy_server']:
        _proxy_server = {
            "http": config['proxy_server'],
            "https": config['proxy_server']
        }
        logger.debug("using proxy server: {}".format(config['verify_ssl']))

    try:
        response = requests.post(
            get_graph_url(),
            data=_post_fields,
            headers=_headers,
            proxies=_proxy_server,
            timeout=config['query_timeout'],
            verify=_verify
        )
        r_json = response.json()

        if response.status_code == 200:
            if 'error' in response.text:
                _exp_text = "Renew Token Error - {}".format(r_json['errors'][0]['message'])
                raise ValueError(_exp_text)
            else:
                token = r_json['data']['GenerateSonraiUserToken']['token']
                logger.info("Storing updated token.")
                store_token()
    except Exception:
        raise SonraiAPIException("Could not renew token")


def token_expiring():
    global token

    # Decode token, parse expiration date, and calculate time remaining
    decoded_token = jwt.decode(token, options=_jwt_options, algorithms=["RS256"])
    current_time = time.time()
    remaining = decoded_token['exp'] - current_time
    logger.debug("expiry:{expiry} || current: {current} || remaining: {remaining}s".format(expiry=str(decoded_token['exp']), current=str(int(current_time)), remaining=str(int(remaining))))

    # If token is near expiration, return true.  Otherwise false.
    if remaining < 0:
        logger.debug("token has expired, cannot be renewed - ({}s ago)".format(str(int(remaining))))
        return False
    elif remaining < _token_refresh_secs:
        # if less than 6 hours remaining, attempt to renew
        logger.debug("token near expiration ({}s)... needs updating".format(str(int(remaining))))
        return True
    else:
        logger.debug("token not near expiration")
        return False


def token_expired():
    global token

    # Decode token, parse expiration date, and calculate time remaining
    decoded_token = jwt.decode(token, options=_jwt_options, algorithms=["RS256"])
    current_time = time.time()
    remaining = decoded_token['exp'] - current_time

    # If token is near expiration, return true.  Otherwise false.
    if remaining < 0:
        logger.debug("token has expired, cannot be renewed.")
        return True

    return False


# Env token over stored token
if not _env_token:
    # Check for token in token store file.
    tokenCheck = path.exists(os.path.join(_token_store, _token_file))

    # check local token
    if tokenCheck is True:
        with open(os.path.join(_token_store, _token_file), "r") as token_source:
            token = token_source.read().strip()
            token_source.close()

    else:
        # ask for a token
        logger.error("No 'user token' found, Please visit this page: https://docs.sonraisecurity.com/api/sonrai-graphql-api")
        token = input('Enter Sonrai User Token (no quotes): ')

        if token:
            store_token()
