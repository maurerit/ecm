
BEGIN;

------------------------------------------
-- CUSTOM blueprints requirements table --
------------------------------------------
CREATE TABLE "ramBlueprintReqs" (
    "blueprintTypeID" SMALLINT,       -- id of blueprint using this material
    "activityID" TINYINT UNSIGNED,    -- building, copying, etc
    "requiredTypeID" SMALLINT,        -- id of resource used for this activity
    "quantity" INT,                   -- how many of this resource is used
    "damagePerJob" DOUBLE,            -- how much of the resource is expended
    "baseMaterial" INT,               -- how much is the base material.  
                                    -- 0 means unaffected by waste, >=quantity means entirely affected
    CONSTRAINT "materials_PK" PRIMARY KEY ("blueprintTypeID", "activityID", "requiredTypeID")
);

CREATE INDEX "ramBlueprintReqs_IX_blueprintTypeID" ON "ramBlueprintReqs" ("blueprintTypeID");
CREATE INDEX "ramBlueprintReqs_IX_activityID" ON "ramBlueprintReqs" ("activityID");

-- The following queries take invTypeMaterials and ramTypeRequirements and combine them 
-- into a single table showing all the materials a blueprint requires, and how much of each 
-- material is affected by waste when building.
-------------------------------------------------------
INSERT INTO "ramBlueprintReqs"
    SELECT  rtr."typeID",
            rtr."activityID",
            rtr."requiredTypeID",
            (rtr."quantity" + IFNULL(itm."quantity", 0)),
            rtr."damagePerJob",
            itm."quantity"
    FROM "invBlueprintTypes" AS b
       INNER JOIN "ramTypeRequirements" AS rtr
           ON rtr."typeID" = b."blueprintTypeID"
          AND rtr."activityID" = 1 -- manufacturing
       LEFT OUTER JOIN "invTypeMaterials" AS itm
           ON itm."typeID" = b."productTypeID"
          AND itm."materialTypeID" = rtr."requiredTypeID"
    WHERE rtr."quantity" > 0;
----------------------------------------------------------
INSERT INTO "ramBlueprintReqs"
    SELECT  b."blueprintTypeID", 
            1,  -- manufacturing activityID
            itm."materialTypeID",   -- requiredTypeID
            (itm."quantity" - IFNULL(sub."quantity" * sub."recycledQuantity", 0)),  -- quantity
            1,   -- damagePerJob
            (itm."quantity" - IFNULL(sub."quantity" * sub."recycledQuantity", 0))  -- baseMaterial
    FROM "invBlueprintTypes" AS b 
       INNER JOIN "invTypeMaterials" AS itm 
           ON itm."typeID" = b."productTypeID" 
       LEFT OUTER JOIN "ramBlueprintReqs" m 
           ON b."blueprintTypeID" = m."blueprintTypeID" 
           AND m."requiredTypeID" = itm."materialTypeID" 
       LEFT OUTER JOIN ( 
           SELECT srtr."typeID" AS "blueprintTypeID", -- tech 2 items recycle into their materials
                  sitm."materialTypeID" AS "recycledTypeID",   -- plus the t1 item's materials
                  srtr."quantity" AS "recycledQuantity", 
                  sitm."quantity" AS "quantity"
           FROM "ramTypeRequirements" AS srtr 
               INNER JOIN "invTypeMaterials" AS sitm 
                   ON srtr."requiredTypeID" = sitm."typeID" 
           WHERE srtr."recycle" = 1   -- the recycle flag determines whether or not this requirement's materials are added
             AND srtr."activityID" = 1 
       ) AS sub 
           ON sub."blueprintTypeID" = b."blueprintTypeID" 
           AND sub."recycledTypeID" = itm."materialTypeID" 
    WHERE m."blueprintTypeID" IS NULL -- partially waste-affected materials already added
    AND (itm."quantity" - IFNULL(sub."quantity" * sub."recycledQuantity", 0)) > 0; -- ignore negative quantities
----------------------------------------------------------
INSERT INTO ramBlueprintReqs("blueprintTypeID", 
                             "activityID", 
                             "requiredTypeID", 
                             "quantity", 
                             "damagePerJob") 
    SELECT  rtr."typeID", 
            rtr."activityID",
            rtr."requiredTypeID", 
            rtr."quantity", 
            rtr."damagePerJob" 
    FROM "ramTypeRequirements" AS rtr 
    WHERE rtr."activityID" NOT IN (1);
