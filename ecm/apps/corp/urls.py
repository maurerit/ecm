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

__date__ = "2012 08 01"
__author__ = "diabeteman"

from django.conf.urls.defaults import patterns

urlpatterns = patterns('ecm.apps.corp.views',
    (r'^$',                             'corp'),
    (r'^contact/$',                        'contact'),
    (r'^standings/$',                   'standings.standings'),
    (r'^login/$',                       'login'),
    (r'^toc/$',                         'list_available_data'),
)

