# SSURGO_CheckgSSURGO.py
#
# Steve Peaslee, USDA-NRCS NCSS
#
# Run basic completeness check on seleced file geodatabases in the specified folder.
# Assumes that all databases were created by the SSURGO Download tools.
#
# Checklist:
#  1. Looks for all 6 SSURGO featureclasses but does not check contents or projection
#  2. Looks for all 69 standalone attribute tables
#  3. Looks for MapunitRaster layer, checking for attribute table with MUKEY and statistics.
#  4. Compares mapunit count in raster with MAPUNIT table. A mismatch is not considered to
#     be an error, but a warning.

# Original coding 01-05-2014
#
# Updated 2014-09-27
#
# Updated 2014-11-24. Added comparison of gSSURGO and SDM record counts for most attribute tables

## ===================================================================================
class MyError(Exception):
    pass

## ===================================================================================
def errorMsg():
    try:
        tb = sys.exc_info()[2]
        tbinfo = traceback.format_tb(tb)[0]
        theMsg = tbinfo + " \n" + str(sys.exc_type)+ ": " + str(sys.exc_value) + " \n"
        PrintMsg(theMsg, 2)

    except:
        PrintMsg("Unhandled error in errorMsg method", 2)
        pass

## ===================================================================================
def PrintMsg(msg, severity=0):
    # Adds tool message to the geoprocessor
    #
    #Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:
        for string in msg.split('\n'):
            #Add a geoprocessing message (in case this is run as a tool)
            if severity == 0:
                arcpy.AddMessage(string)

            elif severity == 1:
                arcpy.AddWarning(string)

            elif severity == 2:
                arcpy.AddMessage("    ")
                arcpy.AddError(string)

    except:
        pass

## ===================================================================================
def GetFieldInfo(gdb):
    # Not being used any more.
    #
    # Assumption is that this is all dictated by the XML Workspace document so schema problems
    # should not occur as long as the standard tools were used to create all databases.
    #
    # Create standard schema description for each geodatabase and use it in comparison
    # to the rest of the tables

    try:
        env.workspace = gdb
        tblList = arcpy.ListTables()
        tblList.extend(arcpy.ListFeatureClasses())
        tblList.extend(arcpy.ListRasters())
        dSchema = dict()
        arcpy.SetProgressorLabel("Reading geodatabase schema...")
        arcpy.SetProgressor("step", "Reading geodatabase schema...",  0, len(tblList), 1)

        for tbl in tblList:
            tblName = tbl.encode('ascii').upper()
            arcpy.SetProgressorLabel("Reading schema for " + os.path.basename(gdb) + ": " + tblName )
            desc = arcpy.Describe(tblName)
            fields = desc.fields
            stdSchema = list()

            for fld in fields:
                stdSchema.append((fld.baseName.encode('ascii').upper(), fld.length, fld.precision, fld.scale, fld.type.encode('ascii').upper()))
                #stdSchema.append((fld.baseName.encode('ascii').upper(), fld.length, fld.precision, fld.scale, fld.type.encode('ascii').upper(), fld.aliasName.encode('ascii').upper()))

            dSchema[tblName] = stdSchema
            arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()
        return dSchema

    except:
        errorMsg()
        return dict()

## ===================================================================================
def CheckFeatureClasses(theWS):
    # Simply make sure that each featureclass is present.
    #
    try:
        PrintMsg(" \n\tChecking for existence of featureclasses", 0)
        env.workspace = theWS
        missingFC = list()
        badFields = list()
        lFC = ['MUPOLYGON', 'FEATLINE', 'FEATPOINT', 'MULINE', 'SAPOLYGON', 'MUPOINT']

        # Create dictionary containing valid, ordered field names
        dFields = dict()
        dFields['MUPOLYGON'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'MUSYM', 'MUKEY', 'SHAPE_LENGTH', 'SHAPE_AREA']
        dFields['FEATLINE'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'FEATSYM', 'FEATKEY', 'SHAPE_LENGTH']
        dFields['FEATPOINT'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'FEATSYM', 'FEATKEY']
        dFields['MULINE'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'MUSYM', 'MUKEY', 'SHAPE_LENGTH']
        dFields['SAPOLYGON'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'LKEY', 'SHAPE_LENGTH', 'SHAPE_AREA']
        dFields['MUPOINT'] = ['OBJECTID', 'SHAPE', 'AREASYMBOL', 'SPATIALVER', 'MUSYM', 'MUKEY']

        for fc in lFC:
            fieldNames = list()

            if not arcpy.Exists(fc):
                # if a featureclass is missing from the geodatabase, add it to the list
                missingFC.append(fc)

            else:
                # Print a list of field names present in the featureclass
                fields = arcpy.Describe(fc).fields
                for fld in fields:
                    fieldNames.append(fld.name.upper())

                if fieldNames != dFields[fc]:
                    badFields.append(fc)
                    PrintMsg("\t" + fc + " has a schema problem: " + "', '".join(fieldNames) + "')", 0 )

        if len(missingFC) > 0:
            PrintMsg("\t" + os.path.basename(theWS) +  " is missing the following gSSURGO featureclasses: " + ", ".join(missingFC), 2)
            return False

        if len(badFields) > 0:
            # One or more featureclasses have a problem with fields or field order
            return False

        return True

    except:
        errorMsg()
        return False

