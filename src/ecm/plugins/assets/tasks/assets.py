# Copyright (c) 2010-2012 Robin Jarry
#
# This file is part of EVE Corporation Management.
#
# EVE Corporation Management is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# EVE Corporation Management is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
# more details.
#
# You should have received a copy of the GNU General Public License along with
# EVE Corporation Management. If not, see <http://www.gnu.org/licenses/>.

__date__ = "2010-03-23"
__author__ = "diabeteman"

import logging

from django.db import transaction

from ecm.apps.common.models import Setting
from ecm.core import utils
from ecm.apps.eve import api
from ecm.apps.eve.models import CelestialObject
from ecm.apps.eve import constants as cst
from ecm.core.eve.classes import Item
from ecm.core.parsers import diff, markUpdated, checkApiVersion
from ecm.plugins.assets.models import Asset, AssetDiff

LOG = logging.getLogger(__name__)
IGNORE_CAN_VOLUMES = True

#------------------------------------------------------------------------------
@transaction.commit_on_success
def update():
    """
    Retrieve all corp assets and calculate the changes.

    If there's an error, nothing is written in the database
    """
    global IGNORE_CAN_VOLUMES

    LOG.info("fetching /corp/AssetList.xml.aspx...")
    api_conn = api.connect()
    apiAssets = api_conn.corp.AssetList(characterID=api.get_charID())
    checkApiVersion(apiAssets._meta.version)

    currentTime = apiAssets._meta.currentTime
    cachedUntil = apiAssets._meta.cachedUntil
    LOG.debug("current time : %s", str(currentTime))
    LOG.debug("cached util : %s", str(cachedUntil))

    LOG.debug("fetching old assets from the database...")
    oldItems = {}
    for a in Asset.objects.all():
        oldItems[a] = a

    newItems = {}
    LOG.debug("%d assets fetched", len(oldItems.keys()))

    IGNORE_CAN_VOLUMES = Setting.get('assets_ignore_containers_volumes')

    # we store the itemIDs of all the assets we want to locate 
    # then query /corp/Locations.xml with the list
    assets_to_locate = []

    LOG.debug("parsing api response...")
    for row in apiAssets.assets:
        if row.typeID == cst.BOOKMARK_TYPEID:
            continue # we don't give a flying @#!$ about the bookmarks...

        if row.locationID >= cst.STATIONS_IDS:
            # this row contains assets in a station
            if row.typeID == cst.OFFICE_TYPEID:
                row_is_office(office=row, items_dic=newItems)
            else:
                row_is_in_hangar(item=row, items_dic=newItems)
        else:
            # this row contains assets in space
            try:
                if cst.HAS_HANGAR_DIVISIONS[row.typeID]:
                    row_is_pos_corporate_hangar_array(corpArray=row, items_dic=newItems)
                else:
                    row_is_pos_array(array=row, items_dic=newItems)
                assets_to_locate.append(row.itemID)
            except KeyError:
                # unhandled typeID, this may be a reactor array or some other crap
                pass

    LOG.info("%d assets parsed", len(newItems))

    diffs = []
    if len(oldItems) != 0:
        LOG.debug("computing diffs since last asset scan...")
        diffs = calc_assets_diff(oldItems=oldItems, newItems=newItems, date=currentTime)
        if diffs:
            for assetDiff in diffs:
                assetDiff.save()
            # we store the update time of the table
            markUpdated(model=AssetDiff, date=currentTime)
        Asset.objects.all().delete()
    for asset in newItems.values():
        asset.save()

    update_assets_locations(assets_to_locate)
    update_assets_names()

    # we store the update time of the table
    markUpdated(model=Asset, date=currentTime)

    LOG.info("%d changes since last scan", len(diffs))

#------------------------------------------------------------------------------
def calc_assets_diff(oldItems, newItems, date):
    removed, added = diff(oldItems=oldItems, newItems=newItems)
    merge_duplicates(removed)
    merge_duplicates(added)

    diffs = []

    # so we don't get an Attribute error when calling addasset.duplicate
    for a in added: a.duplicate = False

    for remasset in removed:
        added_qty = 0
        for addasset in added:
            if not addasset.duplicate and addasset.lookslike(remasset):
                # if there is a match (there cannot be more than one), the added asset
                # was already in the removed assets. We tag the added asset to duplicate
                # and take it in consideration when creating the "removed" AssetDiff
                addasset.duplicate = True
                added_qty = addasset.quantity
                break
        if (added_qty - remasset.quantity):
            # if the added asset doesn't negates the removed one, we create a diff
            diffs.append(AssetDiff(solarSystemID=remasset.solarSystemID,
                                       stationID=remasset.stationID,
                                        hangarID=remasset.hangarID,
                                          typeID=remasset.typeID,
                                            flag=remasset.flag,
                                        quantity=added_qty - remasset.quantity,
                                            date=date,
                                             new=False,
                                          volume=remasset.volume))
    for addasset in added:
        if not addasset.duplicate:
            diffs.append(AssetDiff(solarSystemID=addasset.solarSystemID,
                                       stationID=addasset.stationID,
                                        hangarID=addasset.hangarID,
                                          typeID=addasset.typeID,
                                            flag=addasset.flag,
                                        quantity=addasset.quantity,
                                            date=date,
                                             new=True,
                                          volume=addasset.volume))
    return diffs

