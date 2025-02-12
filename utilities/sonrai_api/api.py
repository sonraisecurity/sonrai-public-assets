import requests
import time
import json

from sonrai_api import config, logger, api_token, token, SonraiAPIException


def _auth_header():
    return {
        "authorization": "Bearer {bearer}".format(bearer=token.token),
        "Content-type": "application/json",
        "query-name": "SonraiAPIQuery",
        "Cache-Control": "no-cache"
    }


def execute_query(query=None, variables={}):
    _verify = True
    _proxy = None
    _complete = None
    _retries = 0
    _response = None

    if config['verify_ssl'] == 0:
        _verify = False
        logger.debug("ssl verification disabled by config")

    if config['proxy_server']:
        _proxy = {
            "http": config['proxy_server'],
            "https": config['proxy_server']
        }
        logger.debug("using proxy server: {}".format(config['verify_ssl']))

    if query:
        while _retries <= int(config['query_retries']) and not _complete:

            try:
                _response = requests.post(
                    api_token['sonrai_url'],
                    data=json.dumps({"query": query, "variables": variables}),
                    headers=_auth_header(),
                    proxies=_proxy,
                    timeout=config['query_timeout'],
                    verify=_verify
                )

            except requests.exceptions.Timeout:
                logger.error("*** Request timeout. Sleeping 5 seconds and trying again. Try #{retry}".format(retry=_retries))
                _retries += 1
                time.sleep(5)

            except Exception as e:
                raise SonraiAPIException("There was a problem communicating with Sonrai - ", str(e))

            else:
                _complete = True

            if _retries == int(config['query_retries']) and _complete is False:
                logger.debug("failed after {} retries, aborting".format(config['query_retries']))
                raise SonraiAPIException("Sonrai API Query Took too long - Aborting")

        if _response.status_code in (404, 403, 402):
            logger.debug("{status} error - please check your server setting".format(status=str(_response.status_code)))
            raise SonraiAPIException("*** AUTHENTICATION FAILED ***")

        if _response.status_code == 401:
            logger.debug("API token expired, please get a new one from the Advanced Search UI.")
            raise SonraiAPIException("Sonrai Token Expired")

        if _response.status_code == 500:
            logger.debug(str(_response.json()))
            raise SonraiAPIException("Sonrai Server 500 Error")

        if "Unexpected exception while fetching Grpc data" in str(_response.json()):
            logger.debug("GPRC error message received:")
            logger.debug("This occurs if the query size limit is reached.")
            logger.debug("Try limiting your query with additional filters & try again.")
            raise SonraiAPIException("GPRC Error - Query Limit Reached")

        if _response.status_code == 200:
            return _response.json()
        else:
            raise SonraiAPIException(_response.status_code)