## ===================================================================================
def CheckTables(theWS):
    # Simply make sure that each table is present and that the SACATALOG table has at least one record
    # The rest of the tables will be checked for record count and existence

    try:
        PrintMsg(" \n\t\tChecking for existence of metadata and SDV attribute tables")
        env.workspace = theWS
        missingTbl = list()
        lTbl = ['mdstatdomdet', 'mdstatdommas', 'mdstatidxdet', 'mdstatidxmas',
        'mdstatrshipdet', 'mdstatrshipmas', 'mdstattabcols', 'mdstattabs', 'sdvalgorithm', 'sdvattribute', 'sdvfolder',
        'sdvfolderattribute']

        for tbl in lTbl:
            if not arcpy.Exists(tbl):
                missingTbl.append(tbl)

        if len(missingTbl) > 0:
            PrintMsg("\t" + os.path.basename(theWS) +  " is missing the following gSSURGO attribute tables: " + ", ".join(missingTbl), 2)
            return False

        return True

    except:
        errorMsg()
        return False

## ===================================================================================
def CheckCatalog(theWS):
    # Simply make sure that at least one survey is populated in the SACATALOG table

    try:
        env.workspace = theWS
        saTbl = os.path.join(theWS, "sacatalog")

        if arcpy.Exists(saTbl):
            # parse Areasymbol from database name. If the geospatial naming convention isn't followed,
            # then this will not work.
            surveyList = list()

            with arcpy.da.SearchCursor(saTbl, ("AREASYMBOL")) as srcCursor:
                for rec in srcCursor:
                    # Get Areasymbol from SACATALOG table, assuming just one survey is present in the database
                    surveyList.append(rec[0])

            if len(surveyList) == 0:
                PrintMsg("\t" + os.path.basename(theWS) + "\\SACATALOG table contains no surveys", 2)
                return False

            else:
                PrintMsg(os.path.basename(theWS) + " contains " + str(len(surveyList)) + " soil surveys", 0)

        else:
            # unable to open SACATALOG table in existing dataset
            PrintMsg("\tSACATALOG table not found in " + os.path.basename(theWS), 2)
            return False

    except:
        errorMsg()
        return False

