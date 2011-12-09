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
from ecm.core.utils import cached_property

__date__ = "2011 8 20"
__author__ = "diabeteman"

from django.db import models
from django.contrib.auth.models import User

from ecm.core.eve.classes import Item, NoBlueprintException
from ecm.plugins.industry.models.research import InventionPolicy
from ecm.plugins.industry.models.catalog import OwnedBlueprint

#------------------------------------------------------------------------------
class Job(models.Model):

    class Meta:
        app_label = 'industry'
        ordering = ['order', 'id']

    PENDING = 0
    PLANNED = 1
    IN_PRODUCTION = 2
    READY = 3

    STATES = {
        PENDING:       'Pending',
        PLANNED:       'Planned',
        IN_PRODUCTION: 'In Production',
        READY:         'Ready',
    }

    SUPPLY = 0
    MANUFACTURING = 1
    INVENTION = 8

    ACTIVITIES = {
        MANUFACTURING: 'Manufacturing',
        SUPPLY:        'Supply',
        INVENTION:     'Invention',
    }

    # self.order is None if this is an aggregation job
    order = models.ForeignKey('Order', related_name='jobs', null=True, blank=True)
    # self.row is not None only if this is a root job
    row = models.ForeignKey('OrderRow', related_name='jobs', null=True, blank=True)
    # self.parentJob is None if this job is directly issued from an OrderRow
    parentJob = models.ForeignKey('self', related_name='childrenJobs', null=True, blank=True)
    # when a job is aggregated by another one, it goes to the AGGREGATED state...
    state = models.PositiveSmallIntegerField(default=PENDING, choices=STATES.items())

    owner = models.ForeignKey(User, related_name='jobs', null=True, blank=True)

    itemID = models.PositiveIntegerField()
    # runs must be a float number, else when jobs are aggregated there may be rounding errors
    runs = models.FloatField()
    blueprint = models.ForeignKey('OwnedBlueprint', related_name='jobs', null=True, blank=True)
    activity = models.SmallIntegerField(default=MANUFACTURING, choices=ACTIVITIES.items())

    dueDate = models.DateField(null=True, blank=True)
    duration = models.BigIntegerField(default=0)
    startDate = models.DateTimeField(null=True, blank=True)
    endDate = models.DateTimeField(null=True, blank=True)

    def createRequirements(self):
        """
        Recursively create all jobs needed to complete the current one.

        SUPPLY jobs are trivial, they stop the recursion.
        """
        if self.activity == Job.SUPPLY:
            return # stop recursion

        materials = self.blueprint.getBillOfMaterials(runs=self.runs,
                                                      meLevel=self.blueprint.me,
                                                      activity=self.activity)

        for mat in materials:
            self.childrenJobs.add(Job.create(itemID=mat.requiredTypeID,
                                             quantity=mat.quantity,
                                             order=self.order,
                                             row=self.row))

        parentBpID = self.blueprint.parentBlueprintTypeID
        if parentBpID is not None and self.blueprint.runs == -1:
            # only create invention jobs if we don't own a BPO/BPC (runs == -1)
            attempts  = InventionPolicy.attempts(self.blueprint)
            # create a temp OwnedBlueprint that will be used to run the invention
            bpc = OwnedBlueprint.objects.create(blueprintTypeID=parentBpID, copy=True)
            # add an INVENTION job
            self.childrenJobs.create(itemID=parentBpID,
                                     blueprint=bpc,
                                     runs=round(self.runs) * attempts,
                                     order=self.order,
                                     row=self.row,
                                     activity=Job.INVENTION)

        if self.activity == Job.INVENTION:
            # add a SUPPLY job for T1 BPCs
            self.childrenJobs.create(itemID=self.blueprint.typeID,
                                     runs=round(self.runs),
                                     order=self.order,
                                     row=self.row,
                                     activity=Job.SUPPLY)
            decriptorTypeID  = InventionPolicy.decryptor(self.parentJob.blueprint)
            if decriptorTypeID is not None:
                # add a SUPPLY job for a decryptorif needed
                self.childrenJobs.create(itemID=decriptorTypeID,
                                         runs=round(self.runs),
                                         order=self.order,
                                         row=self.row,
                                         activity=Job.SUPPLY)

        for job in self.childrenJobs.all():
            # recursive call
            job.createRequirements()

    @staticmethod
    def create(itemID, quantity, order, row):
        """
        Create a job (MANUFACTURING by default).

        If the item cannot be manufactured or if the corp does not own
        the blueprint needed for the item, a SUPPLY job is created.

        The number of runs is calculated from the needed quantity
        """
        item = Item.new(itemID)
        try:
            bpID = item.blueprint.typeID
            activity = Job.MANUFACTURING
            bp = OwnedBlueprint.objects.filter(blueprintTypeID=bpID, copy=False).order_by('-me')[0]
            runs = quantity / item.portionSize
            if quantity % item.portionSize:
                runs += 1
            duration = item.blueprint.getDuration(runs, bp.pe, activity)
        except IndexError:
            if item.techLevel == 2 and item.blueprint.parentBlueprintTypeID is not None:
                # we're trying to manufacture a T2 item without owning its BPO
                # we must create an OwnedBlueprint for this job only (that will
                # be consumed with it)
                # The invention policies are to be specified in InventionPolicies
                bp = InventionPolicy.blueprint(item.blueprint)
                runs = quantity / item.portionSize
                if quantity % item.portionSize:
                    runs += 1
                duration = item.blueprint.getDuration(runs, bp.pe, activity)
                bp.runs = -1 # to identify that this BPC will be invented
                bp.save()
            else:
                bp = None
                activity = Job.SUPPLY
                duration = 0
                runs = quantity
        except NoBlueprintException:
            bp = None
            activity = Job.SUPPLY
            duration = 0
            runs = quantity

        return Job.objects.create(order=order,
                                  row=row,
                                  itemID=itemID,
                                  blueprint=bp,
                                  runs=runs,
                                  activity=activity,
                                  duration=duration)

    def repr_as_tree(self, indent=0):
        output = '    ' * indent + '-> ' + unicode(self) + '\n'
        for j in self.childrenJobs.all():
            output += j.repr_as_tree(indent + 1)
        return output

    @cached_property
    def item(self):
        return Item.new(self.itemID)

    def __unicode__(self):
        return u"[%s] %s x%d" % (Job.ACTIVITIES[self.activity], self.item.typeName, int(round(self.runs)))
