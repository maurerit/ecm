# Copyright (c) 2010-2011 Robin Jarry
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

__date__ = "2010-02-03"
__author__ = "diabeteman"

from django.db.models import Q
from django.conf import settings
from django.utils.text import truncate_words
from django.contrib.auth.models import User

from ecm.apps.hr.models import Member
from ecm.core import utils
from ecm.apps.common.models import UpdateDate
from ecm.view import template_filters

DATE_PATTERN = "%Y-%m-%d_%H-%M-%S"

import logging
logger = logging.getLogger(__name__)

#------------------------------------------------------------------------------
def getScanDate(model):
    try:
        date = UpdateDate.objects.get(model_name=model.__name__)
        return date.update_date
    except UpdateDate.DoesNotExist:
        return "<no data>"

#------------------------------------------------------------------------------
class DatatableParams: pass
def extract_datatable_params(request):
    REQ = request.GET if request.method == 'GET' else request.POST
    params = DatatableParams()
    params.first_id = int(REQ["iDisplayStart"])
    params.length = int(REQ["iDisplayLength"])
    params.last_id = params.first_id + params.length - 1
    params.search = REQ["sSearch"]
    params.sEcho = int(REQ["sEcho"])
    params.column = int(REQ["iSortCol_0"])
    params.asc = REQ["sSortDir_0"] == "asc"
    return params

#------------------------------------------------------------------------------
member_table_columns = [
    "name", # default
    "nickname",
    "owner__username",
    "accessLvl",
    "corpDate",
    "lastLogin",
    "location"
]

def get_members(query, first_id, last_id, search_str=None, sort_by=0 , asc=True):

    query = query.select_related(depth=2) # improve performance

    sort_col = member_table_columns[sort_by]
    # SQL hack for making a case insensitive sort
    if sort_by in (0, 1):
        sort_col = sort_col + "_nocase"
        sort_val = utils.fix_mysql_quotes('LOWER("%s")' % member_table_columns[sort_by])
        query = query.extra(select={ sort_col : sort_val })

    if not asc: sort_col = "-" + sort_col
    query = query.extra(order_by=([sort_col]))

    if search_str:
        total_members = query.count()
        search_args = Q(name__icontains=search_str) | Q(nickname__icontains=search_str)

        if "DIRECTOR".startswith(search_str.upper()):
            search_args = search_args | Q(accessLvl=Member.DIRECTOR_ACCESS_LVL)

        query = query.filter(search_args)
        filtered_members = query.count()
    else:
        total_members = filtered_members = query.count()

    query = query[first_id:last_id]

    member_list = []
    for member in query:
        titles = ["Titles"]
        titles.extend(member.titles.values_list("titleName", flat=True))

        memb = [
            member.permalink,
            truncate_words(member.nickname, 5),
            member.owner_permalink,
            member.accessLvl,
            utils.print_date(member.corpDate),
            utils.print_date(member.lastLogin),
            truncate_words(member.location, 5),
            "|".join(titles)
        ]

        member_list.append(memb)

    return total_members, filtered_members, member_list



#------------------------------------------------------------------------------
if not User.objects.filter(username=settings.ADMIN_USERNAME):
    try:
        logger.info('superuser "%s" does not exists. Creating...' % settings.ADMIN_USERNAME)
        User.objects.create_superuser(username=settings.ADMIN_USERNAME, email='', password='adminecm')
    except:
        logger.exception("")
        raise

#------------------------------------------------------------------------------
if not User.objects.filter(username=settings.CRON_USERNAME):
    try:
        logger.info('user "%s" does not exists. Creating...' % settings.CRON_USERNAME)
        User.objects.create_user(username=settings.CRON_USERNAME, email='', password='cron')
    except:
        logger.exception("")
        raise