## ===================================================================================
def CheckRaster(theWS):
    # Simply make sure that at least one Mapunit Raster is present and that it has
    # a proper attribute table and statistics.
    env.workspace = theWS

    try:

        lRASTER = arcpy.ListRasters("MapunitRaster*")

        if len(lRASTER) == 0:
            PrintMsg("\t" + os.path.basename(theWS) + " has no MapunitRaster layer", 2)
            return False

        else:
            # Just check the first one found
            inRas = lRASTER[0]
            desc = arcpy.Describe(inRas)
            SR = desc.spatialReference
            gcs = SR.GCS
            dn = gcs.datumName
            PrintMsg(" \n\tChecking raster " + inRas,  0)
            PrintMsg(" \n\t\tCoordinate system: " + SR.name + ", " + dn, 0)

            # Make sure raster has statistics and check the MUKEY count
            try:
                # Get the statistic (MAX value) for the raster
                maxValue = int(arcpy.GetRasterProperties_management (inRas, "MAXIMUM").getOutput(0))
                PrintMsg(" \n\t\tRaster has statistics", 0)

            except:
                # Need to test it against a raster with no statistics
                #
                raise MyError, "\t" + inRas + " is missing raster statistics"

            try:
                # Get the raster mapunit count
                # This same check is run during the PolygonToRaster conversion.
                uniqueValues = int(arcpy.GetRasterProperties_management (inRas, "UNIQUEVALUECOUNT").getOutput(0))

                # Get the number of MUKEY values in the MAPUNIT table
                muCnt = MapunitCount(theWS, uniqueValues)

                # Compare tabular and raster MUKEY count
                if muCnt <> uniqueValues:
                    PrintMsg("\t\tDiscrepancy in mapunit count for " + inRas, 1)
                    PrintMsg("\t\t\t Raster mapunits: " + Number_Format(uniqueValues, 0, True), 0)
                    PrintMsg("\t\t\tTabular mapunits: " + Number_Format(muCnt, 0, True), 0)

                else:
                    PrintMsg(" \n\t\tMap unit count in raster matches featureclass", 0)

            except:
                # Need to test it against a raster with no statistics
                #
                PrintMsg("\t" + inRas + " has no raster attribute table", 2)
                return False

            # Make sure raster has MUKEY field
            lFlds = arcpy.ListFields(inRas)

            if lFlds is None:
                PrintMsg("\t" + inRas + " has no attributes fields", 2)
                return False

            if len(lFlds):
                hasMukey = False

                for fld in lFlds:
                    #PrintMsg("\t\t" + fld.name.upper(), 1)
                    if fld.name.upper() == "MUKEY":
                        hasMukey = True
                        # Make sure MUKEY is populated
                        cellCnt = 0
                        wc= "MUKEY = ''"

                        with arcpy.da.SearchCursor(inRas, ("MUKEY", "COUNT"), where_clause=wc) as srcCursor:
                            for rec in srcCursor:
                                # Get Areasymbol from SACATALOG table, assuming just one survey is present in the database
                                theMukey, cellCnt = rec

                            if cellCnt> 0:
                                PrintMsg("\t" + inRas + " is missing MUKEY values for " + Number_Format(cellCnt, 0, True) + " cells", 2  )
                                return False

                        break

            else:
                hasMukey = False

            if hasMukey == False:
                PrintMsg("\t" + inRas + " is missing the MUKEY field", 2)
                return False

            return True

    except:
        errorMsg()
        return False


## ===================================================================================
def MapunitCount(theWS, uniqueValues):
    # Return number of mapunits (mukey) in this survey using the MUPOLYGON featureclass
    #
    try:
        env.workspace = theWS
        muTbl = os.path.join(theWS, "mapunit")
        muPoly = os.path.join(theWS, "MUPOLYGON")

        if arcpy.Exists(muPoly):
            # use cursor to generate list of values
            # Originally used SET, but this causing MEMORY errors with CONUS database
            PrintMsg("\tGetting mapunit list from " + muPoly + "...", 0)
            valList = list()
            cntr = 0

            with arcpy.da.SearchCursor(muPoly, ['mukey']) as cur:
                cntr += 1
                
                for rec in cur:
                    valList.append(rec[0])

                    if cntr == 100000:
                        cntr = 0
                        valSet = set(valList)
                        valList = list(valSet)
                        del valSet
                                              
            # convert long list to a sorted list of unique values
            valSet = set(valList)
            valList = list(valSet)
            del valSet
            valList.sort()
            return len(valList)

        else:
            # unable to find MUPOLYGON featureclass
            PrintMsg("\tMUPOLYGON featureclass not found in " + os.path.basename(theWS), 2)
            return 0

    except:
        errorMsg()
        return 0

## ===================================================================================
def Number_Format(num, places=0, bCommas=True):
    try:
    # Format a number according to locality and given places
        #locale.setlocale(locale.LC_ALL, "")
        if bCommas:
            theNumber = locale.format("%.*f", (places, num), True)

        else:
            theNumber = locale.format("%.*f", (places, num), False)
        return theNumber

    except:
        errorMsg()
        return False