----------------------------------------------------------
UPDATE "ramBlueprintReqs" SET "baseMaterial" = 0 WHERE "baseMaterial" IS NULL;

--------------------
-- PATCH invTypes --
--------------------

-- backup invTypes table and delete it
CREATE TABLE "invTypes_temp" (
  "typeID" int(11) NOT NULL,
  "groupID" smallint(6) DEFAULT NULL,
  "typeName" varchar(100) DEFAULT NULL,
  "description" varchar(3000) DEFAULT NULL,
  "graphicID" smallint(6) DEFAULT NULL,
  "radius" double DEFAULT NULL,
  "mass" double DEFAULT NULL,
  "volume" double DEFAULT NULL,
  "capacity" double DEFAULT NULL,
  "portionSize" int(11) DEFAULT NULL,
  "raceID" tinyint(3) DEFAULT NULL,
  "basePrice" double DEFAULT NULL,
  "published" tinyint(1) DEFAULT NULL,
  "marketGroupID" smallint(6) DEFAULT NULL,
  "chanceOfDuplicating" double DEFAULT NULL,
  "iconID" smallint(6) DEFAULT NULL,
  PRIMARY KEY ("typeID")
);
INSERT INTO "invTypes_temp" SELECT * FROM "invTypes";
DROP TABLE "invTypes";

-- create the new patched one
-- this is an optimization of the invTypes table,  
-- the icons and corresponding blueprints are directly available without the need for SQL joins 
CREATE TABLE "invTypes" (
  "typeID" int(11) NOT NULL,
  "groupID" smallint(6) DEFAULT NULL,
  "categoryID" tinyint(3) DEFAULT NULL,
  "typeName" varchar(100) DEFAULT NULL,
  "blueprintTypeID" int(11) DEFAULT NULL,
  "techLevel" smallint(6) DEFAULT NULL,
  "description" varchar(3000) DEFAULT NULL,
  "volume" double DEFAULT NULL,
  "portionSize" int(11) DEFAULT NULL,
  "basePrice" double DEFAULT NULL,
  "marketGroupID" smallint(6) DEFAULT NULL,
  "icon" varchar(32) DEFAULT NULL,
  PRIMARY KEY ("typeID")
);

CREATE INDEX "invTypes_IX_Group" ON "invTypes" ("groupID");
CREATE INDEX "invTypes_IX_iconID" ON "invTypes" ("icon");
CREATE INDEX "invTypes_IX_marketGroupID" ON "invTypes" ("marketGroupID");
CREATE INDEX "invTypes_IX_techLevel" ON "invTypes" ("techLevel");

-- fill the custom table
INSERT INTO "invTypes"
SELECT  t."typeID", 
        t."groupID", 
        gg."categoryID",
        t."typeName",
        b."blueprintTypeID" AS blueprintTypeID, 
        b."techLevel",
        t."description", 
        t."volume", 
        t."portionSize", 
        t."basePrice", 
        t."marketGroupID", 
        IFNULL('icon' || g."iconFile", CAST(t."typeID" AS TEXT)) AS "icon"
FROM "invTypes_temp" t LEFT OUTER JOIN "eveIcons" g ON t."graphicID" = g."iconID",
     "invTypes_temp" t2 LEFT OUTER JOIN "invBlueprintTypes" b ON t."typeID" = b."productTypeID",
     "invGroups" gg
WHERE t."typeID" = t2."typeID"
  AND t."groupID" = gg."groupID"
  AND t."published" = 1;
  
-- delete the temp table
DROP TABLE "invTypes_temp";

  
----------------------------------------------------------
-- CREATE A SPECIAL SYSTEMS, MOONS & PLANETS TABLE for quick name resolution

CREATE TABLE "mapCelestialObjects" (
  "itemID" int(11) NOT NULL,
  "typeID" int(11) DEFAULT NULL,
  "groupID" smallint(6) DEFAULT NULL,
  "solarSystemID" int(11) DEFAULT NULL,
  "regionID" int(11) DEFAULT NULL,
  "itemName" varchar(100) DEFAULT NULL,
  "security" double DEFAULT NULL,
  PRIMARY KEY ("itemID")
);

