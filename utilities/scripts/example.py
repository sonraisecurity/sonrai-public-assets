# MOVE THIS SCRIPT OUT OF THE SONRAI DIRECTORY TO EXECUTE IT. PLEASE SEE THE README.MD FILE
#
from sonrai_api import api, logger

query = '''
    query getAPITokens {
      SonraiUserTokens {
        items {
          name
          srn
          resourceId
          createdDate
          expireAt
        }
      }
    }
'''

print(api.execute_query(query))

logger.info("Done")