## ===================================================================================
def QuerySDA(sQuery, tbl):
    # Pass a query (from GetSDMCount function) to Soil Data Access designed to get the count of the selected records
    import time, datetime, urllib2, json

    try:
        # Create empty value list to contain the count
        # Normally the list should only contain one item
        valList = list()

        #PrintMsg("\t" + sQuery + " \n", 0)

	    # NEW POST REST REQUEST BEGINS HERE
	    #
        # Uses new HTTPS URL
        # Post Rest returns
        theURL = "https://sdmdataaccess.nrcs.usda.gov"
        url = theURL + "/Tabular/SDMTabularService/post.rest"

        # Create request using JSON, return data as JSON
        dRequest = dict()
        dRequest["format"] = "JSON"
        dRequest["query"] = sQuery
        jData = json.dumps(dRequest)

        # Send request to SDA Tabular service using urllib2 library
        req = urllib2.Request(url, jData)
        resp = urllib2.urlopen(req)
        jsonString = resp.read()

        # Convert the returned JSON string into a Python dictionary.
        data = json.loads(jsonString)
        del jsonString, resp, req

        # Find data section (key='Table')
        valList = list()

        if "Table" in data:
          dataList = data["Table"]  # Data as a list of lists. All values come back as string.

          # Iterate through dataList and reformat the data to create the menu choicelist

          for rec in dataList:
            val = rec[0]
            valList.append(int(val))

        else:
          # No data returned for this query
          raise MyError, "SDA query failed to return requested information: " + sQuery

        if len(valList) == 0:
            raise MyError, "SDA query failed: " + sQuery

        return valList[0]

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return 0

    except httplib.HTTPException, e:
        PrintMsg("HTTP Error: " + str(e) + " for " + tbl, 2)
        return -1

    except urllib2.URLError:
        PrintMsg(sQuery, 1)
        raise MyError, "Connection error for " + tbl
    
    except socket.error, e:
        raise MyError, "Soil Data Access problem for " + tbl + ": " + str(e)
        return -1

    except:
        #PrintMsg(" \nSDA query failed: " + sQuery, 1)
        errorMsg()
        return -1

