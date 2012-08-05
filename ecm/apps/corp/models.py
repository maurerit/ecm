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

__date__ = "2010-02-08"
__author__ = "diabeteman"

try:
    import json
except ImportError:
    # fallback for python 2.5
    import django.utils.simplejson as json

import logging
import urlparse
import urllib2

from django.db import models


LOG = logging.getLogger(__name__)

#------------------------------------------------------------------------------
class Hangar(models.Model):

    class Meta:
        ordering = ['hangarID']

    hangarID = models.PositiveIntegerField(primary_key=True)

    def get_name(self, corp):
        return self.corp_hangars.get(corp=corp, hangar=self).name

    def get_access_lvl(self, corp):
        return self.corp_hangars.get(corp=corp, hangar=self).access_lvl

    def __unicode__(self):
        return unicode(self.hangarID)

#------------------------------------------------------------------------------
class CorpHangar(models.Model):

    class Meta:
        unique_together = ('corp', 'hangar')
        ordering = ('corp', 'hangar')

    corp = models.ForeignKey('Corporation', related_name='hangars')    
    hangar = models.ForeignKey('Hangar', related_name='corp_hangars')
    
    name = models.CharField(max_length=128)
    access_lvl = models.PositiveIntegerField(default=1000)
    
    def __unicode__(self):
        return unicode(self.name)

#------------------------------------------------------------------------------
class Wallet(models.Model):

    class Meta:
        ordering = ['walletID']

    walletID = models.PositiveIntegerField(primary_key=True)

    def get_name(self, corp):
        return self.corp_wallets.get(corp=corp, wallet=self).name

    def get_access_lvl(self, corp):
        return self.corp_wallets.get(corp=corp, wallet=self).access_lvl

    def __unicode__(self):
        return unicode(self.walletID)

#------------------------------------------------------------------------------
class CorpWallet(models.Model):
    
    class Meta:
        unique_together = ('corp', 'wallet')
        ordering = ('corp', 'wallet')
    
    corp = models.ForeignKey('Corporation', related_name='wallet')    
    wallet = models.ForeignKey('Wallet', related_name='corp_wallets')
    
    name = models.CharField(max_length=128)
    access_lvl = models.PositiveIntegerField(default=1000)
    
    def __unicode__(self):
        return unicode(self.name)

#------------------------------------------------------------------------------
class CorpManager(models.Manager):
    
    def mine(self):
        return self.get(is_my_corp=True) 
    
    def others(self):
        return self.filter(is_my_corp=False)

    
class Corporation(models.Model):
    
    objects = CorpManager()
    
    ecm_url         = models.URLField(unique=True)
    is_my_corp      = models.BooleanField(default=False, editable=False)

    corporationID   = models.BigIntegerField(primary_key=True, blank=True)
    corporationName = models.CharField(max_length=256, blank=True, null=True)
    ticker          = models.CharField(max_length=8, blank=True, null=True)
    ceoID           = models.BigIntegerField(blank=True, null=True)
    ceoName         = models.CharField(max_length=256, blank=True, null=True)
    stationID       = models.BigIntegerField(blank=True, null=True)
    stationName     = models.CharField(max_length=256, blank=True, null=True)
    allianceID      = models.BigIntegerField(blank=True, null=True)
    allianceName    = models.CharField(max_length=256, blank=True, null=True)
    allianceTicker  = models.CharField(max_length=8, blank=True, null=True)
    description     = models.TextField(blank=True, null=True)
    taxRate         = models.IntegerField(blank=True, null=True)
    memberLimit     = models.IntegerField(blank=True, null=True)

    private_key     = models.TextField(unique=True, blank=True, null=True)
    public_key      = models.TextField(unique=True, blank=True)
    key_fingerprint = models.CharField(max_length=1024, unique=True, blank=True)
    
    last_update     = models.DateTimeField(auto_now=True)
    
    #override
    def clean(self):
        
        url = urlparse.urljoin(self.ecm_url, '/corp/')
        
        LOG.debug('Fetching public info from %s...' % url)
        
        response = urllib2.urlopen(url)
        public_info = json.load(response)
        
        self.public_key = public_info['public_key']
        self.key_fingerprint = public_info['key_fingerprint']
        self.corporationName = public_info['corp_name']
        self.corporationID = public_info['corp_id']
        self.allianceName = public_info['alliance_name']
        self.allianceID = public_info['alliance_id']
        self.is_my_corp = False
        
        LOG.debug('Fetched public info from %s' % url)

    def __unicode__(self):
        return unicode(self.corporationName)

#------------------------------------------------------------------------------
class Standing(models.Model):
    
    class Meta:
        ordering = ('-value', 'contactName',)
    
    corp = models.ForeignKey('Corporation', related_name='standings')
    contactID = models.BigIntegerField(default=0)
    contactName = models.CharField(max_length=255)
    is_corp_contact = models.BooleanField(default=True)
    value = models.IntegerField(default=0)
    
    @property
    def contact_type(self):
        #https://forums.eveonline.com/default.aspx?g=posts&m=716708#post716708
        #Characters: ]90000000, 98000000[
        #Corporations: ]98000000, 99000000[
        #Alliances: ]99000000, 100000000[
        #Note: This is not accurate and should not be used until a better solution is found.
        if self.contactID > 90000000 and self.contactID < 98000000:
            return 'Character'
        elif self.contactID > 98000000 and self.contactID < 99000000:
            return 'Corporation'
        elif self.contactID > 99000000 and self.contactID < 100000000:
            return 'Alliance'
        else:
            return unicode(self.contactID)
    
    def __unicode__(self):
        return unicode(self.contactName)