CREATE INDEX "mapCelestialObjects_IX_region" ON "mapCelestialObjects" ("regionID");
CREATE INDEX "mapCelestialObjects_IX_system" ON "mapCelestialObjects" ("solarSystemID");

INSERT INTO "mapCelestialObjects"
SELECT  "itemID", 
        "typeID", 
        "groupID", 
        "solarSystemID", 
        "regionID", 
        "itemName", 
        "security"
FROM "mapDenormalize"
WHERE "groupID" IN (5, 7, 8, 15);

UPDATE "mapCelestialObjects" 
SET "security" = 
    (SELECT "mapSolarSystems"."security" 
        FROM "mapSolarSystems"
        WHERE "mapCelestialObjects"."itemID" = "mapSolarSystems"."solarSystemID") 
WHERE "security" IS NULL;


----------------------------------------------------------
-- DROP UNWANTED TABLES

DROP TABLE "agtAgentTypes";
DROP TABLE "agtAgents";
DROP TABLE "agtConfig";
DROP TABLE "agtResearchAgents";

DROP TABLE "chrAncestries";
DROP TABLE "chrAttributes";
DROP TABLE "chrBloodlines";
DROP TABLE "chrFactions";
DROP TABLE "chrRaces";

DROP TABLE "crpActivities";
DROP TABLE "crpNPCCorporationDivisions";
DROP TABLE "crpNPCCorporationResearchFields";
DROP TABLE "crpNPCCorporationTrades";
DROP TABLE "crpNPCCorporations";
DROP TABLE "crpNPCDivisions";

DROP TABLE "crtCategories";
DROP TABLE "crtCertificates";
DROP TABLE "crtClasses";
DROP TABLE "crtRecommendations";
DROP TABLE "crtRelationships";

DROP TABLE "dgmAttributeCategories";
DROP TABLE "dgmAttributeTypes";
DROP TABLE "dgmEffects";
DROP TABLE "dgmTypeAttributes";
DROP TABLE "dgmTypeEffects";

DROP TABLE "eveGraphics";
DROP TABLE "eveIcons";
DROP TABLE "eveLocations";
DROP TABLE "eveNames";
DROP TABLE "eveOwners";
DROP TABLE "eveUnits";

-- DROP TABLE "invBlueprintTypes";
-- DROP TABLE "invCategories";
DROP TABLE "invContrabandTypes";
DROP TABLE "invControlTowerResourcePurposes";
DROP TABLE "invControlTowerResources";
DROP TABLE "invFlags";
-- DROP TABLE "invGroups";
DROP TABLE "invItems";
-- DROP TABLE "invMarketGroups";
DROP TABLE "invMetaGroups";
DROP TABLE "invMetaTypes";
DROP TABLE "invTypeMaterials";
DROP TABLE "invTypeReactions";
-- DROP TABLE "invTypes";

DROP TABLE "mapCelestialStatistics";
DROP TABLE "mapConstellationJumps";
DROP TABLE "mapConstellations";
DROP TABLE "mapDenormalize";
DROP TABLE "mapJumps";
DROP TABLE "mapLandmarks";
DROP TABLE "mapLocationScenes";
DROP TABLE "mapLocationWormholeClasses";
DROP TABLE "mapRegionJumps";
DROP TABLE "mapRegions";
DROP TABLE "mapSolarSystemJumps";
DROP TABLE "mapSolarSystems";
DROP TABLE "mapUniverse";

DROP TABLE "planetSchematics";
DROP TABLE "planetSchematicsPinMap";
DROP TABLE "planetSchematicsTypeMap";

DROP TABLE "ramActivities";
DROP TABLE "ramAssemblyLineStations";
DROP TABLE "ramAssemblyLineTypeDetailPerCategory";
DROP TABLE "ramAssemblyLineTypeDetailPerGroup";
DROP TABLE "ramAssemblyLineTypes";
DROP TABLE "ramAssemblyLines";
DROP TABLE "ramInstallationTypeContents";
DROP TABLE "ramTypeRequirements";

DROP TABLE "staOperationServices";
DROP TABLE "staOperations";
DROP TABLE "staServices";
DROP TABLE "staStationTypes";
DROP TABLE "staStations";

DROP TABLE "trnTranslationColumns";
DROP TABLE "trnTranslations";

COMMIT;

VACUUM;