## ===================================================================================
def GetSDMCount(theInputDB):
    # Run all SDA queries necessary to get the count for each SDM - soil attribute table
    # Can be vulnerable to failure if the SDM database changes before the gSSURGO database is checked.
    #
    try:
        dCount = dict()  # store SDM count for each table in a dictionary
        Q = "SELECT COUNT(*) AS RESULT FROM "  # Base part of each query

        # Get list of areasymbols
        PrintMsg(" \n\tChecking attribute tables", 0)
        bigList = list()
        saTbl = os.path.join(theInputDB, "LEGEND")

        with arcpy.da.SearchCursor(saTbl, ["AREASYMBOL"]) as cur:
            for rec in cur:
                bigList.append("'" + rec[0] + "'")

        size = 4  # limit to number of areasymbols in each
        test = 0
        iterNum = len(bigList) / size
        if (len(bigList) % size) or (len(bigList) < size):
            iterNum += 1

        PrintMsg(" \n\t\tGetting record count from SDM tables in " + str(iterNum) + " iterations...", 0)

        for i in range(0, len(bigList), size):
            test += 1
            asList = bigList[i:i + size]
            
            if len(asList) > 1:
                theAS = ",".join(asList)

            else:
                theAS = asList[0]
                
            subQuery = "SELECT MUKEY FROM MAPUNIT M, LEGEND L WHERE m.LKEY = L.LKEY AND L.AREASYMBOL IN (" + theAS + ")"

            arcpy.SetProgressor("step", "Getting record count from Soil Data Access...", 1, 55, 1)
            # CHORIZON
            tb1 = "chorizon"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if cnt == -1:
                # return empty dictionary, which will let the calling function know there is a serious problem
                # Record checks will be halted for all tables if this occurs
                return dCount

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHAASHTO
            tb1 = "chaashto"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chaashto.chkey AND component.cokey =  chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()


            # CHCONSISTENCE
            tb1 = "chconsistence"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chconsistence.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHDESGNSUFFIX
            tb1 = "chdesgnsuffix"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chdesgnsuffix.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHFRAGS
            tb1 = "chfrags"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chfrags.chkey AND  component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHPORES
            tb1 = "chpores"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chpores.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHSTRUCTGRP
            tb1 = "chstructgrp"
            tb2 = "chorizon"
            tb3 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chstructgrp.chkey AND component.cokey = chorizon.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHTEXT
            tb1 = "chtext"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chtext.chkey AND component.cokey = chorizon.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHTEXTUREGRP
            tb1 = "chtexturegrp"
            tb2 = "chorizon"
            tb3 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chtexturegrp.chkey AND component.cokey = chorizon.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHUNIFIED
            tb1 = "chunified"
            tb2 = "chorizon"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( chorizon.chkey = chunified.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHSTRUCT
            tb1 = "chstruct"
            tb2 = "chstructgrp"
            tb3 = "component"
            tb4 = "chorizon"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + ", " + tb4.upper() +" WHERE component.mukey IN (" + subQuery + ") AND ( chstructgrp.chstructgrpkey = chstruct.chstructgrpkey AND chorizon.chkey = chstructgrp.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHTEXTURE
            tb1 = "chtexture"
            tb2 = "chtexturegrp"
            tb3 = "component"
            tb4 = "chorizon"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + ", " + tb4.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( chtexturegrp.chtgkey = chtexture.chtgkey AND chorizon.chkey = chtexturegrp.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CHTEXTUREMOD
            tb1 = "chtexturemod"
            tb2 = "chtexture"
            tb3 = "chtexturegrp"
            tb4 = "component"
            tb5 = "chorizon"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + ", " + tb4.upper() + ", " + tb5.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( chtexture.chtkey = chtexturemod.chtkey AND chtexturegrp.chtgkey = chtexture.chtgkey AND chorizon.chkey = chtexturegrp.chkey AND component.cokey = chorizon.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COCANOPYCOVER
            tb1 = "cocanopycover"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cocanopycover.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COCROPYLD
            tb1 = "cocropyld"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cocropyld.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # CODIAGFEATURES
            tb1 = "codiagfeatures"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = codiagfeatures.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COECOCLASS
            tb1 = "coecoclass"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = coecoclass.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            # COEROSIONACC
            tb1 = "coerosionacc"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = coerosionacc.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COEPLANTS
            tb1 = "coeplants"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = coeplants.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COFORPROD
            tb1 = "coforprod"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = coforprod.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COFORPRODO
            tb1 = "coforprodo"
            tb2 = "coforprod"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( coforprod.cofprodkey = coforprodo.cofprodkey AND component.cokey = coforprod.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COGEOMORDESC
            tb1 = "cogeomordesc"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cogeomordesc.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COHYDRICCRITERIA
            tb1 = "cohydriccriteria"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cohydriccriteria.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COINTERP
            # Beginning with FY2020, only some records are imported into gSSURGO
            tb1 = "cointerp"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cointerp.cokey ) AND (cointerp.ruledepth = 0 OR cointerp.mrulekey = 54955)"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COMONTH
            tb1 = "comonth"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey =  comonth.cokey )"
            cnt = QuerySDA(sQuery, tb1)
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()


            # COMPONENT
            tb1 = "component"
            sQuery = Q + tb1.upper() + " WHERE component.mukey IN (" + subQuery + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # COPM
            tb1 = "copm"
            tb2 = "copmgrp"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( copmgrp.copmgrpkey = copm.copmgrpkey AND component.cokey = copmgrp.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COPMGRP
            tb1 = "copmgrp"
            tb2 = "component"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = copmgrp.cokey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COPWINDBREAK
            tb1 = "copwindbreak"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = copwindbreak.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # CORESTRICTIONS
            tb1 = "corestrictions"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = corestrictions.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSOILMOIST
            tb1 = "cosoilmoist"
            tb2 = "comonth"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( comonth.comonthkey = cosoilmoist.comonthkey AND component.cokey = comonth.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSOILTEMP
            tb1 = "cosoiltemp"
            tb2 = "comonth"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( comonth.comonthkey = cosoiltemp.comonthkey AND component.cokey = comonth.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSURFFRAGS
            tb1 = "cosurffrags"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cosurffrags.cokey) "
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COTAXFMMIN
            tb1 = "cotaxfmmin"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cotaxfmmin.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COTAXMOISTCL
            tb1 = "cotaxmoistcl"
            tb2 =  "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cotaxmoistcl.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COTEXT
            tb1 = "cotext"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() +  " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cotext.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COTREESTOMNG
            tb1 = "cotreestomng"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cotreestomng.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COTXFMOTHER
            tb1 = "cotxfmother"
            tb2 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( component.cokey = cotxfmother.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSURFMORPHGC
            tb1 = "cosurfmorphgc"
            tb2 = "cogeomordesc"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( cogeomordesc.cogeomdkey = cosurfmorphgc.cogeomdkey AND component.cokey = cogeomordesc.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSURFMORPHHPP
            tb1 = "cosurfmorphhpp"
            tb2 = "cogeomordesc"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( cogeomordesc.cogeomdkey = cosurfmorphhpp.cogeomdkey AND component.cokey = cogeomordesc.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSURFMORPHMR
            tb1 = "cosurfmorphmr"
            tb2 = "cogeomordesc"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND ( cogeomordesc.cogeomdkey = cosurfmorphmr.cogeomdkey AND component.cokey = cogeomordesc.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # COSURFMORPHSS
            tb1 = "cosurfmorphss"
            tb2 = "cogeomordesc"
            tb3 = "component"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE component.mukey IN (" + subQuery + ") AND (" + "cogeomordesc.cogeomdkey = cosurfmorphss.cogeomdkey AND component.cokey = cogeomordesc.cokey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt
            arcpy.SetProgressorPosition()

            # DISTMD
            tb1 = "distmd"
            sQuery = Q + tb1.upper() + " WHERE distmd.areasymbol IN (" + theAS + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # DISTINTERPMD
            tb1 = "distinterpmd"
            tb2 = "distmd"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE distmd.areasymbol IN (" + theAS + ") AND ( distmd.distmdkey = distinterpmd.distmdkey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # DISTLEGENDMD
            tb1 = "distlegendmd"
            tb2 = "distmd"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE distmd.areasymbol IN (" + theAS + ") AND ( distmd.distmdkey = distlegendmd.distmdkey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # FEATDESC
            tb1 = "featdesc"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + " WHERE featdesc.areasymbol IN (" + theAS + ")"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # LAOVERLAP
            tb1 = "laoverlap"
            tb2 = "legend"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE legend.areasymbol IN (" + theAS + ") AND ( legend.lkey = laoverlap.lkey )"
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # LEGEND
            tb1 = "legend"
            sQuery = Q + tb1.upper() + " WHERE legend.areasymbol IN (" + theAS + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # LEGENDTEXT
            tb1 = "legendtext"
            tb2 = "legend"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + " WHERE legend.areasymbol IN (" + theAS + ") AND ( legend.lkey = legendtext.lkey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # MAPUNIT
            tb1 = "mapunit"
            #sQuery = Q + tb1.upper() + " WHERE mapunit.mukey IN (" + theMU + ")"
            sQuery = Q + tb1.upper() + " WHERE mapunit.mukey IN (" + subQuery + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # MUAOVERLAP
            tb1 = "muaoverlap"
            tb2 = "legend"
            tb3 = "mapunit"
            sQuery = Q + tb1.upper() + ", " + tb2.upper() + ", " + tb3.upper() + " WHERE legend.areasymbol IN (" + theAS + ") AND ( mapunit.lkey = legend.lkey AND muaoverlap.mukey = mapunit.mukey )"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # MUAGGATT
            tb1 = "muaggatt"
            sQuery = Q + tb1.upper() + " WHERE muaggatt.mukey IN (" + subQuery + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # MUCROPYLD
            tb1 = "mucropyld"
            sQuery = Q + tb1.upper() + " WHERE SDM.DBO.mucropyld.mukey IN (" + subQuery + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # MUTEXT
            tb1 = "mutext"
            sQuery = Q + tb1.upper() + " WHERE mutext.mukey IN (" + subQuery + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # SACATALOG
            tb1 = "sacatalog"
            sQuery = Q + tb1.upper() + " WHERE SACATALOG.AREASYMBOL IN (" + theAS + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # SAINTERP
            tb1 = "sainterp"
            sQuery = Q + tb1.upper() +  " WHERE sainterp.areasymbol IN (" + theAS + ")"
            arcpy.SetProgressorLabel("SDM pass number " + str(test) + " of " + str(iterNum) + ": " + tb1)
            cnt = QuerySDA(sQuery, tb1)

            if tb1 in dCount:
                dCount[tb1] = dCount[tb1] + cnt

            else:
                dCount[tb1] = cnt

            arcpy.SetProgressorPosition()

            # End of query split

        return dCount

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return dCount

    except:
        errorMsg()
        return dCount

## ===================================================================================
def GetGDBCount(theInputDB, dSDMCounts):
    # Get record count from gSSURGO database
    # Only those soil attributes present in the SDM database will be checked
    # Some metadata and sdv tables are not found in SDM
    try:
        dGDBCounts = dict()
        env.workspace = theInputDB
        badCount = list()
        PrintMsg(" \n\t\tGetting record count from gSSURGO tables", 0)
        arcpy.SetProgressor("step", "Getting table record count from " + os.path.basename(theInputDB), 1, len(dSDMCounts), 1)

        tblList = sorted(dSDMCounts)

        for tbl in tblList:
            arcpy.SetProgressorLabel(tbl)
            sdmCnt = dSDMCounts[tbl]

            if arcpy.Exists(tbl):
                gdbCnt = int(arcpy.GetCount_management(os.path.join(theInputDB, tbl)).getOutput(0))

            else:
                raise MyError, "Missing table (" + tbl+ ") in " + os.path.basename(theInputDB)
                badCount.append((os.path.join(theInputDB, tbl), 0, sdmCnt))

            dGDBCounts[tbl] = gdbCnt
            arcpy.SetProgressorPosition()

            if sdmCnt != gdbCnt:
                if sdmCnt == -1:
                    # SDA query failed to get count for this table
                    badCount.append((tbl, 0, gdbCnt, gdbCnt))

                else:
                    # Record counts do not agree
                    badCount.append(( tbl, sdmCnt, gdbCnt, (sdmCnt - gdbCnt) ))

        if len(badCount) > 0:
            PrintMsg("\t\tDiscrepancy found in table counts:", 2)
            PrintMsg(" \nTABLE, SDM, GDB, DIFF", 0)

        for tbl in badCount:
            PrintMsg(tbl[0] + ", " + str(tbl[1]) + ", " + str(tbl[2]) + ", " + str(tbl[3]), 0)

        arcpy.SetProgressorLabel("")
        arcpy.ResetProgressor()

        if len(badCount) > 0:
            return False

        else:
            return True

    except MyError, e:
        # Example: raise MyError, "This is an error message"
        PrintMsg(str(e), 2)
        return False

    except:
        errorMsg()
        return False

## ===================================================================================
# main
import string, os, sys, traceback, locale, arcpy, httplib
from arcpy import env

from urllib2 import urlopen, URLError, HTTPError
import socket

try:
    arcpy.overwriteOutput = True

    # Script arguments...
    inLoc = arcpy.GetParameterAsText(1)               # input folder
    gdbList = arcpy.GetParameter(2)                   # list of geodatabases in the folder

    iCnt = len(gdbList)
    if iCnt > 1:
        PrintMsg(" \nProcessing " + str(iCnt) + " gSSURGO databases", 0)

    else:
        PrintMsg(" \nProcessing one gSSURGO database", 0)

    # initialize list of problem geodatabases
    problemList = list()

    for i in range(0, iCnt):
        gdbName = gdbList[i]
        theWS = os.path.join(inLoc, gdbName)
        PrintMsg(" \n" + (65 * "*"), 0)
        PrintMsg("Checking " + gdbName + "...", 0)
        PrintMsg((65 * "*"), 0)

        if CheckFeatureClasses(theWS):
            #pass
            dSDMCounts = GetSDMCount(theWS)  # dictionary containing SDM record counts

            if len(dSDMCounts) > 0:

                bCounts = GetGDBCount(theWS, dSDMCounts)

                if bCounts == False:
                    if not gdbName in problemList:
                        problemList.append(gdbName)

                if CheckTables(theWS):
                    if CheckCatalog:
                        pass

                    else:
                        if not gdbName in problemList:
                            problemList.append(gdbName)

                elif not gdbName in problemList:
                    problemList.append(gdbName)

            else:
                raise MyError, "Unable to check table record counts"

        elif not gdbName in problemList:
            problemList.append(gdbName)

        if CheckRaster(theWS):
            pass

        elif not gdbName in problemList:
            problemList.append(gdbName)

        if not gdbName in problemList:
            PrintMsg(" \n\t" + gdbName + " is OK", 0)

    if len(problemList) > 0:
        PrintMsg("The following geodatabases have problems: " + ", ".join(problemList) + " \n ", 2)

    else:
        PrintMsg(" ", 0)

except MyError, e:
    # Example: raise MyError, "This is an error message"
    PrintMsg(str(e) + " \n ", 2)

except:
    errorMsg()
