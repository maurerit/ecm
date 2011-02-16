'''
This file is part of ICE Security Management

Created on 23 mar. 2010
@author: diabeteman
'''
from ism.lib import eveapi
from ism.data.api.models import APIKey
from ism.core.api.cache import CacheHandler

class API:
    USER_ID = None
    API_KEY = None
    CHAR_ID = None

_api = APIKey.objects.get(id=1)
API.USER_ID = _api.userID
API.CHAR_ID = _api.charID
API.API_KEY = _api.key

def connect(debug=False,proxy =None,cache=True):
    if cache : handler = CacheHandler(debug=debug)
    else     : handler = None
    api = eveapi.EVEAPIConnection(cacheHandler=handler, proxy=proxy)
    return api.auth(userID=API.USER_ID, apiKey=API.API_KEY)
    