#------------------------------------------------------------------------------
def merge_duplicates(assetlist):
    assetlist.sort()
    # we sort assets by locationID, hangarID then typeID in order to merge duplicates
    try:
        i = 0
        while(True):
            if assetlist[i].lookslike(assetlist[i + 1]):
                # the assets are sorted so we can merge and delete the duplicate one
                assetlist[i].quantity += assetlist[i + 1].quantity
                del assetlist[i + 1]
            else:
                i += 1
    except IndexError:
        # when we reach the end of the list we WILL get an IndexError,
        # this is the only way to stop the loop :-)
        pass

#------------------------------------------------------------------------------
def row_is_office(office, items_dic):
    """
    'office' represents an office in a station
    """
    try :
        stationID = locationID_to_stationID(office.locationID)
        solarSystemID = CelestialObject.objects.get(itemID=stationID).solarSystemID
        #solarSystemID = db.getSolarSystemID(stationID)
        for item in office.contents:
            if item.typeID == cst.BOOKMARK_TYPEID :
                continue # we don't give a flying @#!$ about the bookmarks...
            row_is_in_hangar(item=item, items_dic=items_dic,
                       solarSystemID=solarSystemID, stationID=stationID)
    except AttributeError:
        # skip the office if it has no contents
        pass

#------------------------------------------------------------------------------
def row_is_pos_corporate_hangar_array(corpArray, items_dic):
    """
    'corpArray' represents an anchorable structure with corporate hangar divisions
    such as a 'Corporate Hangar Array' or a 'Mobile Laboratory'

    The 'stationID' of all the array contents is the unique 'itemID' of the array
    The 'typeID' of the array is stored in the 'flag' field of the contents.
    """
    try:
        solarSystemID = corpArray.locationID
        stationID = corpArray.itemID
        flag = corpArray.typeID
        for item in corpArray.contents:
            if item.typeID == cst.BOOKMARK_TYPEID :
                continue # we don't give a flying @#!$ about the bookmarks...
            row_is_in_hangar(item=item,
                          items_dic=items_dic,
                          solarSystemID=solarSystemID,
                          stationID=stationID,
                          flag=flag)
    except AttributeError:
        # skip the corpArray if it has no contents
        pass

#------------------------------------------------------------------------------
def row_is_pos_array(array, items_dic):
    """
    'array' represents an anchorable structure with no corporate hangar divisions
    such as a 'Ship Maintenance Array' or a 'Silo'

    The 'stationID' of all the array contents is the unique 'itemID' of the array
    The 'typeID' of the array is stored in the 'flag' field of the contents.
    We force the 'hangarID' of all contained items to '0' (no corporate divisions)
    """
    try :
        solarSystemID = array.locationID
        stationID = array.itemID
        flag = array.typeID
        for item in array.contents:
            if item.typeID == cst.BOOKMARK_TYPEID :
                continue # we don't give a flying @#!$ about the bookmarks...
            row_is_in_hangar(item=item,
                          items_dic=items_dic,
                          solarSystemID=solarSystemID,
                          stationID=stationID,
                          hangarID=0,
                          flag=flag)
    except AttributeError:
        # if the array has no attribute 'contents', we ignore it
        pass

#------------------------------------------------------------------------------
def row_is_in_hangar(item, items_dic, solarSystemID=None, stationID=None, hangarID=None, flag=None):
    """
    'item' represents an asset located in a hangar division.
    """
    asset = make_asset_from_row(item)

    if solarSystemID is None and stationID is None:
        # we come from the update() method and the item has a locationID attribute
        asset.stationID = locationID_to_stationID(item.locationID)
        asset.solarSystemID = CelestialObject.objects.get(itemID=asset.stationID).solarSystemID
        #asset.solarSystemID = db.getSolarSystemID(asset.stationID)
    else:
        asset.solarSystemID = solarSystemID
        asset.stationID = stationID

    if hangarID is None:
        try:
            asset.hangarID = cst.HANGAR_FLAG[item.flag]
        except KeyError:
            # if unhandled flag (i.e. not a hangar division)
            # allways fall back to the first division
            asset.hangarID = 1000
    else:
        asset.hangarID = hangarID

    if flag is not None:
        asset.flag = flag

    items_dic[asset] = asset

    try:
        fill_contents(container=asset, item=item, items_dic=items_dic, flag=flag)
        asset.hasContents = True
    except AttributeError:
        # if the item has no attribute 'contents', we're done
        pass

#------------------------------------------------------------------------------
def fill_contents(container, item, items_dic, flag=None):
    """
    Try to fill the contents of an item (assembled ship, assembled container)
    If the item has no contents, raise an attribute error.
    """
    for _item in item.contents:
        if _item.typeID == cst.BOOKMARK_TYPEID:
            continue # we don't give a flying @#!$ about the bookmarks...
        _asset = make_asset_from_row(_item)
        _asset.solarSystemID = container.solarSystemID
        _asset.stationID = container.stationID
        _asset.hangarID = container.hangarID
        _asset.container1 = container.itemID
        if flag is not None:
            _asset.flag = flag
        items_dic[_asset] = _asset

        try :
            for __item in _item.contents:
                if __item.typeID == cst.BOOKMARK_TYPEID:
                    continue # we don't give a flying @#!$ about the bookmarks...
                __asset = make_asset_from_row(__item)
                __asset.solarSystemID = container.solarSystemID
                __asset.stationID = container.stationID
                __asset.hangarID = container.hangarID
                __asset.container1 = container.itemID
                __asset.container2 = _asset.itemID
                if flag is not None:
                    __asset.flag = flag
                items_dic[__asset] = __asset

            _asset.hasContents = True
        except AttributeError:
            # if '__item' has no attribute 'contents', we skip to the next one
            continue



#------------------------------------------------------------------------------
def make_asset_from_row(row):
    i = Item.new(row.typeID)
    if IGNORE_CAN_VOLUMES and i.categoryID == 2:
        volume = 0.0
    else:
        volume = i.volume * row.quantity
    return Asset(itemID    = row.itemID,
                 typeID    = row.typeID,
                 quantity  = row.quantity,
                 flag      = row.flag,
                 singleton = row.singleton,
                 volume    = volume)

#------------------------------------------------------------------------------
def locationID_to_stationID(locationID):
    """
    to convert locationIDs starting 66000000 to stationIDs from staStations
                                                    subtract 6000001 from the locationID
    to convert locationIDs starting 66014933 to stationIDs from the eveAPI
                            ConquerableStationList subtract 6000000 from the locationID

    source : http://www.eveonline.com/ingameboard.asp?a=topic&threadID=667487
    """
    if locationID < 66000000:
        return locationID
    elif locationID < 66014933:
        return locationID - 6000001
    else:
        return locationID - 6000000

#------------------------------------------------------------------------------
def update_assets_locations(assets_to_locate):
    LOG.debug('Locating assets to their closest celestial object...')

    api_conn = api.connect()
    located_assets = []
    # Fetch all the x,y,z positions of the assets from the API
    for sub_list in utils.sublists(assets_to_locate, sub_length=50): # max 50 items per request
        LOG.debug('fetching /corp/Locations.xml.aspx...')
        ids = ','.join(map(str, sub_list))
        locations_api = api_conn.corp.Locations(characterID=api.get_charID(), ids=ids)
        for loc in locations_api.locations:
            located_assets.append( (loc.itemID, loc.itemName, loc.x, loc.y, loc.z) )
    
    LOG.debug('Computing positions...')
    for itemID, itemName, X, Y, Z in located_assets:
        # filter out all assets that are into the "in space" asset
        contained_assets = Asset.objects.filter(stationID=itemID)
        if contained_assets:
            solarSystemID = contained_assets.latest().solarSystemID
            distances = []
            
            #for object_id, x, y, z in db.get_celestial_objects(solarSystemID):
            for obj in CelestialObject.objects.filter(solarSystemID=solarSystemID,
                                                      group__in = [7, 8]):
                # Distances between celestial objects are huge. The error margin
                # that comes with manatthan distance is totally acceptable.
                # See http://en.wikipedia.org/wiki/Taxicab_geometry for culture.
                # manatthan_distance = abs(X - x) + abs(Y - y) + abs(Z - z)
                manatthan_distance = abs(X - obj.x) + abs(Y - obj.y) + abs(Z - obj.z)
                distances.append(( obj.itemID, manatthan_distance ))
            
            # Sort objects by increasing distance (we only want minimum)
            distances.sort(key=lambda obj:obj[1])
            # Finally, update all the items contained into the "in space" asset
            Asset.objects.filter(stationID=itemID).update(closest_object_id=distances[0][0],
                                                          name=itemName)


#------------------------------------------------------------------------------
def update_assets_names():
    LOG.debug('Updating player defined names...')
    
    assets_to_name = Asset.objects.filter(name=None, 
                                          container1=None, 
                                          container2=None, 
                                          singleton=True,
                                          hasContents=True,
                                          quantity=1).values_list('itemID', flat=True)
    api_conn = api.connect()
    named_assets = []
    # Fetch all the x,y,z positions of the assets from the API
    for sub_list in utils.sublists(assets_to_name, sub_length=50): # max 50 items per request
        LOG.debug('fetching /corp/Locations.xml.aspx...')
        ids = ','.join(map(str, sub_list))
        locations_api = api_conn.corp.Locations(characterID=api.get_charID(), ids=ids)
        for loc in locations_api.locations:
            named_assets.append( (loc.itemID, loc.itemName) )
    
    LOG.debug('Writing to DB...')
    for itemID, itemName in named_assets:
        Asset.objects.filter(itemID=itemID).update(name=itemName)

